# ADR-0008: Security and Privacy

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10) |
| **Contributors** | Scott |
| **Depends On** | ADR-0001, ADR-0003, ADR-0004, ADR-0005 |

---

## 1. Context and Problem Statement

GLADyS observes user behavior through sensors (screen, audio, keyboard), learns personal preferences, and can control external devices. This creates significant privacy and security responsibilities:

- What data is collected and how long is it retained?
- How do we prevent malicious plugins from abusing access?
- How do we protect minors?
- How do we maintain user trust through transparency and control?

This ADR establishes security and privacy as foundational design principles, not afterthoughts.

---

## 2. Decision Drivers

1. **Privacy by design:** Local-first, minimize data collection
2. **Defense in depth:** Multiple security layers, fail closed
3. **User control:** Transparency, easy access to permissions
4. **Age-appropriate:** Protect minors from sensitive capabilities
5. **Extensibility:** 3rd party plugins without compromising security
6. **Performance:** Security controls must not compromise responsiveness

---

## 3. Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Local-first** | Data stays on device by default, cloud requires explicit opt-in |
| **Minimal collection** | Collect only what's needed, discard raw data after processing |
| **Fail closed** | Deny by default, require explicit permission grants |
| **Least privilege** | Plugins get minimum permissions needed |
| **Defense in depth** | Multiple security layers, any can abort |
| **Transparency** | Users can see what's collected and why |
| **User control** | Easy to find, understand, and modify permissions |

---

## 4. Data Retention

### 4.1 Tiered Memory Consolidation

Unlimited retention with consolidation to bound storage growth:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     MEMORY CONSOLIDATION TIERS                          │
│                                                                         │
│  Age: 0-7 days                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ FULL EPISODIC EVENTS                                              │ │
│  │                                                                   │ │
│  │ • Complete raw text and structured data                          │ │
│  │ • Full embedding vectors                                         │ │
│  │ • All entity references                                          │ │
│  │ • Complete salience vectors                                      │ │
│  │                                                                   │ │
│  │ Storage: ~2KB per event                                          │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼ Consolidation job (nightly)              │
│  Age: 7-30 days                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ CONSOLIDATED EVENTS                                               │ │
│  │                                                                   │ │
│  │ • Summarized text (LLM-generated)                                │ │
│  │ • Key entities preserved                                         │ │
│  │ • Embedding vectors preserved                                    │ │
│  │ • Peak salience values only                                      │ │
│  │ • Similar events merged                                          │ │
│  │                                                                   │ │
│  │ Storage: ~0.5KB per consolidated event                           │ │
│  │ Reduction: ~10:1                                                 │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼ Consolidation job (weekly)               │
│  Age: 30-180 days                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ SEMANTIC FACTS                                                    │ │
│  │                                                                   │ │
│  │ • Extracted subject-predicate-object triples                     │ │
│  │ • Entity updates and relationships                               │ │
│  │ • No raw event text                                              │ │
│  │ • No embeddings (facts are structured)                           │ │
│  │                                                                   │ │
│  │ Storage: ~0.2KB per fact                                         │ │
│  │ Reduction: ~50:1 from original                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼ Archival job (monthly)                   │
│  Age: 180+ days                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ SIGNIFICANT EVENTS + FACTS                                        │ │
│  │                                                                   │ │
│  │ Preserved indefinitely:                                          │ │
│  │ • High salience events (threat > 0.8, opportunity > 0.8)        │ │
│  │ • User-starred/bookmarked events                                 │ │
│  │ • First occurrence of entities                                   │ │
│  │ • Major user feedback (explicit positive/negative)               │ │
│  │ • All semantic facts                                             │ │
│  │ • Entity records                                                 │ │
│  │                                                                   │ │
│  │ Storage: Grows slowly (~1MB/year)                                │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Retention by Data Type

| Data Type | Retention | Storage | Notes |
|-----------|-----------|---------|-------|
| Episodic events (full) | 7 days | PostgreSQL | Then consolidated |
| Episodic events (consolidated) | 30 days | PostgreSQL | Then extracted to facts |
| Semantic facts | Unlimited | PostgreSQL | Distilled knowledge |
| Entity records | Unlimited | PostgreSQL | Canonical entities |
| User profile traits | Unlimited | PostgreSQL | Learned preferences |
| Feedback events | 180 days | PostgreSQL | Learning validation |
| Raw audio | **Never stored** | N/A | Transcription only |
| Raw images | **Never stored** | RAM only | Structured events only |
| System logs | 30 days | Files | Debugging |
| Security audit log | 1 year | Files | Compliance |

### 4.3 Configuration

```yaml
# config/retention.yaml
retention:
  episodic_events:
    full_days: 7
    consolidated_days: 30
    semantic_extraction_days: 180
    
  significant_event_thresholds:
    threat: 0.8
    opportunity: 0.8
    user_starred: true
    explicit_feedback: true
    first_entity_occurrence: true
  
  consolidation:
    schedule: "0 3 * * *"  # 3 AM daily
    batch_size: 1000
  
  system_logs:
    retention_days: 30
    max_size_mb: 500
  
  security_audit:
    retention_days: 365
    max_size_mb: 1000
```

---

## 5. Image Handling

### 5.1 Process and Discard

Images are processed in memory and immediately discarded. Only structured events are stored.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     IMAGE PROCESSING PIPELINE                           │
│                                                                         │
│  Screen/Game                                                            │
│      │                                                                  │
│      ▼                                                                  │
│  ┌─────────────────┐                                                    │
│  │ Capture (RAM)   │  Image exists only in memory                       │
│  │ Never to disk   │  Written to shared memory region                   │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                    │
│  │ Deduplication   │  pHash + histogram comparison                      │
│  │ (optional)      │  Skip if too similar to previous                   │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                    │
│  │ Vision Model    │  Gemma 3 / LLaVA (local GPU)                       │
│  │                 │  Extracts structured information                   │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Structured Event (STORED)                                        │   │
│  │                                                                  │   │
│  │ {                                                                │   │
│  │   "source": "minecraft-visual-sensor",                           │   │
│  │   "raw_text": "Player 'xX_Slayer_Xx' in diamond armor,           │   │
│  │                approaching from east, distance ~30 blocks",      │   │
│  │   "structured": {                                                │   │
│  │     "entities": ["xX_Slayer_Xx"],                                │   │
│  │     "threat_indicators": ["diamond_armor", "enchanted_weapon"],  │   │
│  │     "position": {"x": 150, "y": 64, "z": -200},                  │   │
│  │     "movement": "approaching"                                    │   │
│  │   }                                                              │   │
│  │ }                                                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐                                                    │
│  │ Image Discarded │  Overwritten in ring buffer                        │
│  │ (Zero storage)  │  No persistence ever                               │
│  └─────────────────┘                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Optional Temporary Buffer

Sensors may request a RAM-only rolling buffer for motion detection and context:

| Constraint | Value | Rationale |
|------------|-------|-----------|
| Max duration | 60 seconds | Enough for context, not surveillance |
| Max frames | 120 frames | Reasonable memory use |
| Storage | RAM only, never disk | Privacy |
| Cleared on | Sensor stop, system shutdown | No persistence |
| Permission | Must be declared in manifest | Explicit opt-in |

**Manifest declaration:**

```yaml
sensor:
  permissions:
    screen:
      type: window
      window_match:
        process: "javaw.exe"
      
      buffer:
        enabled: true
        max_seconds: 30
        max_frames: 60
        justification: "Frame comparison for motion detection"
```

### 5.3 Frame Deduplication

Discard frames too similar to previous to maximize buffer utility:

```python
class FrameDeduplicator:
    """Discard similar frames using pHash + histogram."""
    
    def __init__(
        self,
        phash_threshold: int = 8,           # Hamming distance
        histogram_threshold: float = 0.05    # Chi-squared distance
    ):
        self.phash_threshold = phash_threshold
        self.histogram_threshold = histogram_threshold
    
    def should_keep(self, frame: Image) -> bool:
        """Keep frame if structurally OR colorimetrically different."""
        current_phash = imagehash.phash(frame)
        current_histogram = self._compute_histogram(frame)
        
        if self.last_phash is None:
            self._update_last(current_phash, current_histogram)
            return True
        
        # Check structural change (pHash)
        phash_changed = (current_phash - self.last_phash) >= self.phash_threshold
        
        # Check color/lighting change (histogram)
        hist_changed = self._histogram_distance(
            current_histogram, 
            self.last_histogram
        ) >= self.histogram_threshold
        
        if phash_changed or hist_changed:
            self._update_last(current_phash, current_histogram)
            return True
        
        return False  # Too similar, discard
```

---

## 6. Audio Handling

### 6.1 Transcription Only

Raw audio is never stored. Only transcriptions are persisted.

| Stage | Data | Stored? |
|-------|------|---------|
| Microphone capture | Raw PCM audio | ❌ RAM only |
| Voice activity detection | Audio segments | ❌ RAM only |
| Whisper transcription | Text | ✓ As event |
| Post-processing | Cleaned text | ✓ As event |

### 6.2 Audio Permission Tiers

| Permission | Description | Age | Trust |
|------------|-------------|-----|-------|
| `audio.push_to_talk` | Microphone when user activates | 13+ | Any |
| `audio.voice_activation` | Listen for wake word | 16+ | Signed |
| `audio.always_on` | Continuous listening | 18+ | 1st party |

---

## 7. Cloud API Policy

### 7.1 Local-First Default

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PROCESSING MODES                                    │
│                                                                         │
│  PRIVACY MODE (Default)                                                 │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  • All processing local (Ollama, llama.cpp)                      │ │
│  │  • No data leaves device                                         │ │
│  │  • No network calls to AI providers                              │ │
│  │  • Full privacy, may have reduced model capability               │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  CLOUD MODE (Explicit opt-in)                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  ⚠️  Warning shown on enable:                                     │ │
│  │                                                                   │ │
│  │  "Cloud mode sends conversation data to external AI providers.   │ │
│  │   Data sent: prompts, context, conversation history.             │ │
│  │   Data NOT sent: raw audio, raw images.                          │ │
│  │                                                                   │ │
│  │   Providers: Groq, Azure OpenAI, Anthropic                       │ │
│  │   See their privacy policies for data handling."                 │ │
│  │                                                                   │ │
│  │  [Enable Cloud Mode]  [Stay Local]                               │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  DEVELOPMENT MODE                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  • Cloud APIs enabled by default for convenience                 │ │
│  │  • Clear indicator in UI: "DEV MODE - Cloud Active"              │ │
│  │  • User informed at first launch                                 │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Configuration

```yaml
# config/privacy.yaml
privacy:
  mode: local  # local | cloud | development
  
  cloud:
    enabled: false
    user_acknowledged_warning: false
    providers:
      - groq
      - azure_openai
    
    # What gets sent
    send_prompts: true
    send_context: true
    send_conversation_history: true
    
    # What never gets sent
    send_raw_audio: false   # Always false, not configurable
    send_raw_images: false  # Always false, not configurable
```

---

## 8. Age Restrictions

### 8.1 Age Tiers

| Age | 1st Party Sensors | Signed 3rd Party | Unsigned 3rd Party | High-Risk Permissions |
|-----|-------------------|------------------|--------------------|-----------------------|
| **13-15** | Game sensors only | ❌ | ❌ | Push-to-talk only |
| **16-17** | All 1st party | Game sensors only | ❌ | Moderate (see below) |
| **18+** | All | All | Safe permissions only | All (with consent) |

### 8.2 Permission Age Requirements

| Permission | 13-15 | 16-17 | 18+ |
|------------|-------|-------|-----|
| `screen.game` | ✓ | ✓ | ✓ |
| `screen.window` | ❌ | ✓ | ✓ |
| `screen.full` | ❌ | ❌ | ✓ |
| `audio.push_to_talk` | ✓ | ✓ | ✓ |
| `audio.voice_activation` | ❌ | ✓ | ✓ |
| `audio.always_on` | ❌ | ❌ | ✓ |
| `keyboard.read` | ❌ | ❌ | ✓ |
| `file.read` (game files) | ✓ | ✓ | ✓ |
| `file.read` (scoped) | ❌ | ✓ | ✓ |
| `game.mod.read` | ✓ | ✓ | ✓ |
| `game.mod.write` | ❌ | ✓ | ✓ |
| `iot.sensor` | ❌ | ✓ | ✓ |
| `iot.control` | ❌ | ❌ | ✓ |

### 8.3 Implementation

```python
def check_age_permission(user_age: int, permission: str) -> bool:
    """Check if user age permits this permission."""
    AGE_REQUIREMENTS = {
        "screen.full": 18,
        "screen.window": 16,
        "screen.game": 13,
        "audio.always_on": 18,
        "audio.voice_activation": 16,
        "audio.push_to_talk": 13,
        "keyboard.read": 18,
        "iot.control": 18,
        # ... etc
    }
    
    min_age = AGE_REQUIREMENTS.get(permission, 18)  # Default to 18
    return user_age >= min_age
```

---

## 9. Permission System

### 9.1 Permission Registry

```yaml
# config/permissions.yaml
permissions:
  # ═══════════════════════════════════════════════════════════════════
  # SCREEN / VISUAL
  # ═══════════════════════════════════════════════════════════════════
  
  screen.full:
    description: "Capture entire screen"
    risk: critical
    min_age: 18
    requires: [first_party]
  
  screen.window:
    description: "Capture specific application window"
    risk: high
    min_age: 16
    requires: [first_party, signed]
  
  screen.game:
    description: "Capture game windows only (auto-detected)"
    risk: medium
    min_age: 13
    requires: []
  
  screen.region:
    description: "Capture declared screen regions"
    risk: low
    min_age: 13
    requires: []
  
  # ═══════════════════════════════════════════════════════════════════
  # AUDIO
  # ═══════════════════════════════════════════════════════════════════
  
  audio.always_on:
    description: "Continuous microphone access"
    risk: critical
    min_age: 18
    requires: [first_party]
  
  audio.voice_activation:
    description: "Listen for wake word"
    risk: high
    min_age: 16
    requires: [first_party, signed]
  
  audio.push_to_talk:
    description: "Microphone when user activates"
    risk: medium
    min_age: 13
    requires: []
  
  audio.system:
    description: "System audio capture (game sounds)"
    risk: medium
    min_age: 16
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # INPUT
  # ═══════════════════════════════════════════════════════════════════
  
  keyboard.read:
    description: "Read keystrokes"
    risk: critical
    min_age: 18
    requires: [first_party]
  
  mouse.read:
    description: "Read mouse position and clicks"
    risk: medium
    min_age: 16
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # FILE SYSTEM
  # ═══════════════════════════════════════════════════════════════════
  
  file.read.game:
    description: "Read game-related files (saves, configs)"
    risk: medium
    min_age: 13
    requires: []
  
  file.read.scoped:
    description: "Read declared file paths"
    risk: medium
    min_age: 16
    requires: []
  
  file.read.any:
    description: "Read arbitrary files"
    risk: critical
    min_age: 18
    requires: [first_party]
  
  # ═══════════════════════════════════════════════════════════════════
  # PROCESS
  # ═══════════════════════════════════════════════════════════════════
  
  process.list:
    description: "See running processes"
    risk: low
    min_age: 13
    requires: []
  
  process.focus:
    description: "See focused application"
    risk: low
    min_age: 13
    requires: []
  
  # ═══════════════════════════════════════════════════════════════════
  # NETWORK
  # ═══════════════════════════════════════════════════════════════════
  
  network.read:
    description: "Query external APIs (weather, prices)"
    risk: medium
    min_age: 16
    requires: []
  
  network.write:
    description: "Send data to external APIs"
    risk: high
    min_age: 18
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # GAME INTEGRATION
  # ═══════════════════════════════════════════════════════════════════
  
  game.mod.read:
    description: "Read from game mods/APIs"
    risk: medium
    min_age: 13
    requires: []
  
  game.mod.write:
    description: "Send commands to game mods"
    risk: high
    min_age: 16
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # IOT / SMART HOME
  # ═══════════════════════════════════════════════════════════════════
  
  iot.sensor:
    description: "Read IoT sensors (temperature, humidity)"
    risk: low
    min_age: 16
    requires: []
  
  iot.state:
    description: "Read device states (is light on?)"
    risk: low
    min_age: 16
    requires: []
  
  iot.control:
    description: "Control IoT devices"
    risk: high
    min_age: 18
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # MEMORY
  # ═══════════════════════════════════════════════════════════════════
  
  memory.read:
    description: "Read GLADyS memory"
    risk: low
    min_age: 13
    requires: []
  
  memory.write:
    description: "Write to GLADyS memory"
    risk: low
    min_age: 13
    requires: []
  
  # ═══════════════════════════════════════════════════════════════════
  # EXECUTIVE
  # ═══════════════════════════════════════════════════════════════════
  
  executive.influence:
    description: "Influence response generation"
    risk: medium
    min_age: 16
    requires: []
  
  executive.instruct:
    description: "Send instructions to executive"
    risk: high
    min_age: 18
    requires: [first_party, signed]
  
  # ═══════════════════════════════════════════════════════════════════
  # NOTIFICATIONS
  # ═══════════════════════════════════════════════════════════════════
  
  user.notify:
    description: "Send notifications to user"
    risk: low
    min_age: 13
    requires: []
```

### 9.2 Manifest Permission Declaration

**Sensors:**

```yaml
# sensor manifest
sensor:
  id: minecraft-visual
  
  permissions:
    required:
      - screen.game
      - process.focus
      - game.mod.read
    
    optional:
      - audio.push_to_talk
    
    justifications:
      screen.game: "See Minecraft gameplay for situational awareness"
      process.focus: "Detect when Minecraft is active"
      game.mod.read: "Get precise game state from aperture"
      audio.push_to_talk: "Voice commands for hands-free gaming"
    
    screen:
      type: game
      buffer:
        enabled: true
        max_seconds: 30
        max_frames: 60
    
    game.mod:
      read:
        - mod_id: aperture
          data_types: [player_position, player_health, nearby_entities]
  
  install_behavior:
    on_required_denied: reject
```

**Skills:**

```yaml
# skill manifest
skill:
  id: climate-controller
  
  permissions:
    required:
      - iot.sensor
      - iot.state
      - memory.read
      - memory.write
    
    optional:
      - iot.control
      - network.read
    
    justifications:
      iot.sensor: "Read temperature and humidity sensors"
      iot.state: "Check current thermostat settings"
      iot.control: "Adjust thermostat (with constraints)"
      network.read: "Get weather forecast for proactive adjustments"
      memory.read: "Access learned comfort preferences"
      memory.write: "Store comfort preferences"
    
    iot:
      sensor:
        devices: ["temperature_*", "humidity_*"]
      
      control:
        devices: ["thermostat_living_room", "humidifier_bedroom"]
        actions: [set_temperature, set_humidity, set_mode]
        
        constraints:
          temperature:
            min: 60
            max: 80
            unit: fahrenheit
          humidity:
            min: 30
            max: 60
            unit: percent
          
          changes_per_hour: 4
          require_confirmation_above: 5  # Degrees
```

---

## 10. Sensor Consent Model

### 10.1 Opt-In at Install

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SENSOR INSTALLATION FLOW                            │
│                                                                         │
│  User clicks "Install Minecraft Sensor"                                 │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    PERMISSION REQUEST                             │ │
│  │                                                                   │ │
│  │  Minecraft Visual Sensor requests:                               │ │
│  │                                                                   │ │
│  │  REQUIRED PERMISSIONS                                            │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ ☐ Game Screen Capture                         [Medium Risk] │ │ │
│  │  │   "See Minecraft gameplay for situational awareness"        │ │ │
│  │  │                                                             │ │ │
│  │  │ ☐ Focus Detection                             [Low Risk]    │ │ │
│  │  │   "Detect when Minecraft is active"                         │ │ │
│  │  │                                                             │ │ │
│  │  │ ☐ Game Mod Data                               [Medium Risk] │ │ │
│  │  │   "Get precise game state from aperture"        │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  │                                                                   │ │
│  │  OPTIONAL PERMISSIONS                                            │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ ☐ Push-to-Talk Voice                          [Medium Risk] │ │ │
│  │  │   "Voice commands for hands-free gaming"                    │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  │                                                                   │ │
│  │  ⚠️  Denying required permissions will cancel installation       │ │
│  │                                                                   │ │
│  │  [Grant All Required]  [Customize]  [Cancel]                     │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│              ┌───────────────┴───────────────┐                          │
│              │                               │                          │
│              ▼                               ▼                          │
│     Required granted              Required denied                       │
│     ┌───────────────┐             ┌───────────────┐                    │
│     │ Install       │             │ Installation  │                    │
│     │ proceeds      │             │ cancelled     │                    │
│     └───────────────┘             └───────────────┘                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Permission Management

Easy to find, easy to change:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Settings > Privacy & Security > Permissions                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ACTIVE SENSORS                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  ● Minecraft Visual Sensor                              [Manage]        │
│    Permissions: Screen (Game), Focus, Game Mod, Voice                  │
│    Status: Active                                                       │
│                                                                         │
│  ● Desktop Monitor                                      [Manage]        │
│    Permissions: Screen (Window), Focus                                 │
│    Status: Paused                                                       │
│                                                                         │
│  ACTIVE SKILLS                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  ● Climate Controller                                   [Manage]        │
│    Permissions: IoT Sensor, IoT State, IoT Control, Network            │
│    Status: Active                                                       │
│                                                                         │
│  PERMISSION SUMMARY                                                     │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  Screen Capture                                                         │
│    ├── Full Screen: Not granted                                        │
│    ├── Window: Desktop Monitor                                         │
│    └── Game: Minecraft Visual Sensor                                   │
│                                                                         │
│  Audio                                                                  │
│    ├── Always On: Not granted                                          │
│    ├── Voice Activation: Not granted                                   │
│    └── Push-to-Talk: Minecraft Visual Sensor                           │
│                                                                         │
│  [View All Permissions]  [View Audit Log]  [Reset All]                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.3 Permission Change Behavior

| Action | Effect |
|--------|--------|
| Revoke required permission | Sensor disabled with explanation |
| Revoke optional permission | Sensor continues with reduced functionality |
| Grant new permission | Effective immediately |
| Revoke then re-grant | Sensor re-enabled |

---

## 11. Sandboxing Architecture

### 11.1 Overview

Plugins run in separate processes with no direct system access. All capabilities are mediated through the orchestrator.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SANDBOXING ARCHITECTURE                             │
│                                                                         │
│  ORCHESTRATOR PROCESS (Trusted Core)                                    │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ CAPABILITY SERVICES (only orchestrator has system access)   │ │ │
│  │  │                                                             │ │ │
│  │  │  • ScreenCaptureService   - Captures screen                 │ │ │
│  │  │  • AudioCaptureService    - Captures microphone             │ │ │
│  │  │  • FileAccessService      - Reads files                     │ │ │
│  │  │  • GameModService         - Proxies game mod APIs           │ │ │
│  │  │  • IoTGatewayService      - Proxies IoT devices             │ │ │
│  │  │                                                             │ │ │
│  │  └───────────────────────────┬─────────────────────────────────┘ │ │
│  │                              │                                   │ │
│  │  ┌───────────────────────────┴─────────────────────────────────┐ │ │
│  │  │ SECURITY MODULE                                             │ │ │
│  │  │                                                             │ │ │
│  │  │  • Permission chain (age, trust, consent, scope, rate)     │ │ │
│  │  │  • Checks every request before fulfillment                 │ │ │
│  │  │  • Can abort at any point                                  │ │ │
│  │  │                                                             │ │ │
│  │  └───────────────────────────┬─────────────────────────────────┘ │ │
│  │                              │                                   │ │
│  │  ┌───────────────────────────┴─────────────────────────────────┐ │ │
│  │  │ SHARED MEMORY REGION (owned by orchestrator)               │ │ │
│  │  │                                                             │ │ │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │ │ │
│  │  │  │ Frame 0 │  │ Frame 1 │  │ Frame 2 │  │ Frame 3 │       │ │ │
│  │  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │ │ │
│  │  │                                                             │ │ │
│  │  │  Orchestrator: WRITE access                                │ │ │
│  │  │  Sensors: READ-ONLY access (OS-enforced)                   │ │ │
│  │  │                                                             │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              │ gRPC          │ Shared Mem    │ gRPC                     │
│              │ (control)     │ (data)        │ (control)                │
│              ▼               ▼               ▼                          │
│       ┌───────────┐   ┌───────────┐   ┌───────────┐                    │
│       │ Sensor A  │   │ Sensor B  │   │ Skill A   │                    │
│       │ (sandbox) │   │ (sandbox) │   │ (sandbox) │                    │
│       │           │   │           │   │           │                    │
│       │ CANNOT:   │   │ CANNOT:   │   │ CANNOT:   │                    │
│       │ • Screen  │   │ • Screen  │   │ • IoT     │                    │
│       │ • Audio   │   │ • Audio   │   │ • Network │                    │
│       │ • Files   │   │ • Files   │   │ • Files   │                    │
│       │ • Network │   │ • Network │   │           │                    │
│       │           │   │           │   │           │                    │
│       │ CAN:      │   │ CAN:      │   │ CAN:      │                    │
│       │ • Read    │   │ • Read    │   │ • Request │                    │
│       │   shared  │   │   shared  │   │   via     │                    │
│       │   memory  │   │   memory  │   │   gRPC    │                    │
│       │ • gRPC    │   │ • gRPC    │   │           │                    │
│       └───────────┘   └───────────┘   └───────────┘                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Shared Memory for Performance

Shared memory provides zero-copy image transfer while maintaining security:

| Property | Value |
|----------|-------|
| Owner | Orchestrator process |
| Sensor access | Read-only (OS-enforced via page table) |
| Crash isolation | Sensor crash cannot corrupt shared memory |
| Write attempt | OS returns SEGFAULT, sensor crashes, no effect on orchestrator |

**Implementation:**

```rust
// Rust orchestrator - create shared memory
use shared_memory::{Shmem, ShmemConf};

struct FrameBuffer {
    shmem: Shmem,
    frame_size: usize,
    num_frames: usize,
}

impl FrameBuffer {
    fn new(width: u32, height: u32, num_frames: usize) -> Self {
        let frame_size = (width * height * 4) as usize; // RGBA
        let total_size = HEADER_SIZE + frame_size * num_frames;
        
        let shmem = ShmemConf::new()
            .size(total_size)
            .os_id("gladysframes")
            .create()
            .expect("Failed to create shared memory");
        
        Self { shmem, frame_size, num_frames }
    }
    
    fn write_frame(&self, frame_index: usize, data: &[u8]) {
        let offset = HEADER_SIZE + frame_index * self.frame_size;
        unsafe {
            let ptr = self.shmem.as_ptr().add(offset) as *mut u8;
            std::ptr::copy_nonoverlapping(data.as_ptr(), ptr, data.len());
        }
        self.update_header(frame_index);
    }
}
```

```python
# Python sensor - read-only access
import mmap

class FrameReader:
    def __init__(self):
        # ACCESS_READ enforced by OS - cannot write
        self.shm = mmap.mmap(
            -1, 
            BUFFER_SIZE, 
            "gladysframes", 
            access=mmap.ACCESS_READ
        )
    
    def get_latest_frame(self) -> np.ndarray:
        header = self._read_header()
        offset = HEADER_SIZE + header.latest_index * FRAME_SIZE
        
        # Zero-copy view into shared memory
        return np.frombuffer(
            self.shm, 
            dtype=np.uint8, 
            count=FRAME_SIZE, 
            offset=offset
        ).reshape((HEIGHT, WIDTH, 4))
```

### 11.3 Crash Scenarios

| Scenario | Result |
|----------|--------|
| Sensor crashes | Sensor process dies, shared memory unaffected, orchestrator unaffected |
| Sensor tries to write shared memory | OS SEGFAULT, sensor crashes, no corruption |
| Orchestrator crashes | Shared memory freed by OS, sensors lose access gracefully |
| Sensor goes rogue | Limited to its declared permissions, cannot escalate |

---

## 12. Security Module

### 12.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SECURITY MODULE                                     │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    SECURITY MODULE (Singleton)                    │ │
│  │                                                                   │ │
│  │  • Central authority for all security decisions                  │ │
│  │  • Holds permission registry, policies, user consent             │ │
│  │  • Immutable audit log                                           │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    PERMISSION CHAIN                               │ │
│  │                    (Chain of Responsibility)                      │ │
│  │                                                                   │ │
│  │  ┌─────┐   ┌─────┐   ┌───────┐   ┌─────┐   ┌────┐   ┌──────┐   │ │
│  │  │ Age │ → │Trust│ → │Consent│ → │Scope│ → │Rate│ → │Constr│   │ │
│  │  └─────┘   └─────┘   └───────┘   └─────┘   └────┘   └──────┘   │ │
│  │                                                                   │ │
│  │  Any handler can DENY or ABORT                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    gRPC INTERCEPTORS                              │ │
│  │                                                                   │ │
│  │  Every incoming call validated before reaching service handler   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    ACTION GUARDS                                  │ │
│  │                                                                   │ │
│  │  Final check before privileged operations                        │ │
│  │  • FileAccessGuard.check_before_read(path)                       │ │
│  │  • IoTControlGuard.check_before_control(device, action, value)   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    AUDIT LOG                                      │ │
│  │                                                                   │ │
│  │  Immutable record of all security decisions                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Chain of Responsibility Handlers

| Handler | Checks | Can Result In |
|---------|--------|---------------|
| **AgeCheckHandler** | User age ≥ permission min_age | DENY |
| **TrustLevelHandler** | Plugin is first_party or signed as required | DENY |
| **UserConsentHandler** | User has granted this permission | DENY |
| **ScopeValidationHandler** | Action within declared scope (paths, devices) | ABORT |
| **RateLimitHandler** | Within rate limits | DENY |
| **ConstraintCheckHandler** | Values within declared constraints | DENY |

**DENY vs ABORT:**
- DENY: Normal rejection, logged, plugin can retry
- ABORT: Security violation, plugin terminated, incident logged

### 12.3 Implementation

```python
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod

class SecurityVerdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ABORT = "abort"

@dataclass
class SecurityDecision:
    verdict: SecurityVerdict
    reason: str
    handler: str

@dataclass
class SecurityContext:
    user_age: int
    plugin_id: str
    plugin_type: str
    is_first_party: bool
    is_signed: bool
    requested_permission: str
    action_details: dict

class SecurityHandler(ABC):
    def __init__(self):
        self._next = None
    
    def set_next(self, handler: 'SecurityHandler') -> 'SecurityHandler':
        self._next = handler
        return handler
    
    def handle(self, context: SecurityContext, security: 'SecurityModule') -> SecurityDecision:
        decision = self.check(context, security)
        
        if decision.verdict != SecurityVerdict.ALLOW:
            return decision
        
        if self._next:
            return self._next.handle(context, security)
        
        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            reason="All checks passed",
            handler="FinalAllow"
        )
    
    @abstractmethod
    def check(self, context: SecurityContext, security: 'SecurityModule') -> SecurityDecision:
        pass


class AgeCheckHandler(SecurityHandler):
    def check(self, context: SecurityContext, security: 'SecurityModule') -> SecurityDecision:
        perm = security.permission_registry.get(context.requested_permission)
        min_age = perm.get("min_age", 18)
        
        if context.user_age < min_age:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=f"Requires age {min_age}+",
                handler=self.__class__.__name__
            )
        
        return SecurityDecision(SecurityVerdict.ALLOW, "Age OK", self.__class__.__name__)


class ScopeValidationHandler(SecurityHandler):
    def check(self, context: SecurityContext, security: 'SecurityModule') -> SecurityDecision:
        manifest = security.get_plugin_manifest(context.plugin_id)
        declared_scope = manifest.get_permission_scope(context.requested_permission)
        
        if not declared_scope:
            # Undeclared permission = security violation
            return SecurityDecision(
                verdict=SecurityVerdict.ABORT,
                reason="Undeclared permission",
                handler=self.__class__.__name__
            )
        
        # Check action is within scope
        if context.requested_permission == "file.read.scoped":
            path = context.action_details.get("path")
            if not self._path_in_scope(path, declared_scope.get("paths", [])):
                return SecurityDecision(
                    verdict=SecurityVerdict.ABORT,
                    reason=f"Path {path} not in declared scope",
                    handler=self.__class__.__name__
                )
        
        return SecurityDecision(SecurityVerdict.ALLOW, "In scope", self.__class__.__name__)


class SecurityModule:
    """Singleton security authority."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.permission_registry = self._load_permissions()
        self.user_consents = {}
        self.audit_log = AuditLog()
        
        # Build chain
        self.chain = AgeCheckHandler()
        self.chain.set_next(TrustLevelHandler()) \
            .set_next(UserConsentHandler()) \
            .set_next(ScopeValidationHandler()) \
            .set_next(RateLimitHandler()) \
            .set_next(ConstraintCheckHandler())
    
    def check_permission(self, context: SecurityContext) -> SecurityDecision:
        decision = self.chain.handle(context, self)
        
        self.audit_log.record(
            event_type="permission_check",
            plugin_id=context.plugin_id,
            permission=context.requested_permission,
            verdict=decision.verdict.value,
            reason=decision.reason
        )
        
        if decision.verdict == SecurityVerdict.ABORT:
            self._terminate_plugin(context.plugin_id, decision.reason)
        
        return decision
```

### 12.4 Action Guards

Last line of defense before privileged operations:

```python
class FileAccessGuard:
    def __init__(self, security: SecurityModule):
        self.security = security
    
    def check_before_read(self, plugin_id: str, path: str) -> bool:
        # Normalize path
        normalized = os.path.normpath(os.path.abspath(path))
        
        # Block path traversal
        if ".." in path:
            self.security.audit_log.record(
                event_type="path_traversal_attempt",
                plugin_id=plugin_id,
                path=path
            )
            self.security.abort_plugin(plugin_id, "Path traversal attempt")
            return False
        
        # Block symlink escape
        if os.path.islink(normalized):
            real_path = os.path.realpath(normalized)
            if not self._path_in_allowed_roots(real_path, plugin_id):
                self.security.abort_plugin(plugin_id, "Symlink escape attempt")
                return False
        
        # Re-verify permission (defense in depth)
        context = SecurityContext(
            user_age=self.security.user_age,
            plugin_id=plugin_id,
            plugin_type="sensor",
            is_first_party=self._is_first_party(plugin_id),
            is_signed=self._is_signed(plugin_id),
            requested_permission="file.read.scoped",
            action_details={"path": normalized}
        )
        
        decision = self.security.check_permission(context)
        return decision.verdict == SecurityVerdict.ALLOW


class IoTControlGuard:
    def __init__(self, security: SecurityModule):
        self.security = security
    
    def check_before_control(
        self, 
        plugin_id: str, 
        device: str, 
        action: str, 
        value: any
    ) -> bool:
        # Hard safety limits (cannot be overridden)
        if not self._check_hard_limits(device, action, value):
            self.security.audit_log.record(
                event_type="hard_limit_violation",
                plugin_id=plugin_id,
                device=device,
                action=action,
                value=value
            )
            self.security.abort_plugin(plugin_id, "Hard safety limit violated")
            return False
        
        # Verify permission
        context = SecurityContext(
            user_age=self.security.user_age,
            plugin_id=plugin_id,
            plugin_type="skill",
            is_first_party=self._is_first_party(plugin_id),
            is_signed=self._is_signed(plugin_id),
            requested_permission="iot.control",
            action_details={"device": device, "action": action, "value": value}
        )
        
        return self.security.check_permission(context).verdict == SecurityVerdict.ALLOW
    
    def _check_hard_limits(self, device: str, action: str, value: any) -> bool:
        """Non-negotiable safety limits."""
        HARD_LIMITS = {
            "thermostat": {"set_temperature": {"min": 45, "max": 90}},
            "oven": {"set_temperature": {"max": 550}},
        }
        
        device_type = self._get_device_type(device)
        limits = HARD_LIMITS.get(device_type, {}).get(action, {})
        
        if "min" in limits and value < limits["min"]:
            return False
        if "max" in limits and value > limits["max"]:
            return False
        
        return True
```

### 12.5 Audit Log

```python
class AuditLog:
    """Append-only security audit log."""
    
    def __init__(self, path: str = "/var/log/gladys/security_audit.log"):
        self.path = path
        self._lock = threading.Lock()
    
    def record(self, event_type: str, **kwargs):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **kwargs
        }
        
        with self._lock:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")
```

---

## 13. Game Mod Integration

### 13.1 Bridge Architecture (Aperture)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     GAME MOD INTEGRATION                                │
│                                                                         │
│  GAME PROCESS (Minecraft)                                               │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ Aperture                                        │ │ │
│  │  │                                                             │ │ │
│  │  │  Endpoints:                                                 │ │ │
│  │  │  GET  /player      → position, health, inventory           │ │ │
│  │  │  GET  /entities    → nearby mobs, players                  │ │ │
│  │  │  GET  /world       → time, weather, dimension              │ │ │
│  │  │  POST /waypoint    → set marker (requires write perm)      │ │ │
│  │  │  POST /chat        → send message (requires write perm)    │ │ │
│  │  │                                                             │ │ │
│  │  └───────────────────────────────┬─────────────────────────────┘ │ │
│  │                                  │ localhost:25566                │ │
│  └──────────────────────────────────┼────────────────────────────────┘ │
│                                     │                                   │
│  ORCHESTRATOR                       │                                   │
│  ┌──────────────────────────────────┼────────────────────────────────┐ │
│  │                                  │                                │ │
│  │  ┌───────────────────────────────┴─────────────────────────────┐ │ │
│  │  │ GAME API GATEWAY                                            │ │ │
│  │  │                                                             │ │ │
│  │  │  • Proxies requests to game mods                           │ │ │
│  │  │  • Enforces sensor permissions                             │ │ │
│  │  │  • Validates endpoints/methods                             │ │ │
│  │  │                                                             │ │ │
│  │  └───────────────────────────────┬─────────────────────────────┘ │ │
│  │                                  │ gRPC                           │ │
│  └──────────────────────────────────┼────────────────────────────────┘ │
│                                     │                                   │
│                          ┌──────────┴──────────┐                        │
│                          ▼                     ▼                        │
│                   ┌───────────┐         ┌───────────┐                  │
│                   │ Minecraft │         │ Game      │                  │
│                   │ Sensor    │         │ Skill     │                  │
│                   └───────────┘         └───────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Mod Data vs Screen Capture

| Data Source | Information | Accuracy | Performance |
|-------------|-------------|----------|-------------|
| Screen capture + vision | "I see player with sword" | ~80% | GPU intensive |
| Game mod API | `{"player": "xX_Slayer_Xx", "health": 18.5, "distance": 23.4}` | 100% | Minimal |

**Recommendation:** Prioritize mod data when available, fall back to vision.

---

## 14. Multi-User Policy

### 14.1 Single User Per Installation

| Approach | Implementation |
|----------|----------------|
| User isolation | Each OS user gets separate data directory |
| No profile switching | One GLADyS instance = one user |
| Data location | `$HOME/.gladys/` (per OS user) |

### 14.2 Configuration

```yaml
# Set at first launch
user:
  age: 25  # Declared, not verified
  age_acknowledged: true
  
  data_directory: /home/scott/.gladys/
```

---

## 15. Consequences

### 15.1 Positive

1. Privacy by design, not afterthought
2. Strong sandboxing prevents malicious plugins
3. Age-appropriate restrictions protect minors
4. User maintains control and transparency
5. Audit trail for accountability
6. Shared memory provides performance without sacrificing security

### 15.2 Negative

1. Complex permission system to implement and maintain
2. 3rd party plugin developers must understand permission model
3. Some capabilities restricted to first-party only
4. Memory consolidation adds background processing

### 15.3 Risks

1. Permission UI complexity may confuse users
2. Overly restrictive defaults may frustrate power users
3. Consolidation may lose important context

---

## 16. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0003: Plugin Manifest Specification (permissions)
- ADR-0004: Memory Schema Details (retention)
- ADR-0005: gRPC Service Contracts (interceptors)
- ADR-0006: Observability & Monitoring (audit logs)

---

## 17. Appendix: Permission Quick Reference

### By Risk Level

| Risk | Permissions |
|------|-------------|
| **Critical** | `screen.full`, `audio.always_on`, `keyboard.read`, `file.read.any` |
| **High** | `screen.window`, `audio.voice_activation`, `iot.control`, `game.mod.write`, `network.write` |
| **Medium** | `screen.game`, `audio.push_to_talk`, `file.read.scoped`, `game.mod.read`, `network.read` |
| **Low** | `screen.region`, `process.list`, `process.focus`, `memory.*`, `iot.sensor`, `iot.state` |

### By Age Requirement

| Age | Permissions |
|-----|-------------|
| **13+** | `screen.game`, `screen.region`, `audio.push_to_talk`, `process.*`, `memory.*`, `game.mod.read`, `file.read.game` |
| **16+** | `screen.window`, `audio.voice_activation`, `audio.system`, `mouse.read`, `file.read.scoped`, `game.mod.write`, `network.read`, `iot.sensor`, `iot.state`, `executive.influence` |
| **18+** | `screen.full`, `audio.always_on`, `keyboard.read`, `file.read.any`, `iot.control`, `network.write`, `executive.instruct` |

### By Trust Requirement

| Requirement | Permissions |
|-------------|-------------|
| **Any** | All low/medium risk with age met |
| **Signed** | `screen.window`, `audio.voice_activation`, `game.mod.write`, `iot.control` |
| **First Party** | `screen.full`, `audio.always_on`, `keyboard.read`, `file.read.any` |
