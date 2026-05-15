# RDXP-2K — Instructions Claude Code

## Contexte

Tu es l'agent de codage principal pour RDXP-2K, un plugin de contrôle et librarian pour le Roland RD-2000. Tu travailles en binôme avec Kimi K2.6 (via `kimi-cli` ou Hermes) qui est l'agent d'architecture et de revue de code.

## Rôle

- **Implémentation** : C++ JUCE, CMake, tests Catch2
- **Prototypage Python** : validation SysEx, scripts d'aide au dev
- **Architecture** : tu proposes, Kimi valide ou conteste
- **Git** : tu gères les branches, commits, PRs

## Workflow de collaboration avec Kimi

### 1. Avant de coder une feature

1. Lire `docs/roadmap-v0.3.md` pour le scope MVP
2. Si la feature est complexe (>200 lignes ou architecture nouvelle), préparer un brief dans `.kimi/briefs/` :
   ```markdown
   # Brief : [Nom de la feature]
   ## Contexte
   ## Objectif
   ## Approche proposée
   ## Questions pour Kimi
   ```
3. Lancer `kimi-cli` avec le brief : `kimi-cli --file .kimi/briefs/xxx.md`
4. Attendre le retour de Kimi (ou lire `.kimi/responses/xxx.md` si asynchrone)

### 2. Pendant le coding

- Kimi peut être invoqué pour :
  - Revue de code : `kimi-cli --file src/xxx.cpp --prompt "revue cette implémentation SysEx"`
  - Debug : envoyer le stderr + contexte
  - Refactor : proposition de simplification
- Les échanges asynchrones passent par `~/Sync/syncmail/channel-ia/`

### 3. Après implémentation

- Tests unitaires obligatoires (Catch2)
- Si la feature touche au protocole MIDI/SysEx, valider avec `proto-py/rd2k_probe.py` sur hardware réel
- Mettre à jour `docs/CHANGELOG.md`

## Stack technique

| Composant | Choix |
|-----------|-------|
| Framework | JUCE 7+ |
| Langage | C++17 |
| Build | CMake 3.22+ |
| Tests | Catch2 |
| JSON | nlohmann/json |
| MIDI | JUCE MidiInput/MidiOutput |
| HTTP (standalone only) | cpp-httplib |

## Conventions de code

- Namespace `rdxp2k::`
- Classes PascalCase, fonctions camelCase, membres privés suffixés `_`
- Audio thread : pas de malloc, pas de lock mutex (atomics/lock-free only)
- UI thread : pas de blocking I/O (MIDI via queue async)
- SysEx : toujours passer par `SysExTransactionManager`, jamais directement

## Points d'attention critiques

1. **VST3 = pas de réseau** : le serveur HTTP/MCP est uniquement dans la version Standalone
2. **SysEx throttling** : 20ms minimum entre packets, max 256 bytes/packet
3. **RDS read-only** : format natif = JSON (`.rd2k`), jamais écrire de RDS
4. **Program Write** : les DT1 écrivent en RAM temporaire uniquement — bouton "WRITE TO HARDWARE" obligatoire dans l'UI
5. **Morph delta-compressé** : n'envoyer que les params qui ont changé de >1 unité

## Fichiers de référence

- `docs/roadmap-v0.3.md` — MVP et phases
- `docs/reviews/avis-kimi.md` — critique d'architecture (à relire régulièrement)
- `docs/reviews/avis-gpt.md` — critique UX et workflow
- `MIDI/RD-2000_MIDI_Reference.md` — spec SysEx Roland
- `MIDI/RD-2000_Parameter_Guide_eng01_W.pdf` — guide paramètres officiel

## Communication avec l'équipe

- **Flo** (utilisateur principal) : décisions produit, test hardware, validation émotionnelle
- **Kimi** (co-architecte) : revue architecture, challenge des choix, optimisation protocole
- **Aurore** (Hermes/Mac mini) : génération de docs, scripts, déploiement

## Commandes utiles

```bash
# Build standalone
mkdir -p build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(sysctl -n hw.ncpu)

# Tests
./build/tests/rdxp2k_tests

# Probe SysEx (nécessite RD-2000 branché)
cd proto-py && source .venv/bin/activate && python3 rd2k_probe.py

# Lancer Kimi pour revue
kimi-cli --file src/xxx.cpp --prompt "Revue : cette implémentation respecte-t-elle le throttling SysEx ?"
```
