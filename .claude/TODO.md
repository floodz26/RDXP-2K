# RDXP-2K — TODO pour prochaines sessions

## Situation actuelle (2026-05-15)

Repo GitHub : https://github.com/floodz26/RDXP-2K
Branche active : `aurore/setup-mvp` (poussée, PR ouverte)

### Ce qui est en place
- [x] Structure agent : `.claude/CLAUDE.md`, `.kimi/KIMI.md`
- [x] Roadmap v0.3 MVP recentré : `docs/roadmap-v0.3.md`
- [x] Reviews Kimi + GPT : `docs/reviews/`
- [x] README minimal
- [x] `.gitignore` propre (exclut assets binaires MIDI/)

### Ce qui manque
- [ ] Prototype Python `proto-py/rd2k_probe.py` (Phase 0 — validation SysEx)
- [ ] `docs/ARCHITECTURE.md` — spec technique détaillée pour Kimi
- [ ] `docs/CHANGELOG.md`
- [ ] Setup JUCE minimal dans `plugin/`

---

## Rôle des agents (décision Flo)

| Agent | Rôle | Quand l'invoquer |
|-------|------|------------------|
| **Claude Opus** | Orchestrateur principal | Architecture, specs, revue de haut niveau, décisions produit, coordination |
| **Kimi K2.6** | Implémentation code | Éléments déjà bien définis et spécifiés — pas de décision d'architecture |
| **Aurore (Hermes)** | Support ops | Scripts, docs, déploiement, coordination inter-agents |

**Règle d'or** : Kimi ne code que sur brief clair. Claude prépare le brief, Kimi exécute.

---

## Prochaines étapes prioritaires

### 1. Phase 0 — Validation SysEx (bloquant tout le reste)

**Responsable** : Aurore ou Claude (proto Python)
**Brief pour Kimi** : non — c'est un script jetable, pas besoin de revue architecture

- [ ] Créer `proto-py/rd2k_probe.py` avec mido/rtmidi
  - Détection device MIDI "RD-2000"
  - RQ1 Program Common → mesure latence round-trip
  - DT1 volume zone → relecture → validation
  - Test de charge : 100 DT1 à 15ms
  - Test packet >256 bytes
  - Log CSV des métriques
- [ ] Flo lance sur hardware réel ce week-end
- [ ] Décision Go/No-Go

### 2. Phase 1 — Core JUCE (après Go)

**Responsable** : Kimi (implémentation) sous supervision Claude (architecture)

**Brief à préparer par Claude** :
- SysEx Codec (checksum Roland, nibbled data, DT1/RQ1)
- Transaction Manager (FIFO, throttling 20ms, retry)
- State Manager (modèle données, JSON serialize)
- Tests Catch2

**Livrable** : app standalone qui lit/écrit un paramètre SysEx

### 3. Phase 2 — Zone Viewer + Scene Snapshot

**Responsable** : Kimi (implémentation) + Claude (UI/UX review)

**Brief à préparer** :
- UI JUCE : 8 zones, volume/pan/switch/range/tone
- Scene Capture → `.rd2k` (ZIP JSON)
- Scene List + restore
- Détection conflits hardware/software

### 4. Phase 3+ — Standalone API, VST3, MCP

Voir roadmap v0.3. Pas avant que Phase 2 soit stable.

---

## Fichiers à créer / mettre à jour

| Fichier | Priorité | Responsable | Description |
|---------|----------|-------------|-------------|
| `proto-py/rd2k_probe.py` | 🔴 Haute | Aurore/Claude | Validation SysEx hardware |
| `docs/ARCHITECTURE.md` | 🟡 Moyenne | Claude | Spec technique pour briefs Kimi |
| `plugin/CMakeLists.txt` | 🟡 Moyenne | Kimi | Setup JUCE minimal |
| `plugin/src/SysExCodec.cpp` | 🟡 Moyenne | Kimi | Codec Roland |
| `plugin/src/TransactionManager.cpp` | 🟡 Moyenne | Kimi | Queue + throttling |
| `docs/CHANGELOG.md` | 🟢 Basse | Aurore | Historique des versions |

---

## Communication inter-agents

- **Claude ↔ Kimi** : via briefs dans `.kimi/briefs/`, revues de code
- **Claude ↔ Flo** : décisions produit, validation émotionnelle
- **Aurore ↔ Le Portier** : syncmail `channel-ia` pour coordination

---

*Dernière mise à jour : 2026-05-15 par Aurore*
