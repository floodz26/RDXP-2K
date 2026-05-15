# RDXP-2K

Remote control and librarian for the Roland RD-2000 stage piano.

## Status

Pre-alpha — protocol validation in progress.

## Structure

| Path | Purpose |
|------|---------|
| `proto-py/` | Python prototypes for SysEx validation and metrics collection |
| `plugin/` | JUCE standalone application (placeholder) |
| `docs/`   | Roadmaps, reviews, architecture decisions |

## Quick start (prototype)

```bash
cd proto-py
python3 -m venv .venv && source .venv/bin/activate
pip install mido python-rtmidi
python3 rd2k_probe.py
```

Requires an RD-2000 connected via USB MIDI.

## License

MIT — see LICENSE.
