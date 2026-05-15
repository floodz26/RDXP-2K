#!/usr/bin/env python3
"""
RDXP-2K — Phase 0 SysEx Validation Probe.

Disposable Python prototype. Single purpose: prove (or disprove) that the
Roland RD-2000 SysEx protocol is reliable enough to build a software editor
on top of. This is the Go/No-Go gate before any C++/JUCE work begins.

Usage examples:
    python rd2k_probe.py --list-ports
    python rd2k_probe.py --identity
    python rd2k_probe.py --read
    python rd2k_probe.py --write-readback --zone 1 --value 100
    python rd2k_probe.py --stress --count 100 --interval-ms 15
    python rd2k_probe.py --full-suite --csv logs/run.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import mido
except ImportError:
    sys.stderr.write(
        "mido not installed. Run: pip install -r requirements.txt\n"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Roland RD-2000 SysEx constants
# ---------------------------------------------------------------------------

ROLAND_ID = 0x41
RD2000_MODEL_ID = (0x00, 0x00, 0x75)
DEFAULT_DEVICE_ID = 0x10

CMD_RQ1 = 0x11  # Request data (read)
CMD_DT1 = 0x12  # Data set (write)

# Universal Identity Request (not Roland-specific): F0 7E <dev> 06 01 F7
IDENTITY_REQUEST = (0x7E, 0x7F, 0x06, 0x01)

# Addresses pulled from roadmap-v0.2.md §7.x. MUST be cross-checked against
# the official Roland "RD-2000 MIDI Implementation" PDF before trusting.
ADDR_SYSTEM_MASTER_VOLUME = (0x01, 0x00, 0x00, 0x00)
ADDR_PROGRAM_COMMON_BASE = (0x10, 0x00, 0x00, 0x00)

# Internal Zone block layout (from roadmap):
#   Program Temporary base = 10 00 00 00
#   Internal Zones start somewhere inside the Program Temporary block.
# The exact zone-block offset is one of the things Phase 0 must confirm.
# The placeholder below assumes Internal Zones live at offset 0x20 within
# the Program Temporary (i.e. 10 00 20 00) with each zone taking 0x80 bytes.
ADDR_PROGRAM_TEMP_INTERNAL_ZONE_BASE = (0x10, 0x00, 0x20, 0x00)
INTERNAL_ZONE_STRIDE = 0x80
OFFSET_ZONE_VOLUME = 0x00


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def roland_checksum(payload: list[int]) -> int:
    """Roland checksum: (128 - (sum & 0x7F)) & 0x7F over address + data."""
    return (128 - (sum(payload) & 0x7F)) & 0x7F


def build_rq1(address: tuple[int, int, int, int], size: int,
              device_id: int = DEFAULT_DEVICE_ID) -> list[int]:
    """Build a RQ1 (read) SysEx frame, returning the bytes between F0 and F7."""
    size_bytes = [
        (size >> 21) & 0x7F,
        (size >> 14) & 0x7F,
        (size >> 7) & 0x7F,
        size & 0x7F,
    ]
    payload = list(address) + size_bytes
    checksum = roland_checksum(payload)
    return [
        ROLAND_ID, device_id, *RD2000_MODEL_ID, CMD_RQ1,
        *payload, checksum,
    ]


def build_dt1(address: tuple[int, int, int, int], data: list[int],
              device_id: int = DEFAULT_DEVICE_ID) -> list[int]:
    """Build a DT1 (write) SysEx frame, returning the bytes between F0 and F7."""
    payload = list(address) + list(data)
    checksum = roland_checksum(payload)
    return [
        ROLAND_ID, device_id, *RD2000_MODEL_ID, CMD_DT1,
        *payload, checksum,
    ]


def build_identity_request() -> list[int]:
    return list(IDENTITY_REQUEST)


def zone_volume_address(zone_index_1based: int) -> tuple[int, int, int, int]:
    """Address of the volume parameter for Internal Zone N (1..8)."""
    if not 1 <= zone_index_1based <= 8:
        raise ValueError("zone index must be 1..8")
    base = ADDR_PROGRAM_TEMP_INTERNAL_ZONE_BASE
    offset_in_program = (zone_index_1based - 1) * INTERNAL_ZONE_STRIDE + OFFSET_ZONE_VOLUME
    # The Roland address space is 28-bit (7 bits per byte). We only adjust
    # the last byte since stride 0x80 crosses a byte boundary — handle carry.
    addr = list(base)
    carry = offset_in_program
    for i in range(3, -1, -1):
        addr[i] += carry & 0x7F
        carry = (carry >> 7) + (addr[i] >> 7)
        addr[i] &= 0x7F
        if carry == 0:
            break
    return tuple(addr)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------

def list_ports() -> None:
    print("=== MIDI Input ports ===")
    for name in mido.get_input_names():
        print(f"  {name}")
    print("=== MIDI Output ports ===")
    for name in mido.get_output_names():
        print(f"  {name}")


def find_rd2000_ports() -> tuple[str, str]:
    """Locate the RD-2000 primary input and output ports.

    The RD-2000 exposes two USB MIDI interfaces: "RD-2000" (primary, used
    for SysEx) and "RD-2000 MIDI" (DIN passthrough). We want the primary.
    """
    def pick(names: list[str]) -> Optional[str]:
        primary = [n for n in names if "RD-2000" in n and "MIDI" not in n]
        if primary:
            return primary[0]
        fallback = [n for n in names if "RD-2000" in n]
        return fallback[0] if fallback else None

    in_port = pick(mido.get_input_names())
    out_port = pick(mido.get_output_names())
    if not in_port or not out_port:
        raise RuntimeError(
            "RD-2000 ports not found. Run --list-ports to see available "
            "ports and check USB connection / driver."
        )
    return in_port, out_port


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    op: str
    ok: bool
    rtt_ms: Optional[float]
    detail: str


def send_and_wait(out_port, in_port, frame: list[int],
                  timeout_s: float = 0.5,
                  match: Optional[callable] = None) -> tuple[Optional[mido.Message], float]:
    """Send a SysEx frame and wait for the first matching SysEx reply.

    Returns (message, rtt_ms). message is None if no reply arrived in time.
    """
    while in_port.poll() is not None:
        pass  # drain
    msg = mido.Message("sysex", data=frame)
    t0 = time.perf_counter()
    out_port.send(msg)
    deadline = t0 + timeout_s
    while time.perf_counter() < deadline:
        reply = in_port.poll()
        if reply is not None and reply.type == "sysex":
            if match is None or match(reply):
                return reply, (time.perf_counter() - t0) * 1000.0
        else:
            time.sleep(0.001)
    return None, (time.perf_counter() - t0) * 1000.0


def is_rd2000_reply(msg: mido.Message) -> bool:
    data = tuple(msg.data)
    return (
        len(data) >= 6
        and data[0] == ROLAND_ID
        and data[2:5] == RD2000_MODEL_ID
    )


def is_identity_reply(msg: mido.Message) -> bool:
    data = tuple(msg.data)
    return len(data) >= 4 and data[0] == 0x7E and data[2] == 0x06 and data[3] == 0x02


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

def probe_identity(out_port, in_port) -> ProbeResult:
    frame = build_identity_request()
    reply, rtt = send_and_wait(out_port, in_port, frame,
                               timeout_s=1.0, match=is_identity_reply)
    if reply is None:
        return ProbeResult("identity", False, rtt,
                           "no Identity Reply within 1s")
    data = tuple(reply.data)
    mfg = data[4]
    return ProbeResult("identity", True, rtt,
                       f"Identity Reply mfg=0x{mfg:02x} family={data[5:7]} member={data[7:9]}")


def probe_read(out_port, in_port,
               address: tuple[int, int, int, int] = ADDR_SYSTEM_MASTER_VOLUME,
               size: int = 1) -> ProbeResult:
    frame = build_rq1(address, size)
    reply, rtt = send_and_wait(out_port, in_port, frame,
                               timeout_s=0.5, match=is_rd2000_reply)
    if reply is None:
        return ProbeResult("rq1", False, rtt, "no DT1 reply within 500ms")
    payload = list(reply.data)
    return ProbeResult("rq1", True, rtt,
                       f"reply {len(payload)} bytes: {bytes(payload).hex()}")


def probe_write_readback(out_port, in_port, zone: int, value: int) -> ProbeResult:
    addr = zone_volume_address(zone)
    write_frame = build_dt1(addr, [value & 0x7F])
    out_port.send(mido.Message("sysex", data=write_frame))
    time.sleep(0.025)  # respect ~20ms inter-packet interval
    read_frame = build_rq1(addr, 1)
    reply, rtt = send_and_wait(out_port, in_port, read_frame,
                               timeout_s=0.5, match=is_rd2000_reply)
    if reply is None:
        return ProbeResult("write_readback", False, rtt,
                           "no readback reply")
    data = list(reply.data)
    # DT1 reply: 41 dev 00 00 75 12 [addr4] [data...] [chk]
    if len(data) < 12:
        return ProbeResult("write_readback", False, rtt,
                           f"reply too short: {bytes(data).hex()}")
    read_value = data[10]
    ok = read_value == (value & 0x7F)
    return ProbeResult("write_readback", ok, rtt,
                       f"wrote {value}, read {read_value}")


def probe_stress(out_port, in_port, count: int, interval_ms: int,
                 zone: int = 1) -> ProbeResult:
    """Send `count` DT1s at `interval_ms` apart, then read final value and
    count how many made it (proxy: final value should match last sent)."""
    addr = zone_volume_address(zone)
    sent_values = []
    t0 = time.perf_counter()
    for i in range(count):
        value = (i % 127) + 1  # vary across 1..127
        sent_values.append(value)
        frame = build_dt1(addr, [value])
        out_port.send(mido.Message("sysex", data=frame))
        if i < count - 1:
            time.sleep(interval_ms / 1000.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    time.sleep(0.1)  # let hardware settle
    # Now read back and check final state
    read_frame = build_rq1(addr, 1)
    reply, rtt = send_and_wait(out_port, in_port, read_frame,
                               timeout_s=1.0, match=is_rd2000_reply)
    if reply is None:
        return ProbeResult("stress", False, elapsed_ms,
                           f"sent {count}x DT1 in {elapsed_ms:.1f}ms; "
                           f"NO readback reply (hardware may be saturated)")
    data = list(reply.data)
    read_value = data[10] if len(data) >= 12 else None
    expected = sent_values[-1]
    ok = read_value == expected
    return ProbeResult(
        "stress", ok, elapsed_ms,
        f"sent {count}x DT1 in {elapsed_ms:.1f}ms "
        f"(interval={interval_ms}ms); final read={read_value} expected={expected}",
    )


def latency_distribution(out_port, in_port, iterations: int = 10) -> ProbeResult:
    samples = []
    failures = 0
    for _ in range(iterations):
        res = probe_read(out_port, in_port)
        if res.ok and res.rtt_ms is not None:
            samples.append(res.rtt_ms)
        else:
            failures += 1
        time.sleep(0.025)
    if not samples:
        return ProbeResult("latency_dist", False, None,
                           f"all {iterations} reads failed")
    p50 = statistics.median(samples)
    p95 = sorted(samples)[max(0, int(len(samples) * 0.95) - 1)]
    mean = statistics.mean(samples)
    return ProbeResult(
        "latency_dist", failures == 0, mean,
        f"n={len(samples)} failures={failures} "
        f"min={min(samples):.1f} p50={p50:.1f} mean={mean:.1f} "
        f"p95={p95:.1f} max={max(samples):.1f} ms",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_result(r: ProbeResult) -> None:
    status = "OK " if r.ok else "FAIL"
    rtt = f"{r.rtt_ms:6.1f}ms" if r.rtt_ms is not None else "    --  "
    print(f"[{status}] {r.op:<16} {rtt}  {r.detail}")


def append_csv(path: Path, results: list[ProbeResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "op", "ok", "rtt_ms", "detail"])
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        for r in results:
            w.writerow([ts, r.op, int(r.ok),
                        f"{r.rtt_ms:.3f}" if r.rtt_ms is not None else "",
                        r.detail])


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RD-2000 SysEx validation probe")
    p.add_argument("--list-ports", action="store_true")
    p.add_argument("--identity", action="store_true",
                   help="Send Universal Identity Request")
    p.add_argument("--read", action="store_true",
                   help="Read Master Volume (RQ1, 1 byte)")
    p.add_argument("--latency", action="store_true",
                   help="Run RQ1 round-trip latency distribution")
    p.add_argument("--latency-iterations", type=int, default=20)
    p.add_argument("--write-readback", action="store_true")
    p.add_argument("--zone", type=int, default=1, help="Internal zone 1..8")
    p.add_argument("--value", type=int, default=100, help="Volume 0..127")
    p.add_argument("--stress", action="store_true")
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--interval-ms", type=int, default=15)
    p.add_argument("--full-suite", action="store_true",
                   help="Run identity + latency + write-readback + stress")
    p.add_argument("--csv", type=Path, default=None,
                   help="Append CSV log to this path")
    args = p.parse_args(argv)

    if args.list_ports:
        list_ports()
        return 0

    in_name, out_name = find_rd2000_ports()
    print(f"Using input  port: {in_name}")
    print(f"Using output port: {out_name}")

    results: list[ProbeResult] = []
    with mido.open_input(in_name) as in_port, \
         mido.open_output(out_name) as out_port:

        if args.full_suite:
            tasks = ["identity", "latency", "write-readback", "stress"]
        else:
            tasks = []
            if args.identity:
                tasks.append("identity")
            if args.read:
                tasks.append("read")
            if args.latency:
                tasks.append("latency")
            if args.write_readback:
                tasks.append("write-readback")
            if args.stress:
                tasks.append("stress")

        if not tasks:
            p.print_help()
            return 1

        for task in tasks:
            if task == "identity":
                r = probe_identity(out_port, in_port)
            elif task == "read":
                r = probe_read(out_port, in_port)
            elif task == "latency":
                r = latency_distribution(out_port, in_port,
                                         iterations=args.latency_iterations)
            elif task == "write-readback":
                r = probe_write_readback(out_port, in_port,
                                         zone=args.zone, value=args.value)
            elif task == "stress":
                r = probe_stress(out_port, in_port,
                                 count=args.count,
                                 interval_ms=args.interval_ms,
                                 zone=args.zone)
            else:
                continue
            results.append(r)
            print_result(r)

    if args.csv:
        append_csv(args.csv, results)
        print(f"\nLogged {len(results)} result(s) to {args.csv}")

    any_failed = any(not r.ok for r in results)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
