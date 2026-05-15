# RDXP-2K — Roadmap v0.3

**Date** : 2026-05-15
**Statut** : Roadmap recentrée après relectures critiques (Kimi, GPT)
**Remplace** : `roadmap-v0.2.md` reste comme référence exhaustive de la vision long terme

---

## 1. Pourquoi une v0.3

Les deux relectures (Kimi, GPT) convergent sur trois constats :

1. La v0.2 décrit **18–24 mois de travail équipe**, présenté comme 6 mois solo.
2. **Aucune validation empirique** du protocole SysEx Roland avant la spec → risque architectural majeur.
3. Le scope MVP était un **iceberg** (API REST, MCP, WebSocket, Morph, Hybrid Layers dès la Phase 1).

La v0.3 réduit le scope, ordonne les phases autour d'un **premier usage musical réel le plus tôt possible**, et ajoute une **Phase 0 de validation Go/No-Go**.

---

## 2. Décisions structurantes

| Décision | Raison |
|---|---|
| **Standalone-only pour MVP** | Élimine sandboxing DAW (Ableton/Logic surveillent agressivement les plugins ouvrant des sockets). VST3 reporté en Phase 2. |
| **macOS d'abord** | Core Audio natif, pas de driver tiers, écosystème de dev plus simple. Windows en Phase 2. |
| **RDS read-only** | L'écriture RDS demande de reverse-engineerer un checksum 16-bit non documenté (2–3 mois de risque). Format natif = JSON. |
| **Pas d'API HTTP/MCP au MVP** | Reporté en Phase 3. Au MVP, le seul client de l'état est l'UI locale. |
| **Pas de Morph au MVP** | Reporté en Phase 2. Snapshot brut JSON suffit pour les premières scènes. |
| **Pas d'EQ/Compresseur visuel au MVP** | Reporté en Phase 2. Au MVP, on expose les zones (le cœur du workflow live). |
| **UI = priorité produit** | Référence visuelle : Virus TI2. Designer ou kit Figma engagé dès la Phase 1. |

---

## 3. Phases

### Phase 0 — Validation technique (1–2 semaines) — **EN COURS**

**Objectif** : Go/No-Go sur le protocole SysEx avant d'écrire une ligne de C++.

Livrables :
- [x] Repo `RDXP-2K` initialisé
- [x] Documentation imported (v0.2, avis Kimi & GPT)
- [ ] **`proto-py/rd2k_probe.py`** : prototype Python (mido / python-rtmidi)
  - Détection des ports MIDI RD-2000
  - RQ1 → mesure round-trip latency (10 itérations, stats min/max/p50/p95)
  - DT1 → écriture d'un volume zone, relecture par RQ1, vérification
  - Test de charge : 100 DT1 à 15 ms d'intervalle, comptage des drops
  - Log CSV de toutes les mesures
- [ ] **Tests à faire avec hardware branché** (week-end)
- [ ] **Décision Go/No-Go** documentée dans `docs/phase0-results.md`

Critères de succès :
- Latence RQ1 round-trip p95 < 50 ms
- Écriture DT1 → relecture fiable à 100%
- Pas de drop sur 100 DT1 à 15 ms (ou identification claire du seuil de saturation)

Si échec : retour spec, peut-être que certains offsets sont verrouillés ou nécessitent un mode "edit" explicite.

### Phase 1 — Instrument utilisable (8–12 semaines)

**Objectif** : un standalone que je peux utiliser en répét pour préparer 5 scènes et switcher en 2 secondes.

Livrables :
- Setup JUCE 7 + CMake, build macOS (Standalone uniquement)
- SysEx Codec (encode/decode RQ1/DT1, checksum, nibbled) + tests Catch2
- Transaction Manager (queue FIFO, throttling 20 ms, retry 1 fois)
- Modèle de données : `Session > Scene > Program > Zone` (cf. roadmap v0.2 §3, à conserver)
- Dump complet à l'ouverture (RQ1 multi-blocs), state mirror local
- **Zone Viewer 8 zones** : volume, pan, zone switch, KB range, tone select
- **Scene Snapshot** : capture état complet → JSON, liste de scènes, restore par DT1
- **Bouton "WRITE TO HARDWARE"** (UX explicite pour persister sur le RD-2000)
- **Resync** : détection désalignement (Active Sensing + RQ1 heartbeat 2-3 s) + bouton manuel
- UI propre (référence Virus TI2)

Pas dans la Phase 1 : EQ visuel, compresseur visuel, morphing, macro knobs avancés, hybrid layers, VST3, API.

### Phase 2 — Différenciation (3–4 mois)

- VST3 (ajouter le wrapper JUCE, tester sur Ableton/Bitwig/Logic/Reaper)
- Windows port
- EQ 5 bandes graphique + Compresseur 3 bandes
- Morph delta-compressé (cf. avis Kimi §3.D — n'envoyer que les paramètres dont la valeur a changé de plus de 1 unité, agréger en DT1 contigus)
- Macro Knob Matrix
- Assign Controller Matrix
- Audio USB Router

### Phase 3 — Plateforme (3+ mois)

- Application Standalone héberge un serveur HTTP local (`cpp-httplib`)
- API REST avec sémantique musicale (`_semantic` fields)
- MCP Server pour LLM
- WebSocket events
- Le VST3 reste un pur pont MIDI/SysEx ; il se connecte au standalone si présent

### Phase 4+ — Avancé

- Hybrid Layers HW + VST (avec mesure de latence préalable, cf. avis Kimi §3.E)
- Dual-State Scene (A/B footswitch)
- Velocity Crossfader HW/VST
- Song Map / Cue DAW
- Knob Split Designer
- Smart Init / Layout archetypes
- Piano Voicing Studio

---

## 4. Risques résiduels et mitigation

| Risque | Mitigation |
|---|---|
| RD-2000 droppe des SysEx en rafale | Mesuré en Phase 0 ; throttling et delta-compression en Phase 2 |
| « Program Write » manuel = UX bizarre | Gros bouton explicite "WRITE TO HARDWARE" dès Phase 1 ; documenter clairement la séparation RAM vs Flash |
| Active Sensing non garantie | Heartbeat RQ1 toutes les 2-3 s en arrière-plan |
| UI bâclée tue la perception qualité | Référence visuelle Virus TI2 imposée dès la Phase 1, designer/kit Figma |
| Threading audio bloqué par locks | `LockFreeStateSnapshot` (atomics + buffer ping-pong) dès Phase 1 |
| Compatibilité DAW (VST3 + serveur HTTP) | Séparation stricte plugin / standalone (Phase 2 et Phase 3) |

---

## 5. KPIs Go/No-Go par phase

- **Phase 0 → 1** : critères techniques §3 Phase 0
- **Phase 1 → 2** : « je peux préparer 5 scènes et les switcher en 2 s en répét, sans relancer le standalone »
- **Phase 2 → 3** : VST3 stable sur 3 DAWs majeurs, Windows fonctionnel
- **Phase 3 → 4** : un script externe peut piloter une scène via API HTTP de bout en bout

---

## 6. Hors-scope explicite

Pour éviter le glissement de spec :

- ❌ Écriture du format RDS (lecture seule, et seulement pour extraction)
- ❌ Synchronisation MIDI Clock vers le RD-2000 (il ne l'accepte pas pour son séquenceur rythme)
- ❌ Émulation des sons du RD-2000 en software
- ❌ Cloud sync de scènes (au-delà de Git si l'utilisateur le souhaite)
- ❌ Multi-device (un seul RD-2000 connecté à la fois)
