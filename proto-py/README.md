# proto-py — Phase 0 SysEx Validation

Prototype Python jetable. Son seul rôle : prouver (ou infirmer) que le protocole SysEx du RD-2000 permet de construire un éditeur logiciel fiable. C'est le **Go/No-Go** avant toute ligne de C++/JUCE.

## Installation (macOS)

```bash
cd proto-py
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Préparation hardware

1. Brancher le RD-2000 au Mac en USB type B (port `USB COMPUTER`).
2. Vérifier que macOS voit deux ports MIDI : `RD-2000` (interface principale) et `RD-2000 MIDI`.
3. Sur le RD-2000, charger un programme **simple** (idéalement le tone d'usine `001 Concert Grand`) pour avoir un point de départ connu.
4. **Garder à portée** : un casque ou des moniteurs branchés, pour entendre les artefacts éventuels pendant le test de charge.

## Utilisation

```bash
# Lister les ports MIDI vus par mido
python rd2k_probe.py --list-ports

# Détection + identity request (test smoke, sans risque)
python rd2k_probe.py --identity

# Lecture d'un paramètre (RQ1) — par défaut Master Volume du System Common
python rd2k_probe.py --read

# Aller/retour complet : écrire un volume zone puis le relire
python rd2k_probe.py --write-readback --zone 1 --value 100

# Test de charge : 100 DT1 à 15 ms d'intervalle, comptage des drops
python rd2k_probe.py --stress --count 100 --interval-ms 15

# Tout enchaîner et logger en CSV
python rd2k_probe.py --full-suite --csv logs/run-$(date +%Y%m%d-%H%M%S).csv
```

## Ce qu'on cherche à mesurer

| Mesure | Cible |
|---|---|
| Latence round-trip RQ1 (p50) | < 25 ms |
| Latence round-trip RQ1 (p95) | < 50 ms |
| Taux de succès DT1 → readback identique | 100% |
| Drops sur 100 DT1 à 15 ms | 0 |
| Seuil de saturation | Intervalle minimum sans drop |

## Comprendre le SysEx Roland RD-2000

Frame générique :

```
F0 41 dev 00 00 75 cmd [addr 4 bytes] [data N bytes] [checksum 1 byte] F7
```

| Champ | Valeur |
|---|---|
| `F0` | Start SysEx |
| `41` | Manufacturer Roland |
| `dev` | Device ID (`0x10` par défaut, configurable `0x10`–`0x1F` ou `0x7F` broadcast) |
| `00 00 75` | Model ID RD-2000 |
| `cmd` | `0x11` = RQ1 (read), `0x12` = DT1 (write) |
| `addr` | Adresse 32-bit big-endian, 7 bits par byte |
| `data` | Pour RQ1 : taille demandée (4 bytes). Pour DT1 : valeurs |
| `checksum` | `(0x80 - somme(addr + data)) mod 0x80` |
| `F7` | End SysEx |

**Adresses utilisées par ce script** (à confirmer avec la MIDI Implementation officielle Roland que tu dois consulter — c'est une des choses que la Phase 0 valide) :

| Cible | Adresse | Taille |
|---|---|---|
| Identity Request | (universel, pas une adresse Roland) | — |
| System Common Master Volume | `01 00 00 00` | 1 byte |
| Program Common (start) | `10 00 00 00` | 84 bytes |
| Internal Zone 1 Volume | `10 00 20 00` (offset zone 1) + `00` | 1 byte |

⚠️ **À valider** : ces adresses sont reproduites de la roadmap v0.2 (cf. `docs/roadmap-v0.2.md` §7.x). Croiser systématiquement avec le PDF officiel Roland `RD-2000 MIDI Implementation` avant d'écrire.

## Livrables attendus de la Phase 0

À l'issue des tests hardware, créer `docs/phase0-results.md` avec :
- Versions de firmware et OS testés
- Mesures CSV brutes archivées
- Verdict Go/No-Go documenté
- Liste des comportements inattendus (offsets verrouillés, drops, etc.)
- Recommandations pour la Phase 1 (ajustement du throttling, etc.)
