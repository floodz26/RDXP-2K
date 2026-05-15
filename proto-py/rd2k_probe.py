#!/usr/bin/env python3
"""
RDXP-2K Probe — Phase 0 : Validation SysEx Roland RD-2000

Script de test pour valider la communication SysEx avec le RD-2000 avant
toute implémentation C++/JUCE. Génère un rapport CSV des métriques.

Usage:
    python3 rd2k_probe.py [--port "RD-2000"] [--device-id 16] [--output results/]

Requirements:
    pip install mido python-rtmidi

Auteur : Aurore (RDXP-2K)
Date   : 2026-05-15
"""

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import mido
from mido import Message, open_input, open_output

# ──────────────────────────────────────────────────────────────────────────────
# Constantes Roland RD-2000
# ──────────────────────────────────────────────────────────────────────────────

ROLAND_ID = 0x41
MODEL_ID = [0x00, 0x00, 0x75]
DEFAULT_DEVICE_ID = 0x10  # 16 en décimal

# Adresses de base
ADDR_SYSTEM_BASE = 0x00000000
ADDR_PROGRAM_BASE = 0x10000000

# Offsets Program Temporary
OFFSET_PRG_COMMON = 0x00000000      # 324 bytes
OFFSET_PRG_INT_ZONE = [
    0x00200000, 0x00280000, 0x00300000, 0x00380000,  # zones 1-4
    0x00500000, 0x00580000, 0x00600000, 0x00680000   # zones 5-8
]

# Offset volume dans Internal Zone (offset 0x00)
OFFSET_ZONE_VOLUME = 0x00

# Taille des requêtes
SIZE_PRG_COMMON_NAME = 0x10         # 16 bytes (nom du programme)
SIZE_ZONE_VOLUME = 0x01             # 1 byte

# Timing
THROTTLE_MS = 20                    # ms minimum entre packets SysEx
TIMEOUT_MS = 500                    # ms d'attente réponse RQ1


# ──────────────────────────────────────────────────────────────────────────────
# Structures de données
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    """Résultat d'un test individuel."""
    test_name: str
    status: str          # PASS, FAIL, SKIP, TIMEOUT
    latency_ms: float = 0.0
    details: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProbeSession:
    """Session complète de tests."""
    device_found: bool = False
    device_name: str = ""
    device_id: int = DEFAULT_DEVICE_ID
    firmware_version: str = ""
    results: List[ProbeResult] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())


# ──────────────────────────────────────────────────────────────────────────────
# Codec SysEx Roland
# ──────────────────────────────────────────────────────────────────────────────

def roland_checksum(address: int, data: List[int]) -> int:
    """Calcule le checksum Roland pour un message SysEx."""
    total = 0
    total += (address >> 24) & 0x7F
    total += (address >> 16) & 0x7F
    total += (address >> 8) & 0x7F
    total += address & 0x7F
    for b in data:
        total += b & 0x7F
    remainder = total % 128
    return 0 if remainder == 0 else (128 - remainder)


def build_rq1(device_id: int, address: int, size: int) -> List[int]:
    """Construit un message RQ1 (Data Request 1)."""
    addr_bytes = [
        (address >> 24) & 0x7F,
        (address >> 16) & 0x7F,
        (address >> 8) & 0x7F,
        address & 0x7F,
    ]
    size_bytes = [
        (size >> 24) & 0x7F,
        (size >> 16) & 0x7F,
        (size >> 8) & 0x7F,
        size & 0x7F,
    ]
    checksum = roland_checksum(address, size_bytes)
    msg = [0xF0, ROLAND_ID, device_id] + MODEL_ID + [0x11]
    msg += addr_bytes + size_bytes + [checksum, 0xF7]
    return msg


def build_dt1(device_id: int, address: int, data: List[int]) -> List[int]:
    """Construit un message DT1 (Data Set 1)."""
    addr_bytes = [
        (address >> 24) & 0x7F,
        (address >> 16) & 0x7F,
        (address >> 8) & 0x7F,
        address & 0x7F,
    ]
    checksum = roland_checksum(address, data)
    msg = [0xF0, ROLAND_ID, device_id] + MODEL_ID + [0x12]
    msg += addr_bytes + data + [checksum, 0xF7]
    return msg


def parse_dt1_response(msg_bytes: List[int]) -> Optional[Tuple[int, List[int]]]:
    """
    Parse une réponse DT1 (Data Set 1) du RD-2000.
    Retourne (address, data) ou None si invalide.
    """
    if len(msg_bytes) < 12:
        return None
    if msg_bytes[0] != 0xF0 or msg_bytes[-1] != 0xF7:
        return None
    if msg_bytes[1] != ROLAND_ID:
        return None
    if msg_bytes[3:6] != MODEL_ID:
        return None
    if msg_bytes[6] != 0x12:  # DT1 command
        return None

    address = (
        (msg_bytes[7] << 24)
        | (msg_bytes[8] << 16)
        | (msg_bytes[9] << 8)
        | msg_bytes[10]
    )
    data = msg_bytes[11:-2]  # entre l'adresse et le checksum
    return address, data


# ──────────────────────────────────────────────────────────────────────────────
# Détection MIDI
# ──────────────────────────────────────────────────────────────────────────────

def find_rd2000_port(preferred_name: Optional[str] = None) -> Optional[str]:
    """
    Cherche un port MIDI dont le nom contient 'RD-2000'.
    Accepte aussi les interfaces MIDI DIN (ex: interface Roland UM-ONE,
    iConnectivity, etc.) si elles transmettent les SysEx.
    
    Retourne le nom du port ou None.
    """
    inputs = mido.get_input_names()
    
    # 1. Recherche exacte par nom préféré
    if preferred_name:
        for name in inputs:
            if preferred_name in name:
                return name
    
    # 2. Recherche RD-2000 en USB
    for name in inputs:
        if "RD-2000" in name:
            return name
    
    # 3. Recherche interface Roland MIDI DIN
    for name in inputs:
        if "Roland" in name or "UM-ONE" in name or "UMONE" in name:
            return name
    
    # 4. Recherche générique Roland (insensible casse)
    for name in inputs:
        if "roland" in name.lower():
            return name
    
    # 5. Interface MIDI DIN générique (iConnectivity, M-Audio, etc.)
    # L'utilisateur peut spécifier manuellement avec --port
    return None


def list_midi_ports():
    """Affiche tous les ports MIDI disponibles."""
    print("\n=== Ports MIDI d'entrée ===")
    for i, name in enumerate(mido.get_input_names(), 1):
        marker = "  "
        if "RD-2000" in name:
            marker = "=>"
        print(f"  {marker} {i}. {name}")

    print("\n=== Ports MIDI de sortie ===")
    for i, name in enumerate(mido.get_output_names(), 1):
        marker = "  "
        if "RD-2000" in name:
            marker = "=>"
        print(f"  {marker} {i}. {name}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Communication MIDI
# ──────────────────────────────────────────────────────────────────────────────

class RD2000Connection:
    """Gère la connexion MIDI bidirectionnelle avec le RD-2000."""

    def __init__(self, port_name: str, device_id: int = DEFAULT_DEVICE_ID):
        self.port_name = port_name
        self.device_id = device_id
        self.in_port = None
        self.out_port = None

    def open(self) -> bool:
        try:
            self.in_port = open_input(self.port_name)
            self.out_port = open_output(self.port_name)
            return True
        except Exception as e:
            print(f"[ERREUR] Impossible d'ouvrir le port MIDI : {e}")
            return False

    def close(self):
        if self.in_port:
            self.in_port.close()
        if self.out_port:
            self.out_port.close()

    def send_sysex(self, data: List[int]) -> float:
        """Envoie un message SysEx et retourne le timestamp d'envoi."""
        msg = Message('sysex', data=bytes(data))
        t0 = time.perf_counter()
        self.out_port.send(msg)
        return t0

    def receive_sysex(self, timeout_ms: float = TIMEOUT_MS) -> Optional[List[int]]:
        """
        Attend une réponse SysEx avec timeout.
        Retourne les bytes du message ou None.
        """
        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        while time.perf_counter() < deadline:
            for msg in self.in_port.iter_pending():
                if msg.type == 'sysex':
                    return list(msg.data)
            time.sleep(0.001)  # 1ms polling
        return None

    def send_and_receive(
        self, data: List[int], timeout_ms: float = TIMEOUT_MS
    ) -> Tuple[Optional[List[int]], float]:
        """
        Envoie un SysEx et attend la réponse.
        Retourne (response_bytes, latency_ms) ou (None, 0.0).
        """
        # Vider le buffer d'entrée
        for msg in self.in_port.iter_pending():
            pass

        t0 = self.send_sysex(data)
        response = self.receive_sysex(timeout_ms)
        t1 = time.perf_counter()
        latency = (t1 - t0) * 1000.0
        return response, latency


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_identity_request(conn: RD2000Connection) -> ProbeResult:
    """Test 1 : Identity Request (Universal Non-Realtime)."""
    print("\n[TEST 1] Identity Request...")
    msg = [0xF0, 0x7E, conn.device_id, 0x06, 0x01, 0xF7]
    response, latency = conn.send_and_receive(msg, timeout_ms=1000)

    if response is None:
        return ProbeResult("Identity Request", "TIMEOUT", latency, "Pas de réponse")

    if len(response) < 15:
        return ProbeResult("Identity Request", "FAIL", latency,
                           f"Réponse trop courte ({len(response)} bytes)")

    # Vérifier l'Identity Reply
    if response[1:5] != [0x7E, conn.device_id, 0x06, 0x02]:
        return ProbeResult("Identity Request", "FAIL", latency,
                           "Format de réponse incorrect")

    manufacturer = response[5]
    family_code = (response[6] << 7) | response[7]
    device_number = (response[8] << 7) | response[9]
    version = f"{response[10]}.{response[11]}"

    details = (f"Manufacturer=0x{manufacturer:02X}, Family=0x{family_code:04X}, "
               f"Device=0x{device_number:04X}, Version={version}")
    return ProbeResult("Identity Request", "PASS", latency, details)


def test_rq1_program_name(conn: RD2000Connection) -> ProbeResult:
    """Test 2 : RQ1 Program Common (nom du programme courant)."""
    print("\n[TEST 2] RQ1 Program Common (nom)...")
    address = ADDR_PROGRAM_BASE + OFFSET_PRG_COMMON
    rq1 = build_rq1(conn.device_id, address, SIZE_PRG_COMMON_NAME)
    response, latency = conn.send_and_receive(rq1)

    if response is None:
        return ProbeResult("RQ1 Program Name", "TIMEOUT", latency)

    parsed = parse_dt1_response(response)
    if parsed is None:
        return ProbeResult("RQ1 Program Name", "FAIL", latency,
                           "Réponse DT1 invalide")

    addr, data = parsed
    # Le nom du programme est en ASCII, 16 caractères
    try:
        name = "".join(chr(b) for b in data if 32 <= b <= 126)
    except Exception:
        name = "<non-ASCII>"

    details = f"Nom='{name}', addr=0x{addr:08X}, data_len={len(data)}"
    return ProbeResult("RQ1 Program Name", "PASS", latency, details)


def test_rq1_zone_volume(conn: RD2000Connection) -> ProbeResult:
    """Test 3 : RQ1 Volume Zone 1 Interne."""
    print("\n[TEST 3] RQ1 Volume Zone 1...")
    address = ADDR_PROGRAM_BASE + OFFSET_PRG_INT_ZONE[0] + OFFSET_ZONE_VOLUME
    rq1 = build_rq1(conn.device_id, address, SIZE_ZONE_VOLUME)
    response, latency = conn.send_and_receive(rq1)

    if response is None:
        return ProbeResult("RQ1 Zone Volume", "TIMEOUT", latency)

    parsed = parse_dt1_response(response)
    if parsed is None:
        return ProbeResult("RQ1 Zone Volume", "FAIL", latency,
                           "Réponse DT1 invalide")

    addr, data = parsed
    volume = data[0] if data else -1
    details = f"Volume={volume}, addr=0x{addr:08X}"
    return ProbeResult("RQ1 Zone Volume", "PASS", latency, details)


def test_dt1_zone_volume(conn: RD2000Connection) -> ProbeResult:
    """Test 4 : DT1 Volume Zone 1 + relecture."""
    print("\n[TEST 4] DT1 Volume Zone 1 (écriture + relecture)...")
    address = ADDR_PROGRAM_BASE + OFFSET_PRG_INT_ZONE[0] + OFFSET_ZONE_VOLUME

    # Lire la valeur actuelle
    rq1 = build_rq1(conn.device_id, address, SIZE_ZONE_VOLUME)
    response, _ = conn.send_and_receive(rq1)
    if response is None:
        return ProbeResult("DT1 Zone Volume", "FAIL", 0.0,
                           "Impossible de lire la valeur actuelle")

    parsed = parse_dt1_response(response)
    original_value = parsed[1][0] if parsed else 64

    # Écrire une nouvelle valeur (ex: 100)
    test_value = 100
    dt1 = build_dt1(conn.device_id, address, [test_value])
    conn.send_sysex(dt1)
    time.sleep(THROTTLE_MS / 1000.0)

    # Relire
    response, latency = conn.send_and_receive(rq1)
    if response is None:
        # Restaurer la valeur originale même en cas d'échec
        dt1_restore = build_dt1(conn.device_id, address, [original_value])
        conn.send_sysex(dt1_restore)
        return ProbeResult("DT1 Zone Volume", "TIMEOUT", latency,
                           "Pas de réponse après écriture")

    parsed = parse_dt1_response(response)
    if parsed is None:
        dt1_restore = build_dt1(conn.device_id, address, [original_value])
        conn.send_sysex(dt1_restore)
        return ProbeResult("DT1 Zone Volume", "FAIL", latency,
                           "Réponse DT1 invalide après écriture")

    read_value = parsed[1][0] if parsed[1] else -1

    # Restaurer la valeur originale
    dt1_restore = build_dt1(conn.device_id, address, [original_value])
    conn.send_sysex(dt1_restore)
    time.sleep(THROTTLE_MS / 1000.0)

    if read_value == test_value:
        details = f"Écrit={test_value}, Relu={read_value}, Original restauré={original_value}"
        return ProbeResult("DT1 Zone Volume", "PASS", latency, details)
    else:
        details = f"Écrit={test_value}, Relu={read_value} (attendu {test_value})"
        return ProbeResult("DT1 Zone Volume", "FAIL", latency, details)


def test_load_100_dt1(conn: RD2000Connection) -> ProbeResult:
    """Test 5 : Charge — 100 DT1 à 15ms d'intervalle."""
    print("\n[TEST 5] Test de charge (100 DT1 à 15ms)...")
    address = ADDR_PROGRAM_BASE + OFFSET_PRG_INT_ZONE[0] + OFFSET_ZONE_VOLUME

    # Lire valeur originale
    rq1 = build_rq1(conn.device_id, address, SIZE_ZONE_VOLUME)
    response, _ = conn.send_and_receive(rq1)
    parsed = parse_dt1_response(response) if response else None
    original_value = parsed[1][0] if parsed else 64

    sent = 0
    dropped = 0
    t_start = time.perf_counter()

    for i in range(100):
        # Alterner entre deux valeurs pour forcer le changement
        value = 80 if (i % 2) == 0 else 90
        dt1 = build_dt1(conn.device_id, address, [value])
        conn.send_sysex(dt1)
        sent += 1
        time.sleep(0.015)  # 15ms

    t_elapsed = (time.perf_counter() - t_start) * 1000.0

    # Relire la valeur finale
    time.sleep(THROTTLE_MS / 1000.0)
    response, _ = conn.send_and_receive(rq1)
    parsed = parse_dt1_response(response) if response else None
    final_value = parsed[1][0] if parsed else -1

    # Restaurer
    dt1_restore = build_dt1(conn.device_id, address, [original_value])
    conn.send_sysex(dt1_restore)

    # On ne peut pas savoir exactement combien ont été dropés sans relire
    # chaque valeur, mais on vérifie que le hardware répond encore
    if final_value in [80, 90]:
        details = (f"Envoyés={sent}, Final={final_value}, "
                   f"Durée={t_elapsed:.1f}ms, Taux={sent/(t_elapsed/1000):.1f} msg/s")
        return ProbeResult("Load 100 DT1", "PASS", t_elapsed, details)
    else:
        details = (f"Envoyés={sent}, Final={final_value} (inattendu), "
                   f"Durée={t_elapsed:.1f}ms")
        return ProbeResult("Load 100 DT1", "FAIL", t_elapsed, details)


def test_oversized_packet(conn: RD2000Connection) -> ProbeResult:
    """Test 6 : RQ1 > 256 bytes (doit être ignoré)."""
    print("\n[TEST 6] RQ1 oversized (>256 bytes)...")
    address = ADDR_PROGRAM_BASE + OFFSET_PRG_COMMON
    # Demander 300 bytes (au-delà de la limite)
    rq1 = build_rq1(conn.device_id, address, 300)
    response, latency = conn.send_and_receive(rq1, timeout_ms=1000)

    if response is None:
        return ProbeResult("Oversized Packet", "PASS", latency,
                           "Correctement ignoré (pas de réponse)")
    else:
        return ProbeResult("Oversized Packet", "FAIL", latency,
                           f"Réponse inattendue reçue ({len(response)} bytes)")


# ──────────────────────────────────────────────────────────────────────────────
# Rapport
# ──────────────────────────────────────────────────────────────────────────────

def print_report(session: ProbeSession):
    """Affiche le rapport de session dans le terminal."""
    print("\n" + "=" * 70)
    print(" RAPPORT DE SESSION RDXP-2K PROBE")
    print("=" * 70)
    print(f"  Date        : {session.start_time}")
    print(f"  Device      : {session.device_name or 'Non détecté'}")
    print(f"  Device ID   : 0x{session.device_id:02X}")
    print(f"  Firmware    : {session.firmware_version or 'N/A'}")
    print("-" * 70)

    passed = sum(1 for r in session.results if r.status == "PASS")
    failed = sum(1 for r in session.results if r.status == "FAIL")
    timeouts = sum(1 for r in session.results if r.status == "TIMEOUT")
    skipped = sum(1 for r in session.results if r.status == "SKIP")

    for r in session.results:
        icon = {"PASS": "✓", "FAIL": "✗", "TIMEOUT": "⏱", "SKIP": "⊘"}.get(r.status, "?")
        print(f"  {icon} {r.test_name:30s} [{r.status:7s}] {r.latency_ms:8.2f}ms  {r.details}")

    print("-" * 70)
    print(f"  Résultats : {passed} PASS, {failed} FAIL, {timeouts} TIMEOUT, {skipped} SKIP")
    print("=" * 70)

    # Go/No-Go
    if passed >= 4 and failed == 0 and timeouts == 0:
        print("\n  🟢 GO — Le pipeline SysEx est fiable. Poursuivre vers Phase 1.")
    elif passed >= 3 and failed <= 1:
        print("\n  🟡 CAUTION — Quelques problèmes mineurs. Investiguer avant Phase 1.")
    else:
        print("\n  🔴 NO-GO — Le pipeline SysEx n'est pas fiable. Réévaluer le protocole.")
    print()


def export_csv(session: ProbeSession, output_dir: str):
    """Exporte les résultats en CSV."""
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(
        output_dir,
        f"rd2k_probe_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    )
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "test_name", "status", "latency_ms", "details",
            "device_name", "device_id", "firmware_version"
        ])
        for r in session.results:
            writer.writerow([
                r.timestamp, r.test_name, r.status,
                f"{r.latency_ms:.3f}", r.details,
                session.device_name, f"0x{session.device_id:02X}",
                session.firmware_version
            ])
    print(f"[INFO] Rapport CSV exporté : {filename}")
    return filename


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="RDXP-2K Probe — Validation SysEx RD-2000"
    )
    parser.add_argument(
        "--port", "-p",
        help="Nom du port MIDI (ex: 'RD-2000'). Détection auto si omis."
    )
    parser.add_argument(
        "--device-id", "-d", type=int, default=DEFAULT_DEVICE_ID,
        help=f"Device ID Roland (défaut: {DEFAULT_DEVICE_ID} = 0x{DEFAULT_DEVICE_ID:02X})"
    )
    parser.add_argument(
        "--output", "-o", default="results",
        help="Dossier de sortie pour le CSV (défaut: results/)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="Lister les ports MIDI disponibles et quitter"
    )
    parser.add_argument(
        "--tests", "-t", default="all",
        help="Tests à exécuter : 'all', 'identity', 'rq1', 'dt1', 'load', 'oversized'"
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" RDXP-2K Probe v0.1 — Phase 0 : Validation SysEx")
    print("=" * 70)

    if args.list:
        list_midi_ports()
        return 0

    # Lister les ports
    list_midi_ports()

    # Détection
    port_name = find_rd2000_port(args.port)
    if port_name is None:
        print("[ERREUR] Aucun port RD-2000 trouvé.")
        print("         Branche le piano en USB et vérifie les drivers Roland.")
        return 1

    print(f"[INFO] Port détecté : {port_name}")
    print(f"[INFO] Device ID    : 0x{args.device_id:02X}")

    # Session
    session = ProbeSession(device_id=args.device_id, device_name=port_name)

    # Connexion
    conn = RD2000Connection(port_name, args.device_id)
    if not conn.open():
        return 1

    try:
        # Exécuter les tests
        tests_to_run = args.tests.lower()

        if tests_to_run in ("all", "identity"):
            result = test_identity_request(conn)
            session.results.append(result)
            if result.status == "PASS":
                # Extraire la version du firmware si disponible
                if "Version=" in result.details:
                    session.firmware_version = result.details.split("Version=")[1].split(",")[0]

        if tests_to_run in ("all", "rq1"):
            session.results.append(test_rq1_program_name(conn))
            session.results.append(test_rq1_zone_volume(conn))

        if tests_to_run in ("all", "dt1"):
            session.results.append(test_dt1_zone_volume(conn))

        if tests_to_run in ("all", "load"):
            session.results.append(test_load_100_dt1(conn))

        if tests_to_run in ("all", "oversized"):
            session.results.append(test_oversized_packet(conn))

    finally:
        conn.close()

    # Rapport
    print_report(session)

    # Export CSV
    csv_file = export_csv(session, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
