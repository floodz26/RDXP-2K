# RDXP-2K Probe — Mode d'emploi

## Prérequis

### 1. Installer les drivers Roland (macOS)

Les drivers sont dans `~/Sync/RDXP-2K/MIDI/` (en local, pas sur GitHub) :

- **macOS 11-13** : `MIDI/v1.3/RD2000_USBDriver11.pkg`
- **macOS 14+** : `MIDI/v1.4/RD2000_USBDriver14.pkg`

Double-clique sur le `.pkg` et suis l'installation. Redémarre si demandé.

### 2. Brancher le RD-2000

1. Câble USB-B (imprimante) entre le RD-2000 et le Mac
2. Allumer le RD-2000
3. Vérifier dans **Audio MIDI Setup** (Applications > Utilitaires) que le RD-2000 apparaît

### 3. Installer les dépendances Python

```bash
cd ~/Sync/RDXP-2K/proto-py
python3 -m venv .venv
source .venv/bin/activate
pip install mido python-rtmidi
```

---

## Utilisation

### Lister les ports MIDI

```bash
python3 rd2k_probe.py --list
```

Tu dois voir un port nommé `"RD-2000"` ou `"Roland RD-2000"`.

### Lancer tous les tests

```bash
python3 rd2k_probe.py
```

### Lancer un test spécifique

```bash
# Test d'identité uniquement
python3 rd2k_probe.py --tests identity

# Tests de lecture uniquement
python3 rd2k_probe.py --tests rq1

# Test d'écriture uniquement
python3 rd2k_probe.py --tests dt1

# Test de charge
python3 rd2k_probe.py --tests load
```

### Spécifier un port ou device ID

```bash
# Si le port a un nom inhabituel
python3 rd2k_probe.py --port "Roland RD-2000 MIDI"

# Si le Device ID n'est pas le défaut (0x10 = 16)
python3 rd2k_probe.py --device-id 17
```

---

## Tests effectués

| # | Test | Description | Critère de succès |
|---|------|-------------|-------------------|
| 1 | **Identity Request** | Demande l'identité du device | Réponse avec Manufacturer=Roland |
| 2 | **RQ1 Program Name** | Lit le nom du programme courant | Nom lisible retourné |
| 3 | **RQ1 Zone Volume** | Lit le volume de la Zone 1 | Valeur 0-127 retournée |
| 4 | **DT1 Zone Volume** | Écrit le volume, relit, restaure | Écriture = relecture |
| 5 | **Load 100 DT1** | Envoie 100 messages à 15ms | Hardware répond encore après |
| 6 | **Oversized Packet** | RQ1 de 300 bytes (limite 256) | Ignoré silencieusement |

---

## Interprétation des résultats

### 🟢 GO (4+ PASS, 0 FAIL, 0 TIMEOUT)
Le pipeline SysEx est fiable. Tu peux passer à la Phase 1 (JUCE core).

### 🟡 CAUTION (3+ PASS, ≤1 FAIL)
Quelques problèmes mineurs. Investiguer avant de continuer.

### 🔴 NO-GO (<3 PASS ou >1 FAIL)
Le protocole SysEx ne fonctionne pas comme attendu. Vérifier :
- Drivers Roland installés ?
- Device ID correct ?
- Câble USB fiable ?
- RD-2000 en mode "USB MIDI" (pas "USB Audio") ?

---

## Fichiers générés

Les résultats sont exportés en CSV dans `proto-py/results/` :

```
results/
└── rd2k_probe_2026-05-15_143022.csv
```

Format CSV :
```
timestamp,test_name,status,latency_ms,details,device_name,device_id,firmware_version
```

---

## Dépannage

### "Aucun port RD-2000 trouvé"
- Vérifier que le piano est allumé
- Vérifier le câble USB
- Relancer Audio MIDI Setup
- Réinstaller les drivers Roland

### "TIMEOUT" sur tous les tests
- Vérifier le Device ID dans le menu System → MIDI → Device ID du RD-2000
- Essayer `--device-id 17` (0x11) ou `--device-id 127` (0x7F = broadcast)
- Vérifier que le RD-2000 n'est pas utilisé par une autre application

### "FAIL" sur DT1 Zone Volume
- Le volume peut être protégé en écriture selon le mode
- Essayer avec un autre paramètre (ex: pan)
- Vérifier que le RD-2000 n'est pas en mode "Local Off"

---

## Prochaine étape

Si 🟢 GO : retourner à `docs/roadmap-v0.3.md` et passer à la Phase 1 (Core JUCE).
