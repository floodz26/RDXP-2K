# RDXP-2K

Plugin de contrôle pour Roland RD-2000 — surface unifiée hardware + software.

> **Statut** : Phase 0 — validation technique du protocole SysEx avant tout développement plugin.

## Vision (résumé)

Le hardware est maître du son, le logiciel est maître de la configuration. Bidirectionnel par design : à l'ouverture, l'app lit l'état réel du RD-2000 (SysEx RQ1) ; chaque modification est immédiatement transmise (SysEx DT1).

Référence conceptuelle : plugin Access Virus TI2, adapté à un protocole MIDI/SysEx standard.

## Structure du repo

```
RDXP-2K/
├── docs/
│   ├── roadmap-v0.2.md      # Spécification initiale (large scope)
│   ├── roadmap-v0.3.md      # MVP recentré, standalone-first, macOS-first
│   └── reviews/             # Relectures critiques (Kimi, GPT)
├── proto-py/                # Phase 0 : validation SysEx Python
│   └── rd2k_probe.py        # Détection, RQ1/DT1, mesure latence, test de charge
└── plugin/                  # Phase 1+ : application JUCE (placeholder)
```

## Phase 0 — Aller / Ne-pas-aller

Avant toute ligne de C++/JUCE, on valide :

1. Le RD-2000 répond bien à un RQ1 sur ports MIDI USB
2. La latence round-trip RQ1 est < 50 ms
3. Un DT1 sur le volume d'une zone est appliqué et relisible
4. Le hardware supporte une rafale de 100 DT1 sans drop ni glitch

Voir [`proto-py/README.md`](proto-py/README.md).

## Stratégie produit (synthèse des avis)

- **MVP standalone-only** (VST3 reporté en Phase 2 — évite sandboxing DAW)
- **macOS prioritaire** (Core Audio natif, pas de driver tiers)
- **RDS read-only** (pas d'écriture du format binaire propriétaire Roland)
- **Pas d'API HTTP/MCP dans le MVP** (couche déclarative, Phase 3)
- **UI = 50% de la valeur** (à designer dès le départ, pas en afterthought)

## Licence

Voir [`LICENSE`](LICENSE).
