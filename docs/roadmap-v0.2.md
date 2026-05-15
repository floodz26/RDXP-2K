# RD-2000 Controller Plugin — Roadmap & Spécifications Backend
**Version** : 0.2 (draft)  
**Date** : 2026-05-15  
**Auteur** : Session de conception FLO × Claude  
**Format cible** : VST3 / Standalone (JUCE framework)  
**Statut** : Exploration pré-architecture — document vivant

---

## Table des matières

1. [Vision du produit](#1-vision-du-produit)
2. [Contraintes et hypothèses techniques](#2-contraintes-et-hypothèses-techniques)
3. [Modèle de données central](#3-modèle-de-données-central)
4. [Couche de communication MIDI/SysEx](#4-couche-de-communication-midisysex)
5. [Modules fonctionnels — spécifications détaillées](#5-modules-fonctionnels--spécifications-détaillées)
6. [Architecture globale du backend](#6-architecture-globale-du-backend)
7. [Gestion de l'état et synchronisation bidirectionnelle](#7-gestion-de-létat-et-synchronisation-bidirectionnelle)
8. [Intégration VST3 et DAW](#8-intégration-vst3-et-daw)
9. [Audio USB — routing pilotable](#9-audio-usb--routing-pilotable)
10. [API locale et intégration agent IA / MCP](#10-api-locale-et-intégration-agent-ia--mcp)
11. [Roadmap de développement — phases et priorités](#11-roadmap-de-développement--phases-et-priorités)
12. [Références techniques](#12-références-techniques)

---

## 1. Vision du produit

### 1.1 Problème résolu

Le Roland RD-2000 est un instrument de scène et de studio exceptionnel, mais son interface de contrôle — un écran LCD 256×80 px, des boutons curseurs, et une navigation à plusieurs niveaux de menus imbriqués — rend l'accès à ses paramètres avancés pénible, lent, et peu adapté au travail en studio ou à la reconfiguration rapide sur scène.

Par ailleurs, les éditeurs de contrôleurs MIDI existants (MIDI Designer, RD2000 Editor de Stuart Pryer) exposent les paramètres de manière plate, sans intelligence musicale : ils sont des interfaces génériques, pas des outils de workflow.

Ce plugin vise quelque chose de différent : **une surface de contrôle unifiée hardware + software**, dans laquelle le RD-2000 est un moteur sonore parmi d'autres, intégré dans un écosystème DAW (Ableton, Bitwig, Logic, Reaper). Le modèle de référence conceptuel est le plugin Virus TI2 d'Access Music — qui reste le cas le plus abouti de pilotage logiciel d'un synthétiseur hardware — mais adapté à une architecture MIDI standard (pas USB propriétaire), et étendu à l'hybridation avec des plugins VST.

### 1.2 Philosophie de conception

- **Le hardware est maître du son, le plugin est maître de la configuration.** Le RD-2000 joue toujours en temps réel ; le plugin ne se substitue pas à lui, il le configure.
- **Bidirectionnel par design.** À l'ouverture, le plugin lit l'état réel du RD-2000 (SysEx RQ1). Chaque modification dans le plugin est immédiatement transmise au hardware (SysEx DT1). Les deux sont toujours synchronisés.
- **La scène est l'unité de travail.** Une scène = 8 layers (internes et/ou plugins VST) + EQ + Compresseur + routing audio USB + macro knobs + configuration des contrôleurs. Tout est sauvegardé et rechargé en un geste.
- **Aucune fonction de menu Roland n'est laissée derrière.** Chaque paramètre accessible par SysEx a une représentation directe dans le plugin, sans navigation.

### 1.3 Périmètre fonctionnel (MVP vs Extensions)

**MVP (Phase 1-2, ~6 mois de dev solo)** :
- Connexion et détection du RD-2000
- Dump/restore complet de l'état (Program Temporary)
- Zone Mixer 8 layers (internes + VST)
- EQ 5 bandes + Compresseur 3 bandes système
- Scene Switcher (liste de scènes, bank select + SysEx)
- Program Librarian (fichiers `.rds` + SysEx dump JSON)
- Assign Controller Matrix
- Audio USB Router

**Extensions (Phase 3-4)** :
- Morph Scene (interpolation paramétrique)
- Macro Knob (matrice de modulation)
- Knob Split/Layer Designer (superknob spatial)
- Hybrid Layer (note routing HW + VST simultané)
- Velocity Crossfader HW/VST
- Dual-State Scene (A/B footswitch)
- Song Map (intégration cue DAW)
- Snapshot A/B Compare
- Piano Voicing Studio (note par note)
- Smart Init (archétypes musicaux)
- Zone Swap (drag & drop inter-zones)

---

## 2. Contraintes et hypothèses techniques

### 2.1 Protocole MIDI

| Paramètre | Valeur |
|-----------|--------|
| Manufacturer ID | `0x41` (Roland) |
| Model ID | `0x00 0x00 0x75` (RD-2000) |
| Device ID par défaut | `0x10` (configurable `0x10`–`0x1F` ou `0x7F` broadcast) |
| Max taille packet SysEx | 256 bytes |
| Intervalle entre packets | ~20 ms minimum |
| Active Sensing timeout | 420 ms |
| Canaux MIDI | 1–16 |
| Program Control Channel | Canal 16 par défaut (paramètre système `00 04`) |

### 2.2 Connexion physique

Le RD-2000 se connecte à l'ordinateur via **USB type B** (port `USB COMPUTER` au dos). Ce port expose simultanément :
- **2 interfaces MIDI USB** (`RD-2000` et `RD-2000 MIDI`) — le plugin utilise `RD-2000` (interface principale)
- **Interface audio USB 2 in / 2 out, 24-bit / 192 kHz** — pilotable en volume et routing par SysEx

La connexion USB nécessite le **driver Roland Vendor** (Windows : ASIO Roland, macOS : natif Core Audio). Le plugin doit détecter et avertir si le driver générique est actif.

### 2.3 Limites du protocole

- **Pas de MIDI Clock reçu** : le RD-2000 ne synchronise pas son séquenceur de rythme sur un MIDI Clock externe. Le plugin doit intercepter le clock du DAW et l'utiliser pour piloter les changements de scène, pas le RD-2000 lui-même.
- **Pas de Song Position Pointer** : idem — le plugin gère la timeline côté logiciel.
- **Programme Temporaire uniquement** : les modifications SysEx DT1 affectent la RAM temporaire. Pour persister, il faut un Program Write (manuel sur le hardware, ou géré par le plugin via simulation de séquence — voir §5.1).
- **Données nibblées** : de nombreux paramètres utilisent un format 4 bits (nibbled), où une valeur sur 2 bytes `0a 0bH` = `a × 16 + b`. À gérer dans le codec SysEx.
- **Taille des requêtes RQ1** : la taille doit être exactement celle spécifiée dans la Parameter Address Map. Une taille incorrecte = pas de réponse du RD-2000.
- **Format RDS** : partiellement reverse-engineeré par la communauté. Compression propriétaire (pas de règle 8-en-7 générale). Le plugin gère le RDS en lecture (dump JSON) mais l'écriture de contenu modifié dans le RDS reste risquée (checksum 16 bits non documenté).

### 2.4 Stack technologique recommandé

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Framework plugin | **JUCE 7+** | Standard industriel VST3/AU/CLAP, gestion MIDI native, audio thread-safe |
| Format de distribution | **VST3** principal, **Standalone** secondaire | VST3 : Ableton, Bitwig, Logic, Reaper. Standalone : usage sans DAW |
| Langage | **C++17** | Requis par JUCE ; performances temps réel |
| Sérialisation état | **JSON (nlohmann/json)** | Lisible, versionnable, diffable pour patches |
| Tests | **Catch2** | Léger, header-only, compatible JUCE |
| Build system | **CMake 3.22+** | Standard avec JUCE |
| CI | **GitHub Actions** | Build macOS + Windows en parallèle |

**Note sur CLAP** : le format CLAP (Bitwig natif) sera envisagé en Phase 3 via le wrapper `clap-juce-extensions`. Pas en MVP.

---

## 3. Modèle de données central

Toutes les données du plugin gravitent autour d'un modèle hiérarchique : `Session > Scene > Program > Zone + System`. Ce modèle est indépendant du format de transport (SysEx, JSON, RDS).

### 3.1 Hiérarchie des entités

```
Session
├── metadata (nom, version firmware, device ID)
├── SystemState
│   ├── SystemCommon      (32 params — offsets 00 00–1F)
│   ├── SystemCompressor  (18 params — offsets 00 01 00–11)
│   └── AudioUSBConfig    (7 params extraits de SystemCommon)
├── SceneList [ Scene × N ]
│   └── Scene
│       ├── metadata (nom, index, couleur)
│       ├── programRef → Program (ou snapshot inline)
│       ├── macroKnobs [ MacroKnob × 9 ]
│       ├── dualState { stateA: ProgramDelta, stateB: ProgramDelta }
│       └── morphConfig { duration_ms, curve }
├── ProgramLibrary [ Program × 200 ]
│   └── Program
│       ├── metadata (nom 16 chars ASCII, index, bank)
│       ├── ProgramCommon  (324 bytes = 1 dump RQ1 complet)
│       ├── InternalZone   × 8
│       ├── ExternalZone   × 8
│       ├── Delay          (85 bytes)
│       ├── Reverb         (82 bytes)
│       ├── ModulationFX   × 4 (263 bytes chacun)
│       └── SongRhythm     (5 bytes)
└── LayerTemplateLibrary [ LayerTemplate × N ]
    └── LayerTemplate
        ├── zoneParams (InternalZone ou ExternalZone snapshot)
        ├── vstPlugin { id, preset, routingConfig }
        └── hybridConfig { splitMode, velocityCurve }
```

### 3.2 Structure InternalZone

Reflète exactement les offsets de la Parameter Address Map (section 7.8 du document de référence).

```cpp
struct InternalZone {
    // Mixing
    uint8_t  volume;              // 0x00 : 0–127
    uint8_t  pan;                 // 0x01 : 0–127 (L64=0, centre=64, R63=127)
    uint8_t  delaySendLevel;      // 0x02 : 0–127
    uint8_t  reverbSendLevel;     // 0x03 : 0–127
    uint8_t  resonanceSendLevel;  // 0x04 : 0–127
    bool     routing;             // 0x05 : Normal=0, Inverse=1

    // Keyboard mapping
    uint8_t  kbRangeLower;        // 0x06 : 21–108 (A0–C8)
    uint8_t  kbRangeUpper;        // 0x07 : 21–108
    uint8_t  velRangeLower;       // 0x08 : 1–127
    uint8_t  velRangeUpper;       // 0x09 : 1–127
    int8_t   velSensitivity;      // 0x0A : -63 à +63 (stocké 1–127)
    uint8_t  velMax;              // 0x0B : 1–127
    int8_t   zoneTranspose;       // 0x0C : -48 à +48 (stocké 16–112)
    int8_t   coarseTune;          // 0x0D : -48 à +48 (stocké 16–112)
    int8_t   fineTune;            // 0x0E : -50 à +50 (stocké 14–114)
    bool     zoneSwitch;          // 0x0F : OFF=0, ON=1

    // Control routing switches
    bool     damperSwitch;        // 0x10
    bool     fc1Switch;           // 0x11
    bool     fc2Switch;           // 0x12
    bool     extPedalSwitch;      // 0x13
    bool     modSwitch;           // 0x14
    bool     pitchBendSwitch;     // 0x15
    bool     assign1Switch;       // 0x18
    bool     assign2Switch;       // 0x19
    bool     assign3Switch;       // 0x1A
    bool     assign4Switch;       // 0x1B
    bool     assign5Switch;       // 0x1C

    // Tone selection
    uint8_t  toneBankMSB;         // 0x20
    uint8_t  toneBankLSB;         // 0x21
    uint8_t  toneProgramChange;   // 0x22
    uint8_t  toneCategory;        // 0x23
    uint8_t  toneColorCategory;   // 0x24

    // Sound shaping offsets
    uint8_t  monoPoly;            // 0x25 : MONO=0, POLY=1, MONO/LEGATO=2
    uint8_t  pitchBendRange;      // 0x26 : 0–24 semitones
    bool     portamentoSwitch;    // 0x27
    uint8_t  portamentoTime;      // 0x28–29 (nibbled)
    int8_t   cutoffOffset;        // 0x2A : -64 à +63 (stocké 0–127)
    int8_t   resonanceOffset;     // 0x2B
    int8_t   attackTimeOffset;    // 0x2C
    int8_t   decayTimeOffset;     // 0x2D
    int8_t   releaseTimeOffset;   // 0x2E
    int8_t   vibratoRate;         // 0x2F
    int8_t   vibratoDepth;        // 0x30
    int8_t   vibratoDelay;        // 0x31

    // Piano-specific (zones utilisant un tone de piano)
    uint8_t  nuance;              // 0x32 : TYPE1=0, TYPE2=1, TYPE3=2
    int8_t   hammerNoise;         // 0x33 : -2 à +2 (stocké 62–66)
    uint8_t  damperNoise;         // 0x34
    uint8_t  stringResonance;     // 0x35
    uint8_t  keyOffResonance;     // 0x36
    uint8_t  soundLift;           // 0x37
    uint8_t  mechKeyOnNoise;      // 0x38
    uint8_t  mechKeyOffNoise;     // 0x39
    uint8_t  humNoise;            // 0x3A
};
```

### 3.3 Structure Scene

```cpp
struct Scene {
    std::string name;          // 16 chars max
    std::string color;         // pour l'UI (#RRGGBB)
    int         programIndex;  // référence dans ProgramLibrary (0–199)
    
    // Macro Knobs (9 assignables A1–A9)
    std::array<MacroKnob, 9> macroKnobs;
    
    // Dual-State A/B
    struct DualState {
        ProgramDelta stateA;   // delta de params vs program de référence
        ProgramDelta stateB;
        bool         isStateA; // état courant
    } dualState;
    
    // Morph configuration
    struct MorphConfig {
        float    durationMs;   // 100–10000 ms
        CurveType curve;       // LINEAR, EASE_IN, EASE_OUT, EASE_INOUT, CUSTOM
        std::vector<float> customCurve; // points de contrôle si CUSTOM
    } morphConfig;
    
    // Audio USB overrides pour cette scène
    AudioUSBConfig usbOverride;
    bool           usbOverrideEnabled;
};
```

### 3.4 Structure MacroKnob

```cpp
struct MacroKnob {
    std::string name;      // label affiché dans l'UI
    uint8_t     hwAssign;  // knob physique (A1=0 … A9=8, Wheel1=9, Wheel2=10, Slider=11)
    
    struct Destination {
        enum class Type { INTERNAL_ZONE_PARAM, EXTERNAL_ZONE_PARAM, 
                          CC_TO_VST, SYSEX_DIRECT };
        Type    type;
        int     zoneIndex;     // 0–7 (si zone param)
        int     paramOffset;   // offset SysEx dans la zone
        int     vstMidiChannel;
        int     ccNumber;
        float   scale;         // multiplicateur (peut être négatif)
        float   offset;        // décalage après scale
        CurveType curve;       // réponse non linéaire
        float   minValue;
        float   maxValue;
    };
    
    std::vector<Destination> destinations; // N destinations par macro
};
```

### 3.5 Structure ProgramDelta

Représente un sous-ensemble de paramètres modifiés par rapport à un programme de référence. Utilisé par Dual-State, Morph Scene, et le moteur de transition.

```cpp
struct ProgramDelta {
    // Chaque entrée : (adresse SysEx absolue 4 bytes, valeur courante, valeur cible)
    struct ParamChange {
        uint32_t sysexAddress;
        uint8_t  currentValue;
        uint8_t  targetValue;
        bool     isInterpolable; // false pour les paramètres discrets (tone select, zone switch)
    };
    std::vector<ParamChange> changes;
};
```

---

## 4. Couche de communication MIDI/SysEx

### 4.1 Architecture de la couche transport

```
┌─────────────────────────────────────────────────────┐
│                   Plugin State                       │
│              (thread UI / audio)                     │
└──────────────────────┬──────────────────────────────┘
                       │  StateChange events
                       ▼
┌─────────────────────────────────────────────────────┐
│              SysEx Transaction Manager              │
│  - File d'attente priorisée (temps réel vs batch)   │
│  - Throttling 20ms entre packets >256 bytes         │
│  - Retry sur timeout (500ms)                        │
│  - Détection Active Sensing (timeout 420ms)         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              SysEx Codec (Encoder / Decoder)        │
│  - Génère DT1 (écriture) et RQ1 (lecture)          │
│  - Calcul checksum Roland                           │
│  - Gestion nibbled data                             │
│  - Validation adresses contre Address Map           │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           JUCE MidiOutput / MidiInput               │
│         (USB MIDI vers RD-2000)                     │
└─────────────────────────────────────────────────────┘
```

### 4.2 Calcul du checksum Roland

```cpp
uint8_t rolandChecksum(uint32_t address, const std::vector<uint8_t>& data) {
    uint32_t sum = 0;
    sum += (address >> 24) & 0x7F;  // MSB
    sum += (address >> 16) & 0x7F;
    sum += (address >>  8) & 0x7F;
    sum += (address      ) & 0x7F;  // LSB
    for (uint8_t b : data) sum += b;
    uint32_t remainder = sum % 128;
    return (remainder == 0) ? 0 : (128 - remainder);
}
```

### 4.3 Génération d'un message DT1

```cpp
std::vector<uint8_t> buildDT1(uint8_t deviceId, uint32_t address, 
                               const std::vector<uint8_t>& data) {
    std::vector<uint8_t> msg = {
        0xF0,           // SysEx start
        0x41,           // Roland ID
        deviceId,       // 0x10 par défaut
        0x00, 0x00, 0x75, // Model ID (RD-2000)
        0x12,           // DT1 command
        uint8_t((address >> 24) & 0x7F),
        uint8_t((address >> 16) & 0x7F),
        uint8_t((address >>  8) & 0x7F),
        uint8_t( address        & 0x7F),
    };
    msg.insert(msg.end(), data.begin(), data.end());
    msg.push_back(rolandChecksum(address, data));
    msg.push_back(0xF7); // EOX
    return msg;
}
```

### 4.4 Génération d'un message RQ1 (lecture)

```cpp
std::vector<uint8_t> buildRQ1(uint8_t deviceId, uint32_t address, uint32_t size) {
    uint8_t checksum = rolandChecksum(address, {
        uint8_t((size >> 24) & 0x7F),
        uint8_t((size >> 16) & 0x7F),
        uint8_t((size >>  8) & 0x7F),
        uint8_t( size        & 0x7F)
    });
    // Note : checksum RQ1 inclut les bytes de taille dans la somme
    return {
        0xF0, 0x41, deviceId, 0x00, 0x00, 0x75, 0x11,
        uint8_t((address >> 24) & 0x7F),
        uint8_t((address >> 16) & 0x7F),
        uint8_t((address >>  8) & 0x7F),
        uint8_t( address        & 0x7F),
        uint8_t((size    >> 24) & 0x7F),
        uint8_t((size    >> 16) & 0x7F),
        uint8_t((size    >>  8) & 0x7F),
        uint8_t( size           & 0x7F),
        checksum,
        0xF7
    };
}
```

### 4.5 Transaction Manager — file de priorité

Les messages SysEx sont classés en trois niveaux de priorité :

| Priorité | Type | Exemples | Latence cible |
|----------|------|----------|---------------|
| HIGH | Temps réel — performance | Zone Switch, Volume, Macro Knob live | < 5 ms |
| MEDIUM | Édition paramétrique | Changement EQ, EQ Gain, Cutoff | < 50 ms |
| LOW | Batch — dump/restore | RQ1 full program, Morph Scene batch | < 2 s |

```cpp
class SysExTransactionManager {
public:
    void enqueue(std::vector<uint8_t> message, Priority priority, 
                 std::function<void(bool)> callback = nullptr);
    
    // Appelé depuis le timer thread (20ms interval)
    void processQueue();
    
    // Gestion des réponses RQ1
    void handleIncomingData(const juce::MidiMessage&);
    
    // Détection de connexion
    bool isDeviceConnected() const;

private:
    std::priority_queue<PendingMessage> queue_;
    std::chrono::steady_clock::time_point lastSend_;
    static constexpr int kMinIntervalMs = 20;
    static constexpr int kTimeoutMs = 500;
    std::atomic<bool> awaitingResponse_ { false };
};
```

### 4.6 Codec nibbled data

```cpp
// Encode une valeur entière en format nibbled (N bytes de 4 bits)
std::vector<uint8_t> encodeNibbled(uint32_t value, int numBytes) {
    std::vector<uint8_t> result(numBytes);
    for (int i = numBytes - 1; i >= 0; --i) {
        result[i] = value & 0x0F;
        value >>= 4;
    }
    return result;
}

// Decode nibbled → entier
uint32_t decodeNibbled(const std::vector<uint8_t>& bytes) {
    uint32_t result = 0;
    for (uint8_t b : bytes) result = (result << 4) | (b & 0x0F);
    return result;
}
```

### 4.7 Adresses mémoire complètes — référence plugin

```cpp
namespace Addresses {
    // Base addresses
    static constexpr uint32_t SYSTEM_BASE   = 0x00000000;
    static constexpr uint32_t PROGRAM_BASE  = 0x10000000;
    
    // System offsets
    static constexpr uint32_t SYS_COMMON    = 0x00000000; // size: 0x20
    static constexpr uint32_t SYS_COMPRESSOR= 0x00010000; // size: 0x12
    
    // Program offsets (relatifs à PROGRAM_BASE)
    static constexpr uint32_t PRG_COMMON    = 0x00000000; // size: 0x144 (324 bytes)
    static constexpr uint32_t PRG_SONG      = 0x00020000; // size: 0x05
    static constexpr uint32_t PRG_DELAY     = 0x00040000; // size: 0x55
    static constexpr uint32_t PRG_REVERB    = 0x00060000; // size: 0x52
    
    // Modulation FX (4 zones × 2 slots)
    static constexpr uint32_t PRG_MODFX_Z1  = 0x00100000; // size: 0x107
    static constexpr uint32_t PRG_TREAMO_Z1 = 0x00120000;
    static constexpr uint32_t PRG_MODFX_Z2  = 0x00140000;
    static constexpr uint32_t PRG_TREAMO_Z2 = 0x00160000;
    static constexpr uint32_t PRG_MODFX_Z3  = 0x00180000;
    static constexpr uint32_t PRG_TREAMO_Z3 = 0x001A0000;
    static constexpr uint32_t PRG_MODFX_Z4  = 0x001C0000;
    static constexpr uint32_t PRG_TREAMO_Z4 = 0x001E0000;
    
    // Internal Zones (8 zones)
    static constexpr uint32_t PRG_INT_Z[8] = {
        0x00200000, 0x00280000, 0x00300000, 0x00380000,  // zones 1–4
        0x00500000, 0x00580000, 0x00600000, 0x00680000   // zones 5–8
    };
    static constexpr uint32_t PRG_INT_SIZE  = 0x00000679; // 1657 bytes
    
    // External Zones (8 zones)
    static constexpr uint32_t PRG_EXT_Z[8] = {
        0x00400000, 0x00420000, 0x00440000, 0x00460000,  // zones 1–4
        0x00700000, 0x00720000, 0x00740000, 0x00760000   // zones 5–8
    };
    static constexpr uint32_t PRG_EXT_SIZE  = 0x0000004C; // 76 bytes
    
    // Absolute addresses helpers
    static uint32_t sysCommonParam(uint8_t offset) { 
        return SYSTEM_BASE | (uint32_t)offset; 
    }
    static uint32_t programParam(uint32_t blockOffset, uint8_t paramOffset) {
        return PROGRAM_BASE | blockOffset | paramOffset;
    }
    static uint32_t internalZoneParam(int zone, uint8_t paramOffset) {
        return PROGRAM_BASE | PRG_INT_Z[zone] | paramOffset;
    }
    static uint32_t externalZoneParam(int zone, uint8_t paramOffset) {
        return PROGRAM_BASE | PRG_EXT_Z[zone] | paramOffset;
    }
}
```

---

## 5. Modules fonctionnels — spécifications détaillées

### 5.1 Program Dump Manager (lecture/écriture état complet)

**Responsabilité** : lire et écrire l'état complet du Program Temporary depuis/vers le RD-2000.

**Séquence de dump complet (RQ1)** :

Le dump complet est découpé en blocs séquentiels pour respecter la limite de 256 bytes par packet :

```
1. System Common      → RQ1 addr 00 00 00 00, size 00 00 00 20
2. System Compressor  → RQ1 addr 00 01 00 00, size 00 00 00 12
3. Program Common     → RQ1 addr 10 00 00 00, size 00 00 01 44
4. Program Song       → RQ1 addr 10 00 02 00, size 00 00 00 05
5. Program Delay      → RQ1 addr 10 00 04 00, size 00 00 00 55
6. Program Reverb     → RQ1 addr 10 00 06 00, size 00 00 00 52
7. ModFX Zone 1       → RQ1 addr 10 00 10 00, size 00 00 01 07
   [... × 4 zones ModFX + 4 TremoloAmp]
8. Internal Zone 1    → RQ1 addr 10 00 20 00, size 00 00 06 79
   [... × 8 zones internes]
9. External Zone 1    → RQ1 addr 10 00 40 00, size 00 00 00 4C
   [... × 8 zones externes]
```

**Durée estimée du dump complet** : ~2–3 secondes (latence USB + 20ms entre packets).

**Déclencheurs du dump** :
- Ouverture du plugin (auto)
- Changement de preset sur le hardware (détecté via Program Change entrant)
- Bouton "Sync from Hardware" dans l'UI

**Sérialisation JSON** :

```json
{
  "rd2000_program": {
    "version": "1.0",
    "firmware": "2.00",
    "timestamp": "2026-05-15T14:32:00Z",
    "name": "My Patch",
    "systemCommon": { ... },
    "systemCompressor": { ... },
    "programCommon": { ... },
    "internalZones": [
      { "index": 0, "active": true, "volume": 100, "pan": 64, ... },
      ...
    ],
    "externalZones": [ ... ],
    "delay": { ... },
    "reverb": { ... }
  }
}
```

### 5.2 Scene Manager

**Responsabilité** : gérer la liste des scènes, les transitions, et la synchronisation avec le DAW.

**Opérations** :
- `createScene(name)` → crée une scène à partir de l'état courant du RD-2000
- `activateScene(index)` → envoie le Program Change + delta SysEx vers le RD-2000
- `deleteScene(index)`
- `reorderScene(from, to)`
- `duplicateScene(index)`

**Activation d'une scène — séquence** :

```
1. Envoyer Bank Select MSB (CC 0) sur canal Program Control
2. Envoyer Bank Select LSB (CC 32)
3. Envoyer Program Change
4. Attendre 50ms (le RD-2000 charge le preset)
5. Envoyer les overrides SysEx DT1 (paramètres qui diffèrent du preset stocké)
   — EQ overrides (si activés)
   — USB Audio config (si override activé)
   — Macro knob assignments
```

**Format de fichier de session** :

```
session_name.rd2k         (archive ZIP renommée)
├── session.json          (métadonnées, liste des scènes)
├── programs/
│   ├── program_001.json
│   └── ...
├── scenes/
│   ├── scene_001.json
│   └── ...
└── templates/
    └── layer_templates.json
```

### 5.3 Morph Scene Engine

**Responsabilité** : interpoler les paramètres continus entre deux états du programme sur une durée définie.

**Paramètres interpolables** (valeurs continues) :
- Volume, Pan, Delay Send, Reverb Send par zone
- EQ Gain 5 bandes (Low, Mid-Low, Mid-Mid, Mid-High, High)
- Compresseur : Threshold, Ratio, Level, Attack, Release (par bande)
- Cutoff Offset, Resonance Offset, Attack/Decay/Release Offset par zone
- USB Audio Input Volume, USB Audio Output Volume

**Paramètres non-interpolables** (discrets — commutent au début ou à la fin) :
- Zone Switch (ON/OFF)
- Tone selection (Bank + PC)
- Mono/Poly
- Zone Transpose, Coarse Tune (en semitones entiers)

**Algorithme** :

```cpp
void MorphEngine::startMorph(const ProgramDelta& delta, 
                              float durationMs, CurveType curve) {
    morphStart_ = std::chrono::steady_clock::now();
    morphDuration_ = durationMs;
    curve_ = curve;
    
    // Envoyer immédiatement les params discrets (non-interpolables)
    for (auto& change : delta.changes) {
        if (!change.isInterpolable) {
            txManager_.enqueue(buildDT1(change.sysexAddress, {change.targetValue}),
                               Priority::HIGH);
        }
    }
    
    // Stocker les params interpolables pour le timer
    interpolableChanges_ = filterInterpolable(delta.changes);
    isActive_ = true;
}

// Appelé depuis timer thread à ~60 Hz
void MorphEngine::tick() {
    if (!isActive_) return;
    float t = elapsed() / morphDuration_;
    if (t >= 1.0f) { t = 1.0f; isActive_ = false; }
    float eased = applyCurve(t, curve_);
    
    for (auto& change : interpolableChanges_) {
        uint8_t value = uint8_t(std::lerp(float(change.currentValue), 
                                           float(change.targetValue), eased));
        txManager_.enqueue(buildDT1(change.sysexAddress, {value}), 
                           Priority::MEDIUM);
    }
}
```

**Résolution de la courbe** :
- `LINEAR` : `t`
- `EASE_IN` : `t²`
- `EASE_OUT` : `1 - (1-t)²`
- `EASE_INOUT` : `t < 0.5 ? 2t² : 1 - 2(1-t)²`
- `CUSTOM` : interpolation par spline cubique sur points de contrôle

### 5.4 Macro Knob Engine

**Responsabilité** : translater le mouvement d'un knob physique en messages SysEx multiples vers le RD-2000 et/ou CC vers les plugins VST.

**Flux** :

```
Knob physique A3 (CC assigné, ex CC 83)
    → reçu par le plugin via MidiInput
    → mappé vers MacroKnob[2]
    → pour chaque Destination de MacroKnob[2] :
        → calculer valeur = clamp(value * scale + offset, min, max)
        → si type INTERNAL_ZONE_PARAM : buildDT1 → txManager HIGH
        → si type CC_TO_VST : juce::MidiMessage::controllerEvent → MidiOutput VST
        → si type SYSEX_DIRECT : buildDT1 custom → txManager HIGH
```

**Découplage scène** : les destinations et scalings d'un MacroKnob sont définis par scène. Le changement de scène recharge la matrice de modulation.

### 5.5 Knob Split/Layer Designer

**Responsabilité** : permettre à un knob physique de faire glisser les splits de clavier et les crossfades de vélocité de plusieurs zones simultanément.

**Modèle** :

```cpp
struct SplitVector {
    // Décrit le comportement de chaque zone quand le knob bouge de 0 à 127
    struct ZoneMotion {
        int   zoneIndex;
        float kbLowerDelta;    // variation de KB Range Lower (en semitones/127)
        float kbUpperDelta;    // variation de KB Range Upper
        float velLowerDelta;   // variation de Vel Range Lower
        float velUpperDelta;   // variation de Vel Range Upper
        float volumeDelta;     // variation de volume (crossfade)
    };
    std::vector<ZoneMotion> zoneMotions;
};
```

**Exemple concret** : "Piano/Strings graduel"  
- Zone 1 (Piano) : `kbUpperDelta = -24` (le split descend d'une octave), `velUpperDelta = -30` (vélocité max diminue)
- Zone 2 (Strings) : `kbLowerDelta = -24` (le split suit), `velLowerDelta = +30`, `volumeDelta = +40`
- Résultat : tourner le knob pousse progressivement les strings vers le grave et augmente leur vélocité, comme un crossfade spatial.

**Mise à jour** : à chaque tick du knob, le plugin calcule les nouvelles valeurs de KB Range et Vel Range pour chaque zone impliquée, et envoie les DT1 correspondants en priorité HIGH.

### 5.6 Hybrid Layer Manager

**Responsabilité** : router les notes jouées sur le clavier simultanément vers une zone interne du RD-2000 ET vers un plugin VST sur une piste DAW externe.

**Architecture** :

```
Note On/Off entrant (depuis le clavier du RD-2000, via MidiInput)
    → Plugin reçoit la note
    → Pour chaque HybridLayer actif dans la scène courante :
        → Si note dans KB Range ET vel dans Vel Range de la zone :
            → Envoyer note vers RD-2000 sur le canal de la zone interne (via MidiOutput USB)
            → Envoyer note vers canal DAW du plugin VST associé (via JUCE MidiOutput virtuel)
```

**Note** : en mode hybride, le plugin doit opérer en mode "local off" pour les zones hybridées — il intercepte les notes et les renvoie explicitement. Cela nécessite que le RD-2000 soit configuré pour que la zone hybridée n'envoie pas elle-même les notes (désactivation du zone switch ou du canal).

**Configuration** :

```cpp
struct HybridLayer {
    int     zoneIndex;         // zone interne RD-2000
    float   hwVolumeProportion; // 0.0–1.0
    float   vstVolumeProportion;// 0.0–1.0
    int     vstMidiChannel;    // canal vers le DAW
    bool    velocityCrossfade; // si true, utilise VelocityCrossfader
    // optionnel : VelocityCrossfader
};
```

### 5.7 Program Librarian

**Responsabilité** : gérer une bibliothèque de programmes — dump SysEx, import/export fichiers `.rd2k`, lecture partielle de fichiers `.rds`.

**Opérations** :
- `dumpCurrentProgram()` → lit Program Temporary → JSON
- `restoreProgram(json)` → écrit JSON → Program Temporary via DT1
- `saveToLibrary(program)` → stocke en fichier local
- `importFromRDS(filepath)` → lit fichier RDS, extrait les noms et les blocs de programmes (lecture seule, pas d'écriture RDS car checksum 16-bit non documenté)
- `exportAsRDS(programs[])` → **non implémenté en MVP** (risque de RDS invalide)

**Format RDS — ce qui est connu** :
- Taille totale : 2 041 304 bytes pour le RD-2000
- Blocs de 5 090 bytes par programme
- Noms encodés en ASCII 7 bits packés (16 chars → 14 bytes)
- Checksum par bloc (somme des bytes = 0 mod 256)
- Checksum global 16 bits en fin de fichier (algorithme inconnu)

**Stratégie** : le librarian peut **lire** les noms et les blocs de programmes depuis un RDS, les exposer dans l'UI, et les envoyer au RD-2000 via SysEx DT1 (transcription du bloc compressé vers format SysEx nibblé). L'écriture dans le RDS lui-même est désactivée en MVP.

### 5.8 Audio USB Router

**Responsabilité** : contrôler le routing audio USB du RD-2000 via SysEx.

**Paramètres exposés** :

| Offset SysEx | Paramètre | Plage | Rôle dans le plugin |
|---|---|---|---|
| `00 00 00 17` | USB Audio Input Switch | 0–1 | Active/coupe le retour DAW→RD-2000 |
| `00 00 00 18` | USB Audio Input Volume | 0–127 | Niveau du retour DAW |
| `00 00 00 19` | USB Audio Output Switch | 0–1 | Active/coupe RD-2000→DAW |
| `00 00 00 1A` | USB Audio Output Volume | 0–127 | Niveau envoi vers DAW |
| `00 00 00 1B` | USB Audio In/Out Select | 0–1 | Direction dominante |
| `00 00 00 1C` | USB Audio Output Assign | 0–1 | Route vers MAIN ou SUB OUT |
| `00 00 00 1D` | USB Memory Player Output | 0–1 | Route backing tracks vers MAIN ou SUB |

**Cas d'usage scénarisé** :
- Scène "Studio" : USB Output ON (volume 100), USB Input ON (volume 80)
- Scène "Live solo" : USB Output ON (volume 127), USB Input OFF
- Scène "Playback + Piano" : USB Input ON (volume 60), USB Memory Player → SUB (séparé des moniteurs)

Chaque scène peut stocker ses propres valeurs USB Override, appliquées au changement de scène.

---

## 6. Architecture globale du backend

### 6.1 Diagramme des composants

```
┌──────────────────────────────────────────────────────────────────┐
│                        Plugin Processor                          │
│                   (juce::AudioProcessor)                         │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │   Program   │  │    Scene     │  │   Macro/Split           │ │
│  │  Dump Mgr  │  │   Manager    │  │   Engine                │ │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘ │
│         │                │                       │               │
│         └────────────────┴───────────────────────┘               │
│                          │                                       │
│                ┌─────────▼──────────┐                            │
│                │  State Repository  │  ← source of truth         │
│                │  (in-memory model) │                            │
│                └─────────┬──────────┘                            │
│                          │                                       │
│                ┌─────────▼──────────┐                            │
│                │   SysEx Transaction│                            │
│                │   Manager          │                            │
│                └─────────┬──────────┘                            │
│                          │                                       │
│  ┌─────────────┐  ┌──────▼───────┐  ┌─────────────────────────┐ │
│  │  MIDI Input │  │ MIDI Output  │  │   VST MIDI Output       │ │
│  │  (from RD) │  │ (to RD-2000) │  │   (to DAW tracks)       │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Morph Engine (timer thread ~60Hz)             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │            State Serializer (JSON ↔ Model)                 │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
      ┌───────▼───┐ ┌─────▼─────┐ ┌──▼──────┐
      │ RD-2000   │ │ DAW Host  │ │  File   │
      │ (USB MIDI)│ │ (VST3 API)│ │ System  │
      └───────────┘ └───────────┘ └─────────┘
```

### 6.2 Threading model

| Thread | Rôle | Contraintes |
|--------|------|-------------|
| **Audio thread** (RT) | `processBlock()` — gère les MIDI events entrants/sortants | Pas d'allocation mémoire, pas de lock mutex, pas d'I/O |
| **Timer thread** (20ms) | SysEx Transaction Manager, Morph Engine tick | Lock-free queue vers audio thread |
| **UI thread** | Rendu JUCE Component, édition paramètres | Peut alloc, peut lock |
| **Background thread** | Dump complet (RQ1 batch), sérialisation JSON, I/O fichiers | Pool géré par juce::ThreadPool |

**Communication entre threads** : `juce::AbstractFifo` pour la queue SysEx (UI → timer → audio), `std::atomic` pour les valeurs temps réel.

### 6.3 Gestion des paramètres VST3

Le plugin expose ses paramètres internes à l'hôte VST3 via `juce::AudioProcessorParameter`. **Seuls les paramètres pertinents pour l'automation DAW sont exposés** — pas les 300+ paramètres SysEx.

Paramètres exposés à l'hôte (automatable) :

```
Scene Index (0–N)
Scene Morph Progress (0.0–1.0) — writable pour automation
USB Input Volume (0–127)
USB Output Volume (0–127)
Master Volume (0–127)
MacroKnob 1–9 (0–127 chacun)
Program Tempo (5–300 BPM)
```

Tous les autres paramètres (EQ, compresseur, zones) sont gérés en interne et ne sont pas exposés comme paramètres VST3 pour éviter la pollution de l'hôte.

---

## 7. Gestion de l'état et synchronisation bidirectionnelle

### 7.1 Sources de vérité

Le plugin maintient deux états :

- **`hwState`** : dernier état connu du hardware (mis à jour à chaque RQ1 reçu ou DT1 envoyé)
- **`editState`** : état en cours d'édition dans l'UI (peut diverger temporairement)

À l'ouverture, `editState = hwState` (après le dump initial). Chaque modification dans l'UI met à jour `editState` ET envoie un DT1 vers le hardware, qui met à jour `hwState` en cas de succès.

### 7.2 Détection de désynchronisation

Le plugin détecte les modifications faites directement sur le hardware (knobs, menus) via :
- **Program Change entrant** : indique que l'utilisateur a changé de preset sur le hardware → déclenche un re-dump complet
- **Active Sensing** : si le signal est perdu pendant > 420 ms → warning "Device disconnected" dans l'UI
- **Bouton "Verify"** (UI) : déclenche un RQ1 partiel sur les paramètres critiques et compare avec l'`editState`

### 7.3 Stratégie de conflit

Si une divergence est détectée entre `hwState` et `editState` (causée par une modification hardware pendant une session plugin) :

```
Conflit détecté → Dialog UI :
  [Garder plugin]  → DT1 du editState vers hardware
  [Garder hardware] → RQ1 complet → editState = hwState
  [Voir le diff]   → Afficher le diff paramètre par paramètre
```

### 7.4 Persistance des paramètres VST3

JUCE gère la sérialisation de l'état du plugin via `getStateInformation()` / `setStateInformation()`. Le plugin sérialise :
- L'`editState` complet (JSON, ~50 KB max)
- La liste des scènes (JSON)
- La configuration des MacroKnobs (JSON)
- Les métadonnées de session

Ce state est embarqué dans le fichier de projet DAW (`.als` Ableton, `.bwproject` Bitwig, `.logicx` Logic). La session RD-2000 suit donc le projet DAW automatiquement.

---

## 8. Intégration VST3 et DAW

### 8.1 MIDI I/O déclaré

Le plugin déclare en VST3 :
- **MIDI Input** : reçoit les notes et CC du clavier RD-2000 (via USB MIDI)
- **MIDI Output** : envoie les SysEx et notes vers le RD-2000
- **MIDI Output additionnel** : envoie les notes des Hybrid Layers vers les pistes DAW

Dans JUCE, le plugin est déclaré avec `wantsMidiInput = true` et `producesMidiOutput = true`.

### 8.2 Song Map — intégration timeline DAW

Le plugin écoute les messages MIDI Clock (`0xF8`) et Song Position Pointer (SPP) entrants depuis l'hôte. Une Song Map est une liste ordonnée de `CuePoint` :

```cpp
struct CuePoint {
    int    sppPosition;   // en MIDI beats (1 beat = 6 clocks)
    int    sceneIndex;    // scène à activer
    float  morphDuration; // 0 = instantané
};
```

Le plugin maintient un compteur de clocks MIDI et, quand un SPP correspond à un CuePoint, déclenche `sceneManager.activateScene(cuePoint.sceneIndex)`.

**Ableton** : les Scene changes d'Ableton peuvent être mappés à des CuePoints via l'automation du paramètre "Scene Index" exposé en VST3.

**Bitwig** : idem via l'automation de piste.

### 8.3 Synchronisation Program Change

Quand l'hôte envoie un Program Change au plugin (via MIDI), le plugin l'interprète comme un changement de scène : `scene = PC value`. Permet de piloter les scènes depuis n'importe quel séquenceur externe ou contrôleur de scène.

---

## 9. Audio USB — routing pilotable

### 9.1 Scénarios de routing

Le RD-2000 fonctionne comme une interface audio 2 in / 2 out. Le plugin pilote le routing via les 7 paramètres SysEx identifiés.

**Scénario A — Studio, retour DAW dans le RD** :
```
DAW plugins → USB Audio Input (ON, volume 80) → MAIN OUT (XLR) → Monitors
RD-2000 clavier → USB Audio Output (ON, volume 100) → DAW tracks
```

**Scénario B — Live, clavier seul** :
```
RD-2000 clavier → USB Audio Output (ON, volume 127) → DAW (enregistrement)
USB Audio Input (OFF)
```

**Scénario C — Backing track séparé** :
```
USB Memory Player (backing track) → SUB OUT → Retour casque musiciens
RD-2000 clavier → MAIN OUT → Façade
```

### 9.2 Implémentation

Chaque scène peut stocker un `AudioUSBConfig` override. À l'activation de la scène, si `usbOverrideEnabled = true`, le plugin envoie les 7 DT1 correspondants en priorité HIGH après le Program Change.

```cpp
void AudioUSBRouter::applyConfig(const AudioUSBConfig& config) {
    auto sendParam = [&](uint8_t offset, uint8_t value) {
        txManager_.enqueue(
            buildDT1(Addresses::sysCommonParam(offset), {value}),
            Priority::HIGH
        );
    };
    sendParam(0x17, config.inputSwitch ? 1 : 0);
    sendParam(0x18, config.inputVolume);
    sendParam(0x19, config.outputSwitch ? 1 : 0);
    sendParam(0x1A, config.outputVolume);
    sendParam(0x1B, config.inOutSelect);
    sendParam(0x1C, config.outputAssign);
    sendParam(0x1D, config.memPlayerAssign);
}
```

---

## 10. API locale et intégration agent IA / MCP

### 10.1 Motivation et vision

Le RD-2000, avec ses 8 zones, ses centaines de paramètres, ses 200 programmes, et ses possibilités de morphing et de macro-modulation, est un instrument d'une richesse qui dépasse ce qu'un humain peut explorer exhaustivement en temps réel. Un agent IA disposant d'une connaissance musicale et d'un accès programmatique à l'instrument peut :

- **Composer des structures de layers** complexes à partir d'une description verbale ("crée-moi un pad chaud pour une ballade jazz, avec un string doux en haut du clavier et un rhodes léger en crossfade sur les aigus")
- **Optimiser le voicing** d'un preset par rapport à un style ou un contexte
- **Générer des scènes de setlist** à partir d'une liste de morceaux
- **Suggérer des macros** cohérentes avec le matériau sonore en place
- **Explorer l'espace de paramètres** (EQ, compresseur, voicing piano) de façon systématique, à la façon d'un sound designer qui teste des combinaisons

Cette couche API est conçue comme un **MCP Server embarqué** dans le plugin, accessible localement. Elle est la même couche qu'un outil comme Claude Code pourrait utiliser pour piloter le plugin depuis le terminal, ou qu'une interface web embarquée pourrait consommer.

### 10.2 Architecture de l'API

Le plugin embarque, dans sa version Standalone (et optionnellement en VST3 via processus séparé), un **serveur HTTP local** sur `localhost` avec deux interfaces complémentaires :

```
┌─────────────────────────────────────────────────────────────┐
│                    Plugin (Standalone / VST3)                │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API Server (localhost)                  │   │
│  │                                                      │   │
│  │   REST HTTP   ws://localhost:7842/stream             │   │
│  │   localhost:7842/api/v1/...                          │   │
│  │                                                      │   │
│  │   ┌──────────────┐    ┌────────────────────────────┐ │   │
│  │   │  REST Router │    │  WebSocket Event Bus       │ │   │
│  │   │  (read/write)│    │  (état en temps réel)      │ │   │
│  │   └──────┬───────┘    └───────────────┬────────────┘ │   │
│  │          │                            │              │   │
│  │          └────────────┬───────────────┘              │   │
│  │                       │                              │   │
│  │            ┌──────────▼───────────┐                  │   │
│  │            │   State Repository   │                  │   │
│  │            │   (source of truth)  │                  │   │
│  │            └──────────────────────┘                  │   │
│  │                                                      │   │
│  │   ┌──────────────────────────────────────────────┐   │   │
│  │   │         MCP Server (stdio transport)         │   │   │
│  │   │   Expose les mêmes capacités que REST        │   │   │
│  │   │   + tools structurés pour agents LLM         │   │   │
│  │   └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌───────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ MIDI/SysEx    │  │  Scene/Program │  │  Morph Engine │  │
│  │ Layer         │  │  Manager       │  │               │  │
│  └───────────────┘  └────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
          ▲                    ▲
          │                    │
┌─────────┴──────┐   ┌─────────┴──────────────────────────┐
│  Claude Code   │   │  Agent / LLM (via HTTP ou MCP)     │
│  (CLI local)   │   │  Anthropic API, Ollama, etc.        │
└────────────────┘   └────────────────────────────────────┘
```

### 10.3 Choix du port et sécurité

- **Port** : `7842` (configurable dans les settings du plugin)
- **Bind** : `127.0.0.1` uniquement — jamais exposé sur le réseau
- **Auth** : token API local généré à l'installation, stocké dans le keychain OS (macOS Keychain / Windows Credential Store). Header `Authorization: Bearer <token>` requis sur toutes les requêtes.
- **CORS** : autorisé pour `localhost` uniquement (pour les clients web locaux éventuels)

> Pourquoi ne pas exposer sur le réseau ? Le plugin a un accès direct au hardware audio d'un musicien en performance. Une exposition réseau serait un vecteur de perturbation de scène inacceptable.

### 10.4 API REST — endpoints complets

#### État global

```
GET  /api/v1/status
→ { connected: bool, firmware: string, deviceId: int, 
    activeScene: int, programName: string }

GET  /api/v1/state
→ Dump JSON complet de l'état courant (System + Program + Scenes)

POST /api/v1/state/sync
→ Déclenche un re-dump RQ1 complet depuis le hardware
```

#### Zones internes (8 layers)

```
GET  /api/v1/zones
→ [ { index, active, volume, pan, kbRange, velRange, tone, ... } × 8 ]

GET  /api/v1/zones/:index
→ Paramètres complets d'une zone

PATCH /api/v1/zones/:index
Body: { volume?: int, pan?: int, kbRangeLower?: int, kbRangeUpper?: int,
        velRangeLower?: int, velRangeUpper?: int, zoneSwitch?: bool,
        cutoffOffset?: int, resonanceOffset?: int, ... }
→ Applique les changements via SysEx DT1 en temps réel

POST /api/v1/zones/:index/tone
Body: { bankMSB: int, bankLSB: int, programChange: int }
→ Change le tone de la zone

POST /api/v1/zones/swap
Body: { from: int, to: int }
→ Échange deux zones (RQ1 + DT1)

POST /api/v1/zones/layout
Body: { layout: "piano_solo" | "split_bass_pad" | "organ_strings" | ... }
→ Smart Init : applique un archétype de layout sur les 8 zones
```

#### Scènes

```
GET  /api/v1/scenes
→ [ { index, name, color, programIndex, morphDuration } ]

GET  /api/v1/scenes/:index
→ Détail complet d'une scène

POST /api/v1/scenes
Body: { name: string, color?: string, fromCurrent?: bool }
→ Crée une nouvelle scène (optionnellement depuis l'état courant)

PATCH /api/v1/scenes/:index
Body: { name?, color?, morphDuration?, morphCurve? }

DELETE /api/v1/scenes/:index

POST /api/v1/scenes/:index/activate
Body: { morphFrom?: int }  ← optionnel : morphe depuis une autre scène
→ Active la scène, déclenche le morph si configuré

POST /api/v1/scenes/:index/snapshot
→ Capture l'état hardware courant dans la scène

POST /api/v1/scenes/reorder
Body: { order: [int] }  ← liste des indices dans le nouvel ordre
```

#### EQ et Compresseur

```
GET  /api/v1/eq
→ { switch: bool, inputGain: int, bands: [ { freq, gain, q? } × 5 ] }

PATCH /api/v1/eq
Body: { switch?: bool, inputGain?: int, bands?: [...] }
→ Applique en temps réel

GET  /api/v1/compressor
→ { switch: bool, bands: [ { attack, release, threshold, ratio, level } × 3 ],
    splitFreqLow: int, splitFreqHigh: int }

PATCH /api/v1/compressor
Body: { switch?: bool, bands?: [...], splitFreqLow?: int, ... }
```

#### Macro Knobs

```
GET  /api/v1/macros
→ [ { index, name, hwAssign, destinations: [...] } × 9 ]

PATCH /api/v1/macros/:index
Body: { name?: string, destinations?: [ { type, zoneIndex, paramOffset, 
         scale, offset, curve, minValue, maxValue } ] }

POST /api/v1/macros/:index/trigger
Body: { value: int }  ← 0–127
→ Simule un mouvement du macro knob (utile pour les agents)
```

#### Morph

```
POST /api/v1/morph
Body: { fromScene: int, toScene: int, durationMs: int, curve: string }
→ Déclenche un morph entre deux scènes

GET  /api/v1/morph/status
→ { active: bool, progress: float, fromScene: int, toScene: int }

DELETE /api/v1/morph
→ Arrête le morph en cours (fige à la position actuelle)
```

#### Bibliothèque de programmes

```
GET  /api/v1/programs
→ [ { index, name, bank } × 200 ]

GET  /api/v1/programs/:index
→ Dump JSON complet d'un programme

POST /api/v1/programs/:index/activate
→ Charge le programme sur le hardware

POST /api/v1/programs/save
Body: { name: string }
→ Sauvegarde l'état courant comme nouveau programme dans la bibliothèque

GET  /api/v1/programs/templates
→ Liste des Layer Templates disponibles

POST /api/v1/programs/templates/:id/apply
Body: { zoneIndex: int }
→ Applique un template à une zone spécifique
```

#### Piano Voicing

```
GET  /api/v1/voicing
→ { stringResonance, damperResonance, hammerNoise, lid, cabinetResonance,
    soundBoardResonator, duplex, keyOffResonance, notes: [ val × 128 ] }

PATCH /api/v1/voicing
Body: { stringResonance?: int, lid?: int, ... }

PATCH /api/v1/voicing/notes
Body: { notes: [ { noteIndex: int, tuning?: int, level?: int, character?: int } ] }
→ Édition granulaire note par note (Individual Note Voicing)
```

#### Audio USB

```
GET  /api/v1/audio-usb
→ { inputSwitch, inputVolume, outputSwitch, outputVolume,
    inOutSelect, outputAssign, memPlayerAssign }

PATCH /api/v1/audio-usb
Body: { inputSwitch?: bool, inputVolume?: int, ... }
```

#### WebSocket — événements temps réel

```
ws://localhost:7842/stream

Messages émis par le plugin :
{ type: "param_changed", address: "0x10002000", value: 80 }
{ type: "scene_activated", sceneIndex: 3 }
{ type: "morph_progress", progress: 0.45 }
{ type: "device_connected", firmware: "2.00" }
{ type: "device_disconnected" }
{ type: "program_changed", programIndex: 12, programName: "My Rhodes" }
{ type: "hw_sync_complete" }

Messages acceptés par le plugin (depuis client WS) :
{ type: "subscribe", topics: ["params", "scenes", "morph"] }
{ type: "param_set", address: "0x10002000", value: 80 }
```

### 10.5 MCP Server — tools pour agents LLM

Le plugin expose un **MCP Server** accessible en stdio (pour Claude Code) ou en SSE sur `localhost:7843`. Il enveloppe l'API REST en tools structurés avec des descriptions riches qui permettent à un LLM de comprendre le contexte musical de chaque action.

#### Déclaration des tools MCP

```json
{
  "name": "rd2000_get_state",
  "description": "Lit l'état complet du RD-2000 : les 8 zones actives avec leurs sons assignés, les plages de clavier, les niveaux, l'EQ, le compresseur, et la scène active. À appeler en premier pour connaître le contexte avant toute modification.",
  "inputSchema": { "type": "object", "properties": {} }
}

{
  "name": "rd2000_set_zone",
  "description": "Configure une zone interne du RD-2000. Chaque zone est un layer sonore indépendant. Les 8 zones peuvent être actives simultanément, avec des plages de clavier et de vélocité qui peuvent se superposer (layers) ou se succéder (splits). Volume : 0–127 (64 = neutre). Pan : 0 (gauche) – 64 (centre) – 127 (droite). kbRangeLower et kbRangeUpper : numéros MIDI de note (21=A0, 60=C4, 108=C8).",
  "inputSchema": {
    "type": "object",
    "required": ["zoneIndex"],
    "properties": {
      "zoneIndex":     { "type": "integer", "minimum": 0, "maximum": 7 },
      "zoneSwitch":    { "type": "boolean" },
      "volume":        { "type": "integer", "minimum": 0, "maximum": 127 },
      "pan":           { "type": "integer", "minimum": 0, "maximum": 127 },
      "kbRangeLower":  { "type": "integer", "minimum": 21, "maximum": 108 },
      "kbRangeUpper":  { "type": "integer", "minimum": 21, "maximum": 108 },
      "velRangeLower": { "type": "integer", "minimum": 1,  "maximum": 127 },
      "velRangeUpper": { "type": "integer", "minimum": 1,  "maximum": 127 },
      "cutoffOffset":  { "type": "integer", "minimum": -64, "maximum": 63 },
      "resonanceOffset":{"type": "integer", "minimum": -64, "maximum": 63 },
      "reverbSend":    { "type": "integer", "minimum": 0, "maximum": 127 },
      "delaySend":     { "type": "integer", "minimum": 0, "maximum": 127 }
    }
  }
}

{
  "name": "rd2000_set_tone",
  "description": "Assigne un son (tone) à une zone. Le RD-2000 dispose de plus de 1100 sons répartis en catégories : CONCERT (grands pianos acoustiques), STUDIO (pianos studio), VINTAGE (pianos anciens, RD-1000, MKS-20), MODERN (pianos contemporains), CLAV (clavinet, clavecin), ORGAN (orgues Hammond et classiques), STRINGS (cordes), PAD/CHOIR (pads et chœurs), BASS (basses), OTHER (synthés, guitares, effets). Les sons de piano acoustique utilisent le moteur V-Piano (modélisation physique). Les autres utilisent SuperNATURAL (hybrid sampling). Utiliser bankMSB=85, bankLSB=64 pour les presets factory standard.",
  "inputSchema": {
    "type": "object",
    "required": ["zoneIndex", "programChange"],
    "properties": {
      "zoneIndex":     { "type": "integer", "minimum": 0, "maximum": 7 },
      "bankMSB":       { "type": "integer", "minimum": 0, "maximum": 127 },
      "bankLSB":       { "type": "integer", "minimum": 0, "maximum": 127 },
      "programChange": { "type": "integer", "minimum": 0, "maximum": 127 }
    }
  }
}

{
  "name": "rd2000_create_scene",
  "description": "Crée une nouvelle scène à partir de l'état courant du RD-2000. Une scène encapsule : la configuration des 8 zones, l'EQ, le compresseur, le routing audio USB, et les macro-knobs. Les scènes peuvent être activées instantanément ou avec un morph (transition progressive).",
  "inputSchema": {
    "type": "object",
    "required": ["name"],
    "properties": {
      "name":         { "type": "string", "maxLength": 64 },
      "color":        { "type": "string", "pattern": "^#[0-9A-Fa-f]{6}$" },
      "fromCurrent":  { "type": "boolean", "default": true }
    }
  }
}

{
  "name": "rd2000_morph_scenes",
  "description": "Déclenche une transition progressive (morph) entre deux scènes. Tous les paramètres continus (volumes, EQ, envois d'effets, cutoff, résonance) sont interpolés sur la durée spécifiée. Les paramètres discrets (changements de son, switch de zone) basculent instantanément. Utile pour créer des transitions musicalement douces entre deux configurations sonores.",
  "inputSchema": {
    "type": "object",
    "required": ["fromScene", "toScene"],
    "properties": {
      "fromScene":   { "type": "integer" },
      "toScene":     { "type": "integer" },
      "durationMs":  { "type": "number", "minimum": 100, "maximum": 10000, "default": 2000 },
      "curve":       { "type": "string", "enum": ["linear", "ease_in", "ease_out", "ease_inout"], "default": "ease_inout" }
    }
  }
}

{
  "name": "rd2000_set_eq",
  "description": "Configure l'égaliseur 5 bandes paramétrique du programme courant. Les gains sont en dB (−12.0 à +12.0). Les bandes : LOW (fréquence fixe shelf), MID_LOW / MID_MID / MID_HIGH (paramétriques avec facteur Q), HIGH (fréquence fixe shelf). Toutes les modifications sont appliquées en temps réel sur le hardware.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "switch":     { "type": "boolean" },
      "inputGain":  { "type": "number", "minimum": -15, "maximum": 15 },
      "bands": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "band":  { "type": "string", "enum": ["low", "mid_low", "mid_mid", "mid_high", "high"] },
            "gain":  { "type": "number", "minimum": -12, "maximum": 12 },
            "q":     { "type": "number", "enum": [0.5, 1.0, 2.0, 4.0, 8.0] }
          }
        }
      }
    }
  }
}

{
  "name": "rd2000_set_layout",
  "description": "Applique un archétype de layout sonore sur les 8 zones. Réinitialise les zones selon des splits et layers prédéfinis musicalement cohérents. Idéal comme point de départ avant des ajustements fins.",
  "inputSchema": {
    "type": "object",
    "required": ["layout"],
    "properties": {
      "layout": {
        "type": "string",
        "enum": [
          "piano_solo",           // Zone 1 : piano full range
          "split_bass_pad",       // Z1 basse (A0–B2), Z2 pad (C3–C8)
          "organ_strings",        // Z1 orgue (C2–C8), Z2 strings (C4–C8, vel 80–127)
          "rhodes_chorus",        // Z1 Rhodes (full), Z2 écho léger en layer
          "piano_strings_layer",  // Z1 piano, Z2 strings douce en fondu velocity
          "piano_plus_bass",      // Z1 piano (C3–C8), Z2 basse (A0–B2)
          "grand_ensemble",       // Z1 piano, Z2 strings, Z3 pad, Z4 basse
          "blank"                 // Toutes les zones à zéro
        ]
      }
    }
  }
}

{
  "name": "rd2000_set_macro",
  "description": "Configure un macro-knob : associe un contrôleur physique du RD-2000 (knob A1–A9, wheels, slider) à plusieurs destinations de paramètres simultanées avec des scalings indépendants. Permet à un knob de contrôler par exemple la réverb de la zone 1, le cutoff de la zone 3, et le volume d'un plugin VST externe en même temps.",
  "inputSchema": {
    "type": "object",
    "required": ["macroIndex"],
    "properties": {
      "macroIndex":  { "type": "integer", "minimum": 0, "maximum": 8 },
      "name":        { "type": "string" },
      "hwAssign":    { "type": "integer", "description": "0=A1, 1=A2, ..., 8=A9, 9=Wheel1, 10=Wheel2, 11=Slider" },
      "destinations": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type":        { "type": "string", "enum": ["zone_param", "cc_to_vst", "sysex"] },
            "zoneIndex":   { "type": "integer", "minimum": 0, "maximum": 7 },
            "param":       { "type": "string", "enum": ["volume", "pan", "reverbSend", "delaySend", "cutoffOffset", "resonanceOffset", "vibratoDepth"] },
            "scale":       { "type": "number", "minimum": -1, "maximum": 1 },
            "offset":      { "type": "number" },
            "curve":       { "type": "string", "enum": ["linear", "log", "exp", "s_curve"] }
          }
        }
      }
    }
  }
}

{
  "name": "rd2000_piano_voicing",
  "description": "Ajuste les paramètres de réalisme acoustique du piano. Ces paramètres affectent la physique simulée : String Resonance (résonance des cordes sympathiques), Damper Resonance (résonance de la pédale de sustain), Hammer Noise (bruit du marteau), Key Off Resonance (résonance au relâchement), Cabinet Resonance (caisse de résonance), Lid (position du couvercle 0=fermé, 6=ouvert max).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "stringResonance":  { "type": "integer", "minimum": 0, "maximum": 10 },
      "damperResonance":  { "type": "integer", "minimum": 0, "maximum": 10 },
      "hammerNoise":      { "type": "integer", "minimum": -2, "maximum": 2 },
      "keyOffResonance":  { "type": "integer", "minimum": 0, "maximum": 10 },
      "cabinetResonance": { "type": "integer", "minimum": 0, "maximum": 10 },
      "lid":              { "type": "integer", "minimum": 0, "maximum": 6 },
      "duplex":           { "type": "integer", "minimum": 0, "maximum": 10 },
      "soundBoard":       { "type": "integer", "minimum": 0, "maximum": 4 }
    }
  }
}
```

### 10.6 Exemple de workflow agent complet

Voici un scénario concret illustrant comment Claude Code interagit avec le plugin via MCP :

```
User → Claude Code :
"Prépare-moi un son de ballade jazz : 
 piano doux avec beaucoup de réverb en bas du clavier,
 et des strings chaudes qui apparaissent progressivement 
 dans les aigus à partir de C4. Le tout très chaleureux."

Claude Code → rd2000_get_state()
← { zones: [{ active: true, tone: "Steinway D", volume: 100 }...], 
    eq: { ... }, reverb: { type: "HALL2", level: 45 } }

Claude Code → rd2000_set_layout({ layout: "blank" })
← { success: true }

Claude Code → rd2000_set_zone({
  zoneIndex: 0,
  zoneSwitch: true,
  kbRangeLower: 21,   // A0
  kbRangeUpper: 108,  // C8
  velRangeLower: 1,
  velRangeUpper: 127,
  volume: 90,
  reverbSend: 80,     // beaucoup de réverb
  cutoffOffset: -15   // légèrement sombre
})

Claude Code → rd2000_set_tone({
  zoneIndex: 0,
  bankMSB: 85, bankLSB: 64,
  programChange: 1    // Grand Piano 1 (V-Piano)
})

Claude Code → rd2000_set_zone({
  zoneIndex: 1,
  zoneSwitch: true,
  kbRangeLower: 60,   // C4 — les strings commencent ici
  kbRangeUpper: 108,
  velRangeLower: 40,  // apparaissent à partir de velocité moyenne
  velRangeUpper: 127,
  volume: 55,
  pan: 70,            // légèrement à droite
  reverbSend: 90,
  cutoffOffset: -20,  // doux et chaud
  attackTimeOffset: 15 // attaque lente
})

Claude Code → rd2000_set_tone({
  zoneIndex: 1, bankMSB: 85, bankLSB: 64, programChange: 87  // Warm Strings
})

Claude Code → rd2000_set_eq({
  switch: true,
  inputGain: 0,
  bands: [
    { band: "low",      gain: +2.0 },        // chaleur dans le bas
    { band: "mid_low",  gain: +1.5, q: 1.0 },
    { band: "mid_mid",  gain: -1.0, q: 2.0 }, // légèrement évidé au mid
    { band: "mid_high", gain: +0.5, q: 1.0 },
    { band: "high",     gain: -2.0 }          // atténuer les hautes freq
  ]
})

Claude Code → rd2000_set_macro({
  macroIndex: 0,
  name: "Présence Strings",
  hwAssign: 0,         // Knob A1
  destinations: [
    { type: "zone_param", zoneIndex: 1, param: "volume",
      scale: 0.6, offset: 0, curve: "ease_in" },
    { type: "zone_param", zoneIndex: 1, param: "reverbSend",
      scale: 0.3, offset: 0, curve: "linear" },
    { type: "zone_param", zoneIndex: 0, param: "reverbSend",
      scale: -0.2, offset: 0, curve: "linear" }  // piano moins reverb quand strings montent
  ]
})

Claude Code → rd2000_create_scene({
  name: "Ballade Jazz",
  color: "#1D9E75",
  fromCurrent: true
})

← { success: true, sceneIndex: 4 }

Claude Code → User :
"Scène 'Ballade Jazz' créée. Piano doux avec réverb Hall2 sur tout le clavier, 
 strings chaudes qui apparaissent à partir de C4 sur les velocités moyennes. 
 Le Knob A1 contrôle la présence des strings (monte leur volume et reverb, 
 baisse légèrement la reverb du piano). EQ chaud avec atténuation des hautes fréquences."
```

### 10.7 Considérations de design pour l'interopérabilité IA

#### Descriptions sémantiques riches

Chaque endpoint REST retourne, en plus des valeurs brutes, des **métadonnées sémantiques** qui aident un LLM à interpréter les données musicalement :

```json
{
  "zones": [{
    "index": 0,
    "zoneSwitch": true,
    "volume": 90,
    "tone": {
      "programChange": 1,
      "name": "Grand Piano 1",
      "engine": "V-Piano",
      "category": "CONCERT",
      "description": "Piano de concert Steinway, modélisation physique complète, polyphonie illimitée"
    },
    "kbRange": { "lower": 21, "upper": 108, "description": "Clavier complet A0–C8" },
    "velRange": { "lower": 1,  "upper": 127, "description": "Toutes velocités" },
    "_semantic": {
      "role": "melody",
      "texture": "acoustic piano",
      "register": "full"
    }
  }]
}
```

Le champ `_semantic` est écrit par le plugin à partir de règles heuristiques simples (range de notes, catégorie de tone, vélocité) et peut être enrichi par l'agent.

#### Endpoint de suggestion

```
POST /api/v1/ai/suggest
Body: {
  "intent": "Je veux un son épique pour une intro orchestrale",
  "constraints": {
    "usedZones": [0, 1],
    "style": "cinematic",
    "tempo": 120
  }
}
→ { suggestions: [ { description, zones: [...], eq: {...}, macros: [...] } ] }
```

Cet endpoint n'est pas lui-même un LLM — il utilise des règles heuristiques et/ou peut appeler l'API Anthropic en interne si une clé API est configurée dans les settings du plugin. Il retourne une liste de configurations suggérées que l'agent ou l'utilisateur peut appliquer.

#### Historique des actions (pour le contexte LLM)

```
GET /api/v1/history
→ [ { timestamp, action, params, result } × N (dernières 100 actions) ]
```

Cet historique permet à un agent de reprendre une session en comprenant ce qui a déjà été fait, sans avoir à relire tout l'état.

### 10.8 MCP Server — configuration pour Claude Code

Le plugin expose un fichier de configuration MCP à placer dans `~/.claude/mcp_servers.json` :

```json
{
  "rd2000": {
    "type": "sse",
    "url": "http://localhost:7843/mcp",
    "headers": {
      "Authorization": "Bearer ${RD2000_API_TOKEN}"
    },
    "description": "Contrôle le Roland RD-2000 via le plugin DAW. Permet de configurer les zones, les sons, l'EQ, les scènes et les transitions en temps réel."
  }
}
```

La variable `RD2000_API_TOKEN` est générée par le plugin à l'installation et stockée dans le keychain OS.

### 10.9 Implémentation technique du serveur HTTP

Le serveur HTTP est implémenté directement en C++ dans le plugin, sans dépendance lourde. Options :

| Bibliothèque | Licence | Avantages | Inconvénients |
|---|---|---|---|
| **cpp-httplib** | MIT | Header-only, légère, HTTPS optionnel | Pas de WebSocket natif (besoin d'extension) |
| **Crow** | BSD | REST + WebSocket natif, simple | Un peu plus lourde |
| **Boost.Beast** | BSL | Très complet, WebSocket robuste | Dépendance Boost entière |

**Recommandation** : `cpp-httplib` pour REST + `uWebSockets` (MIT) pour le WebSocket. Les deux sont header-only ou quasi, et facilement intégrables dans un build JUCE CMake.

Le serveur démarre dans un thread dédié (`juce::Thread`) au lancement du plugin Standalone, ou sur demande explicite en mode VST3 (bouton "Start API Server" dans les settings). Il s'arrête proprement à la fermeture.

### 10.10 Sécurité et robustesse

- **Rate limiting** : max 100 requêtes/seconde pour éviter de saturer la queue SysEx
- **Validation** : toutes les valeurs sont clampées aux plages valides avant envoi SysEx — l'agent ne peut pas envoyer de valeur illicite au hardware
- **Dry-run mode** : paramètre `?dry_run=true` sur tout endpoint → retourne ce qui serait envoyé sans l'envoyer. Permet à l'agent de vérifier sa logique avant d'agir.
- **Audit log** : toutes les actions via API sont loguées dans `~/.rd2000plugin/api_audit.log` (configurable)
- **Killswitch** : `POST /api/v1/emergency/panic` → envoie `All Sounds Off` + `Reset All Controllers` sur tous les canaux. Accessible sans token auth.

---

## 11. Roadmap de développement — phases et priorités

### Phase 0 — Fondations (4–6 semaines)

**Objectif** : projet JUCE opérationnel, connexion bidirectionnelle fonctionnelle, API skeleton.

- [ ] Setup projet CMake + JUCE 7, CI GitHub Actions (macOS + Windows)
- [ ] Détection et connexion du RD-2000 (Identity Request, Active Sensing)
- [ ] SysEx Codec complet (DT1/RQ1, checksum, nibbled data)
- [ ] SysEx Transaction Manager (queue prioritaire, throttling 20ms)
- [ ] Dump complet initial (tous les blocs RQ1)
- [ ] Modèle de données (InternalZone, ExternalZone, SystemCommon)
- [ ] Sérialisation JSON bidirectionnelle
- [ ] Tests unitaires : codec, checksum, nibbled, adresses
- [ ] **API Server skeleton** : HTTP sur port 7842, auth token, `/status`, `/state`
- [ ] **MCP Server skeleton** : transport SSE sur 7843, tool `rd2000_get_state`
- [ ] UI squelette (JUCE Component) — statut connexion, dump status, bouton "Start API"

**Livrable** : plugin standalone connecté au RD-2000, état lisible en JSON via `curl` et via Claude Code MCP.

---

### Phase 1 — MVP Core (8–10 semaines)

**Objectif** : fonctions essentielles de layers et de scènes + API complète en parallèle.

- [ ] Zone Mixer 8 layers — Volume, Pan, Sends, Zone Switch, KB Range, Vel Range
- [ ] EQ 5 bandes — curseurs + courbe de réponse dessinée en temps réel
- [ ] Compresseur 3 bandes système — tous les paramètres
- [ ] Scene Manager — create, activate, delete, reorder, snapshot
- [ ] Scene Switcher — Bank Select + SysEx overrides + Audio USB override par scène
- [ ] Program Librarian — dump JSON, restore, liste locale, import RDS (noms)
- [ ] Audio USB Router — 7 paramètres, override par scène
- [ ] Persist VST3 (getStateInformation / setStateInformation)
- [ ] Assign Controller Matrix — A1-A9, Wheels, Slider, FC1/FC2/EXT
- [ ] Tone selector par zone (browser : catégorie + numéro)
- [ ] **API REST complète** : zones, EQ, compresseur, scènes, programmes, audio-usb
- [ ] **MCP tools** : `set_zone`, `set_tone`, `set_eq`, `create_scene`, `set_layout`, `activate_scene`
- [ ] **WebSocket** : events param_changed, scene_activated, device_connected/disconnected
- [ ] **Dry-run mode** (`?dry_run=true`) sur tous les endpoints
- [ ] **Audit log** et rate limiting

**Livrable** : plugin utilisable en studio, pilotable intégralement par un agent Claude Code.

---

### Phase 2 — Workflows avancés (6–8 semaines)

**Objectif** : fonctions différenciantes pour la performance et le sound design.

- [ ] Morph Scene Engine (interpolation paramétrique, courbes, timer 60Hz)
- [ ] Dual-State A/B (delta SysEx, toggle footswitch FC1/FC2)
- [ ] Macro Knob Engine (matrice multi-destination, scaling, courbes)
- [ ] Snapshot A/B Compare
- [ ] Song Map (MIDI Clock DAW → CuePoints → activation scène)
- [ ] Smart Init — 8 archétypes musicaux prêts à l'emploi
- [ ] Zone Swap (drag & drop inter-zones)
- [ ] Layer Template Library (briques réutilisables save/load)
- [ ] **API** : `/morph`, `/macros`, `/macros/:index/trigger`, `/history`
- [ ] **MCP tools** : `morph_scenes`, `set_macro`, `set_layout` étendu
- [ ] **`/ai/suggest`** — heuristiques de configuration par intention musicale
- [ ] **WebSocket** : morph_progress, macro_triggered

**Livrable** : plugin live-ready, agent IA capable de composer des structures sonores complexes en dialogue.

---

### Phase 3 — Hybridation VST (6–8 semaines)

**Objectif** : intégration avec les instruments logiciels du DAW.

- [ ] Hybrid Layer Manager (note routing HW + VST simultané)
- [ ] Velocity Crossfader HW/VST (courbe éditable graphiquement)
- [ ] Knob Split/Layer Designer (superknob spatial, vue piano roll de zones)
- [ ] Plugin Insert Chain (vue unifiée HW + effets DAW par layer)
- [ ] MIDI Output virtuel vers DAW (JUCE IAC / loopMIDI sur Windows)
- [ ] Piano Voicing Studio (Individual Note Voicing × 128, nibbled)
- [ ] Program Librarian étendu (import RDS partiel — blocs complets)
- [ ] **API** : `/voicing`, `/voicing/notes`, `/hybrid-layers`
- [ ] **MCP tools** : `piano_voicing`, `set_hybrid_layer`, `velocity_crossfade`
- [ ] **Métadonnées sémantiques** (`_semantic`) sur tous les endpoints zones

**Livrable** : plugin hybride complet, HW + software — agent IA capable de travailler le voicing note par note et les layers VST.

---

### Phase 4 — Polish et distribution (4–6 semaines)

- [ ] UI design final (voir spécifications frontend — document séparé)
- [ ] Optimisation performances (profiling, latence, CPU)
- [ ] Documentation utilisateur (PDF + vidéos)
- [ ] **OpenAPI 3.0 spec** auto-générée depuis le code
- [ ] **Fichier `mcp_config.json`** généré automatiquement à l'installation
- [ ] Installateurs macOS (notarisation Apple) + Windows (NSIS)
- [ ] Tests beta avec utilisateurs RD-2000
- [ ] CLAP format (wrapper clap-juce-extensions)
- [ ] Support RD-2000 EX (firmware 2.x — 2 slots expansion)
- [ ] Publication optionnelle du MCP server dans un registre communautaire

---

## 12. Références techniques

### Documents Roland officiels
- `RD-2000_MIDI_Imple_eng02_W.pdf` — MIDI Implementation v1.01 (Jan 2018)
- `RD-2000_Parameter_Guide_eng01_W.pdf` — Guide des paramètres
- `RD-2000_eng04_W.pdf` — Manuel utilisateur
- `RD-2000_Sound_List_eng02_W.pdf` — Liste des sons et patterns de rythme

### Projets communautaires
- `roland-rds` (GitHub : davidlang42) — bibliothèque C# pour fichiers RDS Roland
- RD2000 Editor (Stuart Pryer, stuartpryer.co.uk) — éditeur Windows existant
- Roland Clan Forums — reverse-engineering RDS, audio USB, bugs firmware

### Frameworks audio et plugin
- JUCE 7 (juce.com) — framework plugin VST3/AU/CLAP (Proprietary/GPL)
- nlohmann/json (github.com/nlohmann/json) — JSON header-only (MIT)
- Catch2 (github.com/catchorg/Catch2) — tests unitaires (BSL-1.0)
- clap-juce-extensions (github.com/free-audio/clap-juce-extensions) — wrapper CLAP (MIT)

### Frameworks API et réseau
- cpp-httplib (github.com/yhirose/cpp-httplib) — serveur HTTP header-only (MIT)
- uWebSockets (github.com/uNetworking/uWebSockets) — WebSocket haute performance (Apache 2.0)
- MCP SDK C++ (si disponible) ou implémentation SSE manuelle selon spec MCP

### Spécifications protocole
- Roland SysEx Format : adresse 4 bytes, checksum Roland, format nibbled
- VST3 SDK (Steinberg) — ISynthesizer, IMidiMapping, IEditController
- MIDI 1.0 Detailed Specification — SysEx, Program Change, Bank Select
- Model Context Protocol spec (modelcontextprotocol.io) — tools, SSE transport
- OpenAPI 3.0 (swagger.io) — documentation de l'API REST

---

*Document en cours. Prochaine session : spécifications frontend et design system du plugin.*

*Version 0.2 — session 2026-05-15 — FLO × Claude*
