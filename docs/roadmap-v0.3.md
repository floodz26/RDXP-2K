# RDXP-2K — Roadmap v0.3 (MVP Recentré)

**Version** : 0.3  
**Date** : 2026-05-15  
**Auteur** : Aurore (synthèse Flo × Claude × Kimi × GPT)  
**Statut** : MVP en cours de définition — document vivant

---

## Synthèse des avis

Les deux relecteurs (Kimi et GPT) convergent sur 4 points critiques :

1. **Scope MVP trop large d'un facteur 2.5–3** → réduire drastiquement
2. **Valider le protocole SysEx avant C++** → prototype Python obligatoire
3. **Découpler API HTTP/MCP du plugin VST3** → standalone-only en MVP
4. **L'UI est 50% de la valeur** → pas un afterthought

Points spécifiques de Kimi à garder en tête :
- RDS en écriture = trou noir → JSON natif, RDS read-only
- Morph delta-compressé sinon le bus MIDI sature
- « Program Write » manuel = limitation UX majeure à adresser dès le MVP

---

## MVP v0.3 — Scope réduit

### Ce qui est IN (4 features)

| # | Feature | Description | Justification |
|---|---------|-------------|---------------|
| 1 | **Connexion + Dump/Restore** | Détection RD-2000, lecture état complet (RQ1), écriture paramètres (DT1), sauvegarde/restauration JSON | Fondation technique — sans ça, rien ne marche |
| 2 | **Zone Mixer basique** | Volume, Pan, Zone Switch, KB Range, Tone Select pour les 8 zones internes | Valeur musicale immédiate — le RD-2000 est pénible à mixer |
| 3 | **Scene Snapshot JSON** | Capture de l'état complet → fichier `.rd2k` (ZIP de JSON), liste de scènes, double-clic pour restaurer | Killer feature différenciante — pas dans l'éditeur officiel |
| 4 | **UI lisible et réactive** | 8 zones visibles, feedback immédiat, pas de fancy graphics | 50% de la perception de qualité |

### Ce qui est OUT du MVP (Phase 2+)

- ❌ VST3 — standalone uniquement
- ❌ API HTTP / MCP Server — pas de réseau
- ❌ WebSocket temps réel
- ❌ Morph Scene — pas d'interpolation
- ❌ EQ graphique / Compresseur — pas de traitement visuel
- ❌ Macro Knobs — pas de matrice de modulation
- ❌ Hybrid Layers — pas de routing HW+VST
- ❌ Assign Controller Matrix — pas de mapping MIDI avancé
- ❌ Audio USB Router — pas de routing audio
- ❌ RDS write — lecture seule
- ❌ Program Librarian complet — juste dump/restore

### Format de distribution MVP

**Standalone uniquement** (macOS d'abord, Windows ensuite).
Le VST3 est Phase 2+ quand le core est éprouvé.

---

## Architecture MVP

```
┌─────────────────────────────────────────┐
│           UI (JUCE)                     │
│  - Zone viewer (8 zones)                │
│  - Scene list (capture/restore)         │
│  - Connection status                    │
│  - "WRITE TO HARDWARE" button           │
└──────────────────┬──────────────────────┘
                   │ StateChange events
                   ▼
┌─────────────────────────────────────────┐
│      State Manager (thread-safe)        │
│  - Modèle Session > Scene > Program     │
│  - JSON serialize/deserialize           │
│  - Dirty flag (diff vs hardware)        │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│     SysEx Transaction Manager           │
│  - Queue FIFO simple (pas prioritaire)  │
│  - Throttling 20ms                      │
│  - Retry 1× sur timeout 500ms           │
│  - Heartbeat RQ1 toutes les 3s          │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│        SysEx Codec                      │
│  - DT1 encode / RQ1 encode              │
│  - Checksum Roland                      │
│  - Nibbled data encode/decode           │
│  - Address Map validation               │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│     JUCE MidiInput / MidiOutput         │
│        (USB MIDI → RD-2000)             │
└─────────────────────────────────────────┘
```

---

## Phases de développement

### Phase 0 — Validation technique (2 semaines, Go/No-Go)

**Objectif** : prouver que le pipeline SysEx est robuste sur hardware réel.

- [ ] **Prototype Python** (`proto-py/rd2k_probe.py`) :
  - [ ] Détection device MIDI
  - [ ] RQ1 Program Common → mesure latence round-trip
  - [ ] DT1 volume zone → relecture → validation
  - [ ] Test de charge : 100 DT1 à 15ms d'intervalle
  - [ ] Test packet >256 bytes → confirmation ignore
  - [ ] Log CSV des métriques
- [ ] **Décision Go/No-Go** : si fiable à 95%, continuer. Sinon réévaluer.

**Livrable** : `proto-py/results/YYYY-MM-DD_probe_report.csv`

### Phase 1 — Core JUCE minimal (4 semaines)

**Objectif** : application standalone qui compile et parle au RD-2000.

- [ ] Setup CMake + JUCE 7, projet "Hello World" standalone
- [ ] SysEx Codec (checksum, nibbled, DT1/RQ1) + tests Catch2
- [ ] Transaction Manager minimal (FIFO, throttling, retry)
- [ ] State Manager (modèle données, JSON serialize)
- [ ] Première connexion : lire Program Common, afficher nom dans UI
- [ ] Première édition : changer volume zone, voir le changement sur le RD-2000

**Livrable** : app standalone qui lit/écrit un paramètre SysEx

### Phase 2 — Zone Viewer + Scene Snapshot (4 semaines)

**Objectif** : instrument utilisable en live.

- [ ] UI Zone Viewer : 8 zones, volume/pan/switch/range/tone
- [ ] Édition bidirectionnelle (UI → DT1 → hardware → RQ1 → UI)
- [ ] Scene Capture : dump complet → JSON `.rd2k`
- [ ] Scene List : liste, nommage, double-clic restore
- [ ] Gestion des conflits : détection changement hardware, proposition "Resync"
- [ ] Bouton "WRITE TO HARDWARE" (Program Write simulation)

**Livrable** : tu peux préparer 5 scènes pour un concert et switcher en 2s

### Phase 3 — Polish + Standalone API (4 semaines, optionnel)

**Objectif** : API locale pour scripting et future intégration IA.

- [ ] `cpp-httplib` dans standalone uniquement
- [ ] Endpoints : `GET /status`, `GET /zones`, `PATCH /zones/:index`
- [ ] Auth basique (token fichier config)
- [ ] Tests avec `curl`
- [ ] UI polish : couleurs, responsive, tooltips

**Livrable** : app standalone + API locale testable

### Phase 4+ — VST3, MCP, Morph, etc.

Voir roadmap v0.2 originale. Tout ce qui était dans le MVP initial devient Phase 4+.

---

## Format natif `.rd2k`

ZIP contenant :
```
scene_name.rd2k/
├── manifest.json       # metadata, version, firmware
├── program_common.json # 324 bytes décodés
├── zones/
│   ├── internal_0.json # zone 1
│   ├── ...
│   └── internal_7.json # zone 8
├── system/
│   ├── common.json
│   └── compressor.json
└── scenes/
    ├── scene_001.json  # snapshot complet
    └── ...
```

---

## Métriques de succès du MVP

| Métrique | Cible |
|----------|-------|
| Latence round-trip RQ1 | < 100ms |
| DT1 fiable à 15ms d'intervalle | 95%+ sans drop |
| Switch scene | < 2 secondes |
| Temps de démarrage app | < 3 secondes |
| Crash en 2h d'utilisation | 0 |

---

## Risques et mitigation

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| SysEx pas fiable sur RD-2000 | Moyenne | Mortel | Phase 0 Go/No-Go |
| Latence MIDI trop haute pour le live | Moyenne | Majeur | Throttling adaptatif, delta-compression |
| JUCE UI trop lente/complexe | Faible | Majeur | UI simple, pas de rendu custom |
| Scope creep (trop de features) | Élevée | Majeur | Cette roadmap, revues Kimi régulières |
| Abandon par manque de feedback | Élevée | Majeur | MVP utilisable rapidement, tester en live |

---

## Prochaines étapes immédiates

1. **Ce week-end (Flo)** : brancher le RD-2000, lancer `rd2k_probe.py`, collecter métriques
2. **Semaine prochaine (Claude)** : si Go, setup JUCE minimal + SysEx Codec
3. **En parallèle (Kimi)** : revue de l'architecture State Manager, challenge du threading model

---

*Document vivant — dernière mise à jour : 2026-05-15*
