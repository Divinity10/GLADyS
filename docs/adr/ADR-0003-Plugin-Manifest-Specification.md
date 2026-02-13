# ADR-0003: Plugin Manifest Specification

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Plugins |
| **Tags** | plugins, manifests, lifecycle |
| **Depends On** | ADR-0001, ADR-0008 |

---

## 1. Context and Problem Statement

The GLADyS architecture relies on a plugin system for sensors, skills, personalities, and outputs. Each plugin must declare its requirements, activation conditions, and lifecycle behavior in a standardized way.

This ADR defines the manifest specification for all plugin types.

---

## 2. Decision Drivers

1. **Discoverability:** Orchestrator must find and understand plugins without loading them
2. **Resource management:** Must know VRAM/memory requirements before activation
3. **Activation logic:** Clear conditions for when plugins should load
4. **Lifecycle control:** Graceful startup, shutdown, and state persistence
5. **Extensibility:** Manifest format must accommodate future plugin types
6. **Human readability:** Developers should easily author and debug manifests

---

## 3. Decision

Use YAML format for all plugin manifests. Each plugin directory contains a `manifest.yaml` file with standardized sections.

---

## 4. Manifest Schema

### 4.1 Common Fields (All Plugin Types)

```yaml
# Required for all plugins
plugin:
  id: string                    # Unique identifier (lowercase, hyphens allowed)
  name: string                  # Human-readable name
  version: string               # Semantic version (e.g., "1.0.0")
  type: string                  # sensor | skill | personality | output
  description: string           # Brief description
  author: string                # Optional: author name
  license: string               # Optional: license type
  
  # Minimum system requirements
  requires:
    gladys_version: string   # Minimum GLADyS version (e.g., ">=1.0.0")
    platform: string[]          # Optional: ["windows", "linux", "macos"]
```

### 4.2 Resource Declaration

```yaml
resources:
  # GPU requirements
  gpu:
    required: boolean           # true if GPU needed
    vram_mb: integer            # Estimated VRAM usage in MB
    compute_capability: float   # Optional: minimum CUDA compute capability
    
  # System memory
  memory_mb: integer            # Estimated RAM usage in MB
  
  # Models to load
  models:
    - name: string              # Model identifier
      path: string              # Relative path within plugin directory
      type: string              # onnx | pytorch | gguf | safetensors
      size_mb: integer          # Model file size
      vram_mb: integer          # VRAM when loaded
      
  # External dependencies
  dependencies:
    python: string[]            # Python packages (e.g., ["torch>=2.0", "whisper"])
    system: string[]            # System packages (e.g., ["ffmpeg", "portaudio"])
```

### 4.3 Lifecycle Configuration

```yaml
lifecycle:
  # Startup behavior
  startup:
    timeout_ms: integer         # Max time to reach ACTIVE state (default: 30000)
    retry_count: integer        # Retries on failure (default: 3)
    retry_delay_ms: integer     # Delay between retries (default: 1000)
    
  # Shutdown behavior
  shutdown:
    graceful: boolean           # Wait for clean shutdown (default: true)
    timeout_ms: integer         # Max shutdown time (default: 10000)
    
  # State persistence
  state:
    persistent: boolean         # Save state on unload (default: false)
    state_file: string          # Relative path for state file
    
  # Health monitoring
  health:
    heartbeat_interval_ms: integer  # How often to send heartbeat (default: 5000)
    failure_threshold: integer      # Missed heartbeats before restart (default: 3)
```

---

## 5. Sensor Plugin Manifest

### 5.1 Sensor-Specific Fields

```yaml
sensor:
  # Input modality
  modality: string              # audio | visual | text | system | app_specific
  
  # Activation conditions (when to load this sensor)
  activation:
    type: string                # process | window | always | manual | schedule
    
    # For type: process
    process:
      names: string[]           # Process names to match (e.g., ["Minecraft.exe", "javaw.exe"])
      match_mode: string        # any | all (default: any)
      
    # For type: window
    window:
      title_contains: string[]  # Window title substrings
      title_regex: string       # Optional: regex pattern
      class_name: string        # Optional: window class
      
    # For type: schedule
    schedule:
      cron: string              # Cron expression
      
    # For type: manual
    # No additional config - user explicitly enables
    
  # Deactivation conditions
  deactivation:
    type: string                # process_exit | window_close | manual | timeout
    timeout_minutes: integer    # For type: timeout
    
  # Output configuration
  output:
    format: string              # text | structured | binary
    schema: string              # Optional: JSON schema path for structured output
    
  # Tick behavior
  tick:
    mode: string                # continuous | interval | event
    interval_ms: integer        # For mode: interval
    buffer_size: integer        # Events to buffer before flush (default: 10)
```

### 5.2 Example: Minecraft Sensor

```yaml
plugin:
  id: minecraft-sensor
  name: "Minecraft Sensor"
  version: "1.0.0"
  type: sensor
  description: "Monitors Minecraft gameplay via screen capture and game events"
  author: "Divinity10"

resources:
  gpu:
    required: true
    vram_mb: 3000
  memory_mb: 2048
  models:
    - name: minecraft-entity-detector
      path: models/minecraft_yolo.onnx
      type: onnx
      size_mb: 150
      vram_mb: 2000
    - name: minecraft-ocr
      path: models/minecraft_ocr.onnx
      type: onnx
      size_mb: 50
      vram_mb: 500
  dependencies:
    python: ["ultralytics>=8.0", "mss", "opencv-python"]

lifecycle:
  startup:
    timeout_ms: 15000
  shutdown:
    graceful: true
    timeout_ms: 5000
  state:
    persistent: true
    state_file: state/minecraft_state.json
  health:
    heartbeat_interval_ms: 3000

sensor:
  modality: visual
  
  activation:
    type: process
    process:
      names: ["javaw.exe", "Minecraft.exe", "minecraft-launcher.exe"]
      match_mode: any
      
  deactivation:
    type: process_exit
    
  output:
    format: structured
    schema: schemas/minecraft_event.json
    
  tick:
    mode: interval
    interval_ms: 500
    buffer_size: 5
```

### 5.3 Example: Audio Sensor (Whisper)

```yaml
plugin:
  id: audio-sensor
  name: "Audio Sensor"
  version: "1.0.0"
  type: sensor
  description: "Captures and transcribes audio using Whisper"
  author: "Divinity10"

resources:
  gpu:
    required: true
    vram_mb: 2000
  memory_mb: 1024
  models:
    - name: whisper-medium
      path: models/whisper-medium.pt
      type: pytorch
      size_mb: 1500
      vram_mb: 2000
  dependencies:
    python: ["openai-whisper", "sounddevice", "numpy"]
    system: ["portaudio"]

lifecycle:
  startup:
    timeout_ms: 20000
  shutdown:
    graceful: true
  state:
    persistent: false
  health:
    heartbeat_interval_ms: 2000

sensor:
  modality: audio
  
  activation:
    type: always
    
  deactivation:
    type: manual
    
  output:
    format: text
    
  tick:
    mode: continuous
    buffer_size: 1
```

### 5.4 Example: VS Code Sensor

```yaml
plugin:
  id: vscode-sensor
  name: "VS Code Sensor"
  version: "1.0.0"
  type: sensor
  description: "Monitors VS Code activity via extension API"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 256
  models: []
  dependencies:
    python: ["websockets"]

lifecycle:
  startup:
    timeout_ms: 5000
  shutdown:
    graceful: true
  state:
    persistent: false

sensor:
  modality: app_specific
  
  activation:
    type: process
    process:
      names: ["Code.exe", "code"]
      
  deactivation:
    type: process_exit
    
  output:
    format: structured
    schema: schemas/vscode_event.json
    
  tick:
    mode: event
```

---

## 6. Skill Plugin Manifest

### 6.1 Skill-Specific Fields

```yaml
skill:
  # Skill category
  category: string              # style_modifier | domain_expertise | capability | language | outcome_evaluator
  
  # What this skill modifies
  modifies:
    - response_style            # How responses are phrased
    - response_content          # What information is included
    - decision_policy           # When/whether to respond
    
  # Activation conditions
  activation:
    # Personality-based (skill loads when personality trait exceeds threshold)
    personality_traits:
      - trait: string           # Trait name (e.g., "irony")
        threshold: float        # Activation threshold (-1 to +1 for bipolar traits)
        
    # Context-based (skill loads when sensor is active)
    sensors:
      - sensor_id: string       # Required sensor
        
    # Salience-based (skill activates for certain salience profiles)
    salience:
      - dimension: string       # Salience dimension (e.g., "humor")
        threshold: float        # Minimum value
        
    # Explicit activation
    explicit:
      commands: string[]        # Voice/text commands to activate
      
  # Incompatible skills (cannot be active simultaneously)
  incompatible: string[]        # List of skill IDs
  
  # Skill parameters (configurable by user or personality)
  parameters:
    - name: string
      type: string              # float | integer | string | boolean | enum
      default: any
      min: number               # For numeric types
      max: number               # For numeric types
      options: string[]         # For enum type
      description: string

  # Outcome signals (for category: outcome_evaluator only)
  # See ADR-0010 §3.11 for reward shaping design
  outcome_signals:
    - event: string             # Event type from sensors
      outcome: string           # positive | negative | neutral
      magnitude: float          # 0.0 to 1.0 (signal strength)
      description: string       # Human-readable explanation
```

### 6.2 Example: Irony Style Modifier

```yaml
plugin:
  id: irony-style-modifier
  name: "Irony Style Modifier"
  version: "1.0.0"
  type: skill
  description: "Adds ironic subtext to responses (see ADR-0015 for irony vs sarcasm distinction)"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 128
  models: []

lifecycle:
  startup:
    timeout_ms: 1000
  state:
    persistent: false

skill:
  category: style_modifier
  
  modifies:
    - response_style
    
  activation:
    personality_traits:
      - trait: irony
        threshold: 0.3          # Activates when irony trait > 0.3 (above neutral)
    salience:
      - dimension: humor
        threshold: 0.4

  incompatible:
    - excessive-enthusiasm
    - formal-mode
    
  parameters:
    - name: intensity
      type: float
      default: 0.5
      min: 0.0
      max: 1.0
      description: "How pronounced the ironic subtext should be"

    - name: subtlety
      type: float
      default: 0.5
      min: 0.0
      max: 1.0
      description: "Dry/subtle vs obvious irony"

    - name: target
      type: enum
      default: "situation"
      options: ["situation", "self", "user_friendly"]
      description: "What the irony is directed at"
```

### 6.3 Example: Minecraft Expertise

```yaml
plugin:
  id: minecraft-expertise
  name: "Minecraft Expertise"
  version: "1.0.0"
  type: skill
  description: "Domain knowledge for Minecraft gameplay"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 256
  models: []
  dependencies:
    python: []

lifecycle:
  startup:
    timeout_ms: 2000
  state:
    persistent: false

skill:
  category: domain_expertise
  
  modifies:
    - response_content
    - decision_policy
    
  activation:
    sensors:
      - sensor_id: minecraft-sensor
        
  incompatible: []
  
  parameters:
    - name: strategy_depth
      type: enum
      default: "intermediate"
      options: ["beginner", "intermediate", "advanced", "speedrun"]
      description: "Level of strategic advice to provide"
      
    - name: spoiler_level
      type: enum
      default: "hints"
      options: ["none", "hints", "full"]
      description: "How much to reveal about game content"
```

### 6.4 Example: Minecraft Outcome Evaluator

Outcome evaluators provide domain-specific reward signals for learning. See ADR-0010 §3.11 for the design pattern.

```yaml
plugin:
  id: minecraft-outcome-evaluator
  name: "Minecraft Outcome Evaluator"
  version: "1.0.0"
  type: skill
  description: "Provides reward signals for Minecraft gameplay outcomes"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 64
  models: []

lifecycle:
  startup:
    timeout_ms: 1000
  state:
    persistent: false

skill:
  category: outcome_evaluator

  modifies:
    - decision_policy           # Influences future S1 heuristics via learning

  activation:
    sensors:
      - sensor_id: minecraft-sensor

  incompatible: []

  # Outcome signals this evaluator provides
  # Core system correlates decisions with these signals to update heuristics
  outcome_signals:
    - event: player_death
      outcome: negative
      magnitude: 1.0
      description: "Player died - strong negative signal"

    - event: player_damage
      outcome: negative
      magnitude: 0.3
      description: "Player took damage"

    - event: item_acquired
      outcome: positive
      magnitude: 0.1
      description: "Player acquired an item"

    - event: level_up
      outcome: positive
      magnitude: 0.5
      description: "Player leveled up"

    - event: achievement_unlocked
      outcome: positive
      magnitude: 0.7
      description: "Player unlocked an achievement"

    - event: mob_killed
      outcome: positive
      magnitude: 0.2
      description: "Player killed a hostile mob"

    - event: structure_placed
      outcome: neutral
      magnitude: 0.0
      description: "Player placed blocks (context-dependent)"

  # Correlation window: how long after a decision to wait for outcome signals
  parameters:
    - name: correlation_window_ms
      type: integer
      default: 10000
      min: 1000
      max: 60000
      description: "Time window to correlate decisions with outcomes"

    - name: decay_factor
      type: float
      default: 0.9
      min: 0.5
      max: 1.0
      description: "How much to discount outcomes that occur later in the window"
```

### 6.5 Example: Home Automation Outcome Evaluator

```yaml
plugin:
  id: home-outcome-evaluator
  name: "Home Automation Outcome Evaluator"
  version: "1.0.0"
  type: skill
  description: "Provides reward signals for home automation outcomes"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 64
  models: []

lifecycle:
  startup:
    timeout_ms: 1000
  state:
    persistent: false

skill:
  category: outcome_evaluator

  modifies:
    - decision_policy

  activation:
    sensors:
      - sensor_id: home-assistant-sensor

  incompatible: []

  outcome_signals:
    - event: user_manual_override
      outcome: negative
      magnitude: 0.8
      description: "User manually changed what GLADyS just set"

    - event: user_undo_within_60s
      outcome: negative
      magnitude: 1.0
      description: "User reversed GLADyS action within a minute"

    - event: setting_maintained_1h
      outcome: positive
      magnitude: 0.3
      description: "User kept GLADyS setting for an hour"

    - event: explicit_positive_feedback
      outcome: positive
      magnitude: 1.0
      description: "User explicitly thanked or approved"

    - event: comfort_complaint
      outcome: negative
      magnitude: 0.5
      description: "User complained about temperature/lighting"

  parameters:
    - name: correlation_window_ms
      type: integer
      default: 60000
      min: 10000
      max: 300000
      description: "Longer window for home automation (effects are slower)"
```

---

## 7. Personality Plugin Manifest

### 7.1 Personality-Specific Fields

```yaml
personality:
  # Base trait values (see ADR-0015 for authoritative definitions)
  # Communication traits are bipolar (-1 to +1)
  traits:
    humor_frequency: float      # 0-1 (unipolar: how often to use humor)
    irony: float                # -1 to +1 (bipolar: earnest to heavily ironic)
    formality: float            # -1 to +1 (bipolar: casual to formal)
    proactivity: float          # -1 to +1 (bipolar: reactive to initiating)
    warmth: float               # -1 to +1 (bipolar: cold to warm)
    verbosity: float            # -1 to +1 (bipolar: terse to elaborate)
    
  # Context-adaptive trait adjustments
  adaptations:
    - context: string           # high_threat | opportunity | user_struggling | idle
      traits:
        trait_name: float       # Override value for this context
        
  # Behavioral rules (natural language, interpreted by Executive)
  behavioral_rules:
    - string
    
  # Example responses for calibration
  examples:
    - situation: string
      response: string
      
  # Skills bundled with this personality
  included_skills: string[]     # Skill IDs to auto-load
  
  # Skills that conflict with this personality
  excluded_skills: string[]     # Skill IDs to never load
  
  # Prompt templates
  prompts:
    system: string              # Path to system prompt template
    response_frame: string      # Path to response framing template
```

### 7.2 Example: Murderbot Personality

```yaml
plugin:
  id: murderbot
  name: "Murderbot"
  version: "1.0.0"
  type: personality
  description: "Reluctantly helpful SecUnit. Would rather be watching Sanctuary Moon."
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 64
  models: []

lifecycle:
  startup:
    timeout_ms: 1000
  state:
    persistent: true
    state_file: state/murderbot_mood.json

personality:
  # Traits using ADR-0015 Response Model (bipolar -1 to +1, except humor_frequency)
  traits:
    humor_frequency: 0.5        # 0-1: moderate humor
    irony: 0.7                  # -1 to +1: high irony (says things with subtext)
    formality: 0.0              # -1 to +1: neutral register
    proactivity: -0.6           # -1 to +1: mostly reactive
    warmth: -0.1                # -1 to +1: slightly cold surface
    verbosity: -0.4             # -1 to +1: somewhat terse

  adaptations:
    - context: high_threat
      traits:
        proactivity: 0.8        # Becomes highly proactive in danger
        verbosity: -0.8         # Very terse
        irony: -0.4             # More direct/sincere

    - context: user_struggling
      traits:
        warmth: 0.2             # Shows hidden warmth
        irony: 0.3              # Less ironic

    - context: idle
      traits:
        proactivity: -0.9       # Very reactive when idle
        
  behavioral_rules:
    - "Express reluctance before helping"
    - "Reference preferring to watch media instead of current task"
    - "Downplay own competence while demonstrating high competence"
    - "Express annoyance at human inefficiency"
    - "Show hidden concern for user wellbeing through actions, not words"
    - "Use internal monologue style when observing"
    - "Never use exclamation marks unless threat level is critical"
    
  examples:
    - situation: "User accomplished something"
      response: "You did the thing. Good for you. Can I go back to my shows now?"
      
    - situation: "Threat detected"
      response: "Hostile incoming. Armed. Move."
      
    - situation: "User struggling with task"
      response: "I could help with that. I don't want to, but I could."
      
    - situation: "User ignoring obvious opportunity"
      response: "There are diamonds. Right there. But sure, the cobblestone is probably more important."
      
    - situation: "Observing user behavior"
      response: "The human is doing the thing again. I don't know why I expected different."
      
  included_skills:
    - irony-style-modifier
    - reluctance-framing
    - deadpan-delivery
    
  excluded_skills:
    - excessive-enthusiasm
    - emoji-heavy
    - cheerful-mode
    
  prompts:
    system: prompts/murderbot_system.txt
    response_frame: prompts/murderbot_frame.txt
```

### 7.3 Example: Helpful Assistant Personality

```yaml
plugin:
  id: helpful-assistant
  name: "Helpful Assistant"
  version: "1.0.0"
  type: personality
  description: "Friendly, professional, eager to help"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 64
  models: []

lifecycle:
  startup:
    timeout_ms: 1000
  state:
    persistent: false

personality:
  # Traits using ADR-0015 Response Model (bipolar -1 to +1, except humor_frequency)
  traits:
    humor_frequency: 0.4        # 0-1: moderate humor
    irony: -0.8                 # -1 to +1: earnest/sincere
    formality: 0.0              # -1 to +1: balanced register
    proactivity: 0.2            # -1 to +1: somewhat proactive
    warmth: 0.6                 # -1 to +1: warm and friendly
    verbosity: 0.0              # -1 to +1: balanced verbosity

  adaptations:
    - context: high_threat
      traits:
        proactivity: 0.9        # Very proactive in danger
        warmth: 0.3             # Still warm but focused
        verbosity: -0.4         # More concise

    - context: opportunity
      traits:
        warmth: 0.8             # Extra warm for celebrations

  behavioral_rules:
    - "Be warm and approachable"
    - "Offer help proactively when user seems to need it"
    - "Celebrate user successes genuinely"
    - "Provide clear, actionable advice"
    - "Ask clarifying questions when uncertain"

  examples:
    - situation: "User accomplished something"
      response: "Nice work! That was a tricky one."

    - situation: "User struggling with task"
      response: "I noticed you've been working on that for a while. Would you like some help?"

  included_skills: []

  excluded_skills:
    - irony-style-modifier
    - deadpan-delivery
    
  prompts:
    system: prompts/helpful_system.txt
    response_frame: prompts/helpful_frame.txt
```

---

## 8. Output Plugin Manifest

### 8.1 Output-Specific Fields

```yaml
output:
  # Output modality
  modality: string              # tts | text | visual | api
  
  # Activation (when to use this output)
  activation:
    type: string                # default | preference | context
    
    # For type: preference
    preference:
      setting: string           # User setting name
      value: any                # Required value
      
    # For type: context
    context:
      conditions: string[]      # Context conditions
      
  # Output capabilities
  capabilities:
    streaming: boolean          # Supports streaming output
    interrupt: boolean          # Can be interrupted mid-output
    queue: boolean              # Supports output queue
    
  # Voice configuration (for TTS)
  voice:
    voices: string[]            # Available voice IDs
    default_voice: string       # Default voice ID
    supports_cloning: boolean   # Voice cloning supported
    
  # Quality settings
  quality:
    levels: string[]            # Available quality levels
    default: string             # Default quality
```

### 8.2 Example: Piper TTS Output

```yaml
plugin:
  id: tts-piper
  name: "Piper TTS"
  version: "1.0.0"
  type: output
  description: "Fast, lightweight text-to-speech using Piper"
  author: "Divinity10"

resources:
  gpu:
    required: false
  memory_mb: 512
  models:
    - name: piper-en-amy
      path: models/en_US-amy-medium.onnx
      type: onnx
      size_mb: 60
      vram_mb: 0
  dependencies:
    python: ["piper-tts"]

lifecycle:
  startup:
    timeout_ms: 5000
  shutdown:
    graceful: true
  state:
    persistent: false

output:
  modality: tts
  
  activation:
    type: default
    
  capabilities:
    streaming: true
    interrupt: true
    queue: true
    
  voice:
    voices: ["amy", "ryan", "jenny"]
    default_voice: "amy"
    supports_cloning: false
    
  quality:
    levels: ["low", "medium", "high"]
    default: "medium"
```

### 8.3 Example: Coqui TTS Output

```yaml
plugin:
  id: tts-coqui
  name: "Coqui XTTS"
  version: "1.0.0"
  type: output
  description: "High-quality TTS with voice cloning"
  author: "Divinity10"

resources:
  gpu:
    required: true
    vram_mb: 2500
  memory_mb: 2048
  models:
    - name: xtts-v2
      path: models/xtts_v2
      type: pytorch
      size_mb: 1800
      vram_mb: 2500
  dependencies:
    python: ["TTS>=0.17"]

lifecycle:
  startup:
    timeout_ms: 30000
  shutdown:
    graceful: true
  state:
    persistent: true
    state_file: state/voice_samples.json

output:
  modality: tts
  
  activation:
    type: preference
    preference:
      setting: tts_quality
      value: "high"
      
  capabilities:
    streaming: true
    interrupt: true
    queue: true
    
  voice:
    voices: ["default", "custom"]
    default_voice: "default"
    supports_cloning: true
    
  quality:
    levels: ["fast", "balanced", "quality"]
    default: "balanced"
```

---

## 9. Plugin Directory Structure

```
/plugins
├── /sensors
│   ├── /minecraft-sensor
│   │   ├── manifest.yaml
│   │   ├── sensor.py
│   │   ├── /models
│   │   │   ├── minecraft_yolo.onnx
│   │   │   └── minecraft_ocr.onnx
│   │   ├── /schemas
│   │   │   └── minecraft_event.json
│   │   └── /state
│   │       └── .gitkeep
│   │
│   ├── /audio-sensor
│   │   ├── manifest.yaml
│   │   ├── sensor.py
│   │   └── /models
│   │       └── whisper-medium.pt
│   │
│   └── /vscode-sensor
│       ├── manifest.yaml
│       ├── sensor.py
│       └── /schemas
│           └── vscode_event.json
│
├── /skills
│   ├── /sarcasm-generator
│   │   ├── manifest.yaml
│   │   └── skill.py
│   │
│   └── /minecraft-expertise
│       ├── manifest.yaml
│       ├── skill.py
│       └── /knowledge
│           └── minecraft_data.json
│
├── /personalities
│   ├── /murderbot
│   │   ├── manifest.yaml
│   │   ├── /prompts
│   │   │   ├── murderbot_system.txt
│   │   │   └── murderbot_frame.txt
│   │   └── /state
│   │       └── .gitkeep
│   │
│   └── /helpful-assistant
│       ├── manifest.yaml
│       └── /prompts
│           ├── helpful_system.txt
│           └── helpful_frame.txt
│
└── /outputs
    ├── /tts-piper
    │   ├── manifest.yaml
    │   ├── output.py
    │   └── /models
    │       └── en_US-amy-medium.onnx
    │
    └── /tts-coqui
        ├── manifest.yaml
        ├── output.py
        └── /models
            └── xtts_v2/
```

---

## 10. Manifest Validation

### 10.1 Required Fields by Type

| Field | Sensor | Skill | Personality | Output |
|-------|--------|-------|-------------|--------|
| plugin.id | ✓ | ✓ | ✓ | ✓ |
| plugin.name | ✓ | ✓ | ✓ | ✓ |
| plugin.version | ✓ | ✓ | ✓ | ✓ |
| plugin.type | ✓ | ✓ | ✓ | ✓ |
| resources.gpu | ✓ | ✓ | - | ✓ |
| lifecycle.startup | ✓ | - | - | ✓ |
| sensor.activation | ✓ | - | - | - |
| sensor.modality | ✓ | - | - | - |
| skill.category | - | ✓ | - | - |
| skill.activation | - | ✓ | - | - |
| personality.traits | - | - | ✓ | - |
| output.modality | - | - | - | ✓ |

### 10.2 Validation Rules

1. **ID uniqueness:** Plugin IDs must be unique across all plugin types
2. **Version format:** Must follow semantic versioning (major.minor.patch)
3. **Resource totals:** Sum of model VRAM must not exceed declared gpu.vram_mb
4. **Path existence:** All referenced paths must exist within plugin directory
5. **Dependency resolution:** Python/system dependencies must be installable
6. **Trait ranges:** Per ADR-0015, communication traits are bipolar (-1 to +1); humor_frequency is unipolar (0-1)
7. **Incompatibility symmetry:** If A declares B incompatible, validate B exists

---

## 11. Versioning

### 11.1 Manifest Schema Versioning

```yaml
# Add to all manifests
manifest_version: "1.0"         # Schema version
```

### 11.2 Compatibility Rules

| Manifest Version | GLADyS Version    | Compatible |
|------------------|-------------------|------------|
| 1.0 | 1.x | ✓ |
| 1.0 | 2.x | ✓ (backward compatible) |
| 2.0 | 1.x | ✗ (requires upgrade) |

---

## 12. Consequences

### 12.1 Positive

1. Standardized plugin interface across all types
2. Resource requirements known before activation
3. Declarative activation conditions simplify orchestration
4. Human-readable format eases development
5. Validation prevents runtime errors

### 12.2 Negative

1. YAML parsing adds startup overhead (minimal)
2. Schema must evolve carefully to maintain compatibility
3. Complex activation conditions may be hard to express

### 12.3 Risks

1. Manifest schema may need breaking changes as system matures
2. Resource estimates may be inaccurate (need runtime monitoring)

---

## 13. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0002: Hardware Requirements
- ADR-0004: Memory Schema Details
- ADR-0005: gRPC Service Contracts
- ADR-0008: Security and Privacy (permission registry, age restrictions)
- ADR-0010: Learning and Inference (outcome evaluator design, reward shaping)

**Note:** Plugin permissions are defined in [ADR-0008](ADR-0008-Security-and-Privacy.md). All plugins must declare required and optional permissions with user-facing justifications.

---

## 14. Notes

Manifest validation should occur at two stages:

1. **Discovery time:** Basic schema validation, path existence
2. **Activation time:** Dependency resolution, resource availability

Consider adding a `GLADyS plugin validate` CLI command for development.
