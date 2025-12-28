# ADR-0001: AI Companion System Architecture

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10) |
| **Contributors** | Scott |

---

## 1. Context and Problem Statement

We are building a general-purpose AI Companion/Assistant that monitors user activity across applications and responds proactively. The system should congratulate achievements, commiserate with setbacks, suggest actions, and provide reminders. Initial scope targets a single application (Minecraft) but the architecture must scale to monitor the user's entire computing environment.

The AI must have a configurable personality across multiple dimensions (humor, sarcasm, helpfulness, companionship vs. assistant mode) and adapt its responses based on context and user preferences.

---

## 2. Decision Drivers

1. **Brain-inspired architecture:** The human brain solves similar problems (selective attention, threat detection, proactive response). Using it as a mental model provides coherent component design.

2. **Modularity and extensibility:** Sensors, skills, and personalities must be pluggable. New capabilities should be addable without redesigning core systems.

3. **Performance requirements:** Sub-second response latency for conversational feel. Efficient resource usage with dynamic loading/unloading.

4. **Team capabilities:** Small team with strong C# background, learning Python and Rust. Architecture should leverage existing skills while enabling growth.

5. **Scalable scope:** From single-app monitoring to full-system awareness. Memory and event handling must support unbounded event types.

6. **User privacy:** Data stays local to user's machine. User owns their data.

---

## 3. Decision

We adopt a brain-inspired, plugin-based modular architecture with polyglot implementation. Components are organized by function with language selection optimized for each component's requirements and the team's capabilities.

---

## 4. Architecture Overview

### 4.1 Brain-Inspired Design

The architecture models key brain systems:

| Brain Structure | System Component | Function |
|-----------------|------------------|----------|
| Sensory cortex | Sensor Layer | Perceive and preprocess inputs |
| Thalamus | Preprocessing/Fusion | Relay, gate, normalize sensory data |
| Amygdala + Insula | Salience Gateway | Evaluate importance, detect threats/opportunities |
| Hippocampus | Memory Controller | Store and retrieve memories |
| Prefrontal cortex | Executive | Decision-making, planning, personality |
| Motor cortex | Output Layer | Generate speech, text, actions |

### 4.2 Component Hierarchy

The system is organized into tiers based on activation patterns:

| Tier | Components | Activation |
|------|------------|------------|
| Tier 0: Always On | System Monitor, Orchestration | Lightweight, no models, always running |
| Tier 1: Context-Activated | App-specific sensors, domain skills | Loaded when target app/context active |
| Tier 2: User-Activated | Privacy-sensitive sensors (webcam, mic) | Explicitly enabled by user |

### 4.3 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATION (Rust)                            │
│  • Clock tick generation                                                │
│  • Component lifecycle                                                  │
│  • Message routing via gRPC                                             │
│  • Health monitoring                                                    │
│  • Exclusion zone enforcement                                           │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ gRPC
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────────────┐   ┌───────────────────┐
│  SENSORS (Python) │   │  SALIENCE + MEMORY        │   │  EXECUTIVE (C#)   │
│                   │   │  (Python)                 │   │                   │
│ • Audio           │   │                           │   │ • Semantic Kernel │
│ • Visual          │   │ ┌───────────────────────┐ │   │ • Attention mgmt  │
│ • Screen/OCR      │   │ │   Short-Term Buffer   │ │   │ • Action policy   │
│ • App events      │   │ │   (in-memory ring)    │ │   │ • Personality     │
│ • Future sensors  │   │ └───────────────────────┘ │   │ • Skill loading   │
│                   │   │                           │   │                   │
│ Emits: plain text │   │ ┌───────────────────────┐ │   │ Outputs:          │
│ observations      │   │ │  Long-Term (Postgres  │ │   │ • Text            │
│                   │   │ │  + pgvector, LOCAL)   │ │   │ • Speech (TTS)    │
│                   │   │ └───────────────────────┘ │   │                   │
└───────────────────┘   └───────────────────────────┘   └───────────────────┘
```

---

## 5. Language Decisions

| Component | Language | Rationale |
|-----------|----------|-----------|
| Orchestration | Rust | Long-running reliability, memory safety, excellent async. Learning opportunity with contained scope. |
| Sensors | Python | Unmatched AI ecosystem (Whisper, transformers, YOLO). C++ inference underneath means same speed as any language. |
| Salience Gateway | Python | Needs embedding models, small LLM. AI ecosystem advantage. Shares process with Memory for efficiency. |
| Memory | Python | Vector DB clients, embedding models. PostgreSQL via standard libraries. IPC overhead avoided by co-locating with Salience. |
| Executive | C# | Semantic Kernel (Microsoft-maintained). Strong OOP for complex state. Team's primary language. Type safety for personality/policy logic. |
| Output (TTS) | Python | TTS models (Piper, Coqui, Bark) are Python-first. |

### 5.1 Inter-Process Communication

Components communicate via gRPC, managed by the Rust orchestration layer. The Salience Gateway and Memory Controller share a process to avoid IPC overhead on the hot path (memory is accessed every tick).

**Transport abstraction:** Implement `ISensorTransport` interface with `GrpcTransport`, `WebSocketTransport`, `MqttTransport` implementations. Sensor manifest declares preferred transport. Enables future flexibility.

---

## 6. Module Architecture

### 6.1 Module Taxonomy

| Type | Purpose | Examples |
|------|---------|----------|
| Sensors | Perceive the world, emit events | Audio, Visual, App-specific |
| Skills | Extend AI capabilities or style | Sarcasm, Domain expertise |
| Personalities | Define base behavioral traits | Murderbot, Helpful Assistant |
| Outputs | How AI communicates/acts | TTS, Text |

### 6.2 Plugin Lifecycle

Modules follow a state machine:

```
┌─────────┐     activation      ┌──────────┐     ready      ┌────────┐
│UNLOADED │────triggered───────►│ LOADING  │───signal──────►│ ACTIVE │
└─────────┘                     └──────────┘                └────────┘
     ▲                                                           │
     │                                                           │
     │         ┌───────────┐      shutdown       ┌───────────┐   │
     └─────────│ UNLOADING │◄────triggered───────│ STOPPING  │◄──┘
               └───────────┘                     └───────────┘
                    │
                    │ state persisted
                    ▼
               ┌───────────┐
               │ SUSPENDED │  (state saved, can fast-resume)
               └───────────┘
```

Each plugin declares its requirements via manifest (YAML):
- Activation conditions (process name, window title, user request)
- Resource requirements (GPU, VRAM, models)
- Lifecycle settings (startup time, graceful shutdown, state persistence)

### 6.3 Sensor Manager Responsibilities

- **Discovery:** Scan plugin directory, load manifests, validate requirements
- **Activation:** Match context events to activation conditions, check resources, start process
- **Deactivation:** Graceful shutdown, state persistence, resource release
- **Health:** Monitor heartbeats, restart crashed modules, report status
- **Resource Arbitration:** Track VRAM/memory usage, queue or deny activations when resources insufficient

### 6.4 Skill Types

| Skill Type | Examples | Activation |
|------------|----------|------------|
| Style Modifiers | Sarcasm, formal, casual, poetic | Personality config or context |
| Personality Templates | Murderbot, Drill Sergeant, Jarvis | User selection |
| Domain Expertise | Minecraft strategy, coding patterns | Context-activated (sensor active) |
| Capability Extensions | Smart home, calendar management | User-enabled |

### 6.5 Plugin Directory Structure

```
/plugins
├── /sensors
│   ├── /minecraft
│   │   ├── manifest.yaml
│   │   ├── sensor.py
│   │   └── models/
│   ├── /vscode
│   └── /discord
├── /personalities
│   ├── /murderbot
│   │   ├── manifest.yaml
│   │   └── prompts/
│   └── /helpful_assistant
├── /skills
│   ├── /sarcasm_generator
│   │   ├── manifest.yaml
│   │   └── skill.py
│   └── /minecraft_expertise
└── /outputs
    ├── /tts_piper
    └── /tts_bark
```

---

## 7. Salience Gateway

### 7.1 Multi-Dimensional Salience Vector

Rather than a single composite score, salience is a vector of dimensions that the Executive uses for nuanced decision-making:

| Dimension | Range | Interpretation |
|-----------|-------|----------------|
| threat | 0-1 | Danger, urgency, needs immediate action |
| opportunity | 0-1 | Positive event worth noting/celebrating |
| humor | 0-1 | Joke potential, funny situation |
| novelty | 0-1 | New, unexpected, not seen before |
| goal_relevance | 0-1 | Relates to user's current activity |
| social | 0-1 | Involves other people, relationships |
| emotional | -1 to 1 | Negative to positive valence for user |
| actionability | 0-1 | AI can meaningfully help/contribute |
| habituation | 0-1 | Frequency of similar events (high = suppress) |

### 7.2 Extensible Dimensions

New dimensions can be added as capabilities grow:
- **time_pressure:** Event near deadline (calendar integration)
- **wellbeing:** User seems tired/stressed (health tracking)
- **teaching_moment:** Good opportunity to explain something
- **inspiration:** Creative opportunity detected

### 7.3 Executive Feedback Loop

The Executive can send modulation signals back to the Salience Gateway:
- **Suppress:** "I'm aware of this, stop alerting"
- **Heighten:** "Watch for X specifically"
- **Habituate:** "This is now normal, reduce salience"

---

## 8. Memory Architecture

### 8.1 Design Principles

- Data stays local to user's machine (PostgreSQL + pgvector)
- Handle both structured data (when schema is known) and unstructured data (when scope expands)
- Vector search is essential for semantic queries ("suspicious behavior", "user struggling")
- Design storage layer with abstraction for future backend swapping

### 8.2 Short-Term Memory (In-Process)

Hybrid structured index + tokenized payload for fast filtering and LLM injection:

| Field | Description |
|-------|-------------|
| id | UUID |
| timestamp | Event time (always present) |
| source | App/sensor that generated event (always present) |
| raw | Free text description (always present) |
| salience | JSON object with all salience dimensions (always present) |
| structured | Domain-specific fields (optional, varies by source) |
| tokens | Pre-tokenized for direct LLM context injection |

Queries filter by structured fields (source, time, salience thresholds), then inject tokenized payloads into LLM context.

### 8.3 Long-Term Memory (PostgreSQL + pgvector)

Four tables with different characteristics:

#### 8.3.1 Episodic Events
High-volume, append-only record of what happened. Includes embedding for semantic search, salience scores, and optional domain-specific structured fields.

**Lifecycle:** Archive old events, summarize into semantic facts during sleep cycle.

#### 8.3.2 Semantic Facts
Derived knowledge in subject-predicate-object form (e.g., "xX_Slayer_Xx is_hostile"). Includes confidence scores, source episode references, and supersession tracking.

**Lifecycle:** Update confidence, supersede when contradicted. Indefinite retention.

#### 8.3.3 User Profile
Traits about the user across dimensions (humor preference, communication style, interests). Uses EWMA (exponential weighted moving average) for adaptation:

```
short_term = α × new_observation + (1 - α) × short_term  // α = 0.3-0.5
long_term = β × short_term + (1 - β) × long_term         // β = 0.05-0.1, only when stable
```

**Prioritization:** System observations weighted higher than user self-reports.

**Lifecycle:** Indefinite, slowly evolving, high confidence threshold for changes.

#### 8.3.4 Entities
Known people, places, things with canonical names, aliases, types, and flexible attributes (JSONB). Supports cross-domain identity and relationship tracking.

**Lifecycle:** Merge duplicates, update attributes.

### 8.4 Memory Extraction Pipeline (Sleep Cycle)

Background processes run during configured "sleep" time:

| Process | Frequency | Function |
|---------|-----------|----------|
| Entity Extractor | Continuous | Identifies entity mentions, creates/updates records |
| Fact Extractor | ~10 min | Infers semantic facts, updates confidence |
| Profile Updater | ~daily | Analyzes episodes/facts, updates user traits |
| Consolidator | Nightly | Summarizes episodic → semantic, prunes low-salience |
| Archiver | Nightly | Marks old episodes archived |
| Integrity Check | Nightly | Hash verification, corruption detection |
| Backup | Nightly | Point-in-time backup |

### 8.5 Retention Policy

| Memory Type | Retention | Notes |
|-------------|-----------|-------|
| Episodic | Configurable | User can set duration; archived after threshold |
| Semantic | Indefinite | Core knowledge |
| User Profile | Indefinite | Evolves over time |
| Entities | Indefinite | Updated, merged |

---

## 9. Executive Module

### 9.1 Responsibilities

- **Attention Management:** Focus sphere, salience thresholds, interrupt policy
- **Action Policy:** Clock tick evaluation, probabilistic delay, response type selection
- **Personality Engine:** Base personality + loaded skills → response generation
- **Skill Orchestration:** Load/unload skills based on personality and context
- **Salience Modulation:** Send feedback to gateway (suppress, heighten, habituate)

### 9.2 Personality Matrix

Base traits are configurable per personality template:

| Trait | Range | Effect |
|-------|-------|--------|
| humor | 0-1 | Likelihood of jokes/wit |
| sarcasm | 0-1 | Caustic vs. sincere tone |
| formality | 0-1 | Casual vs. professional |
| proactive | 0-1 | How often to speak unprompted |
| enthusiasm | 0-1 | Energy level in responses |
| helpfulness | 0-1 | Willingness to assist |
| verbosity | 0-1 | Terse vs. detailed responses |

### 9.3 Context-Adaptive Personality

Traits can shift based on context:
- **High threat:** Increase proactive, decrease sarcasm, minimize verbosity
- **Opportunity:** Increase enthusiasm
- **User struggling:** Increase helpfulness, soften tone

### 9.4 User Personality Control

- Users can adjust settings in real-time
- Temporary overrides (duration-based, app-scoped) supported
- Changes require confirmation to prevent accidents
- Personality history maintained for rollback

---

## 10. User Control & Privacy

### 10.1 Data Locality

All user data stored locally on user's machine. Future option for user-controlled NAS/server.

### 10.2 Exclusion Zones

- Configurable list of apps/contexts to never monitor
- Stored in orchestrator config (not memory system)
- Enforced before sensor capture
- Pause/resume via keyboard shortcut with auto-resume option

### 10.3 Transparency

- Users can view memory contents
- Memory editing: correct facts, selective deletion by time/source/content
- Feedback mechanisms: thumbs up/down, text, voice

### 10.4 Right to Delete

Users can delete specific memories or time ranges.

---

## 11. Failure Handling

### 11.1 Sensor Crash

1. Continue without that sensor (graceful degradation)
2. Notify user
3. Log for debugging
4. Automatic restart attempts

### 11.2 Executive Timeout

- Timeout threshold enforced
- Fallback response reflecting personality (e.g., "Brainfart. Something important may have happened—I'm not sure what.")
- Late delivery acceptable if relevancy window hasn't passed
- Drop if no longer relevant (e.g., warning about attack after user already died)

### 11.3 Memory Corruption

- Nightly backups during sleep cycle
- Point-in-time recovery capability
- Periodic hash verification for corruption detection

### 11.4 Resource Exhaustion

1. Automatic unloading of lower-priority sensors
2. Notify user
3. Ask user to disable features (e.g., TTS)

---

## 12. Latency Budget

Target: ~1000ms end-to-end for conversational feel.

| Component | Target | Notes |
|-----------|--------|-------|
| Sensor capture | 50 ms | Continuous, non-blocking |
| Preprocessing/Fusion | 50 ms | Light transformation |
| Salience evaluation | 100 ms | Small model inference |
| Memory retrieval | 50 ms | Vector + structured query |
| Executive decision | 400 ms | Main LLM inference (bottleneck) |
| Response generation | 200 ms | Text formatting, skill application |
| TTS synthesis | 150 ms | Can stream for faster first audio |
| **Total** | **1000 ms** | |

---

## 13. Cold Start / Bootstrapping

### 13.1 New User Experience

- Default neutral personality with templates available for customization
- Allow user to provide self-description, but prioritize observed behavior
- Silent observation with EWMA-based adaptation (TCP/IP-inspired)
- Short-term observations affect immediate behavior
- Persistent patterns promote to long-term profile

### 13.2 Change Detection

After settling period, system monitors for behavioral changes:
- Short-term deviations handled via high-α EWMA
- If deviation persists, update long-term profile with low-β EWMA
- Enables adaptation without overreacting to temporary changes

---

## 14. Distributed Sensors (Future)

### 14.1 Latency Thresholds

| Latency | Handling |
|---------|----------|
| < 100ms | Process normally |
| 100-500ms | Process, flag as delayed |
| 500ms-2s | Process if relevant, warn of lag |
| > 2s | Drop or queue for background |

### 14.2 Reliability

- Sensors register on startup ("I'm present and ready")
- Graceful offline handling (mark unavailable, don't break system)
- Periodic reconnection attempts
- User notification of offline sensors

### 14.3 Security (Future)

Design with abstraction layer for future addition of:
- TLS
- API keys / certificates
- Encrypted payloads

---

## 15. Testing Strategy

| Type | Approach |
|------|----------|
| Subjective Quality | Human evaluation |
| Regression | Automated where possible; team sets criteria |
| Scenario Simulation | Team as users; direct conversation testing |
| Integration | End-to-end tests + contract testing for gRPC |

---

## 16. Design Patterns

### 16.1 Behavioral Patterns

| Pattern | Where | Justification |
|---------|-------|---------------|
| Strategy | Sensor transport, TTS engine, LLM backend | Swap implementations without changing consumers |
| Observer/Pub-Sub | Event flow sensors → salience → executive | Decouples producers from consumers |
| State Machine | Module lifecycle | Explicit states prevent invalid transitions |
| Pipeline | Sensor → Preprocessing → Salience → Executive | Each stage transforms and passes forward |
| Decorator | Skill stacking (sarcasm wraps base response) | Layer behaviors without modifying core |
| Circuit Breaker | Remote API calls | Fail fast when dependency is down |

### 16.2 Structural Patterns

| Pattern | Where | Justification |
|---------|-------|---------------|
| Repository | Memory access | Abstracts storage backend, enables swapping |
| Factory | Plugin loading | Create sensors/skills/personalities from manifests |
| Hexagonal/Ports & Adapters | Overall architecture | Core logic independent of I/O |
| Plugin Architecture | Sensors, skills, personalities, outputs | Extensibility without core changes |
| Sidecar | Per-sensor processes | Isolation, independent lifecycle |

### 16.3 Data Patterns

| Pattern | Where | Justification |
|---------|-------|---------------|
| CQRS | Memory system | Separate read (retrieval) from write (storage) paths |
| Event Sourcing | Episodic memory | Store events as source of truth, derive state |

---

## 17. Consequences

### 17.1 Positive

1. **Scalable scope:** Architecture handles single-app to full-system monitoring without redesign.
2. **Modular extensibility:** New sensors, skills, personalities added without core changes.
3. **Resource efficiency:** Dynamic loading means idle resources aren't consumed.
4. **Team skill leverage:** C# for complex logic, Python for AI, Rust for learning.
5. **Personality flexibility:** Rich personality system enables diverse AI characters.
6. **User privacy:** Local-first data storage, user owns their data.

### 17.2 Negative/Risks

1. **Polyglot complexity:** Three languages increases cognitive load and tooling requirements.
2. **IPC overhead:** Cross-process communication adds latency. Mitigated by co-locating hot-path components.
3. **Rust learning curve:** Orchestration development may be slower initially.
4. **Vector DB maintenance:** Embedding generation and index management add operational burden.

### 17.3 Neutral

1. **Brain metaphor limits:** Model is inspiration, not specification. Deviate where software can do better.
2. **Plugin interface stability:** Plugin manifest format will need versioning as requirements evolve.

---

## 18. Related Decisions

- ADR-0002: Hardware Requirements (pending)
- ADR-0003: Plugin Manifest Specification (pending)
- ADR-0004: Memory Schema Details (pending)
- ADR-0005: gRPC Service Contracts (pending)

---

## 19. Notes

This architecture emerged from iterative discussion exploring brain-inspired design, language tradeoffs, memory strategies, and plugin requirements. Key influences include the Murderbot Diaries personality concept and the recognition that semantic understanding (not just structured queries) is essential for general-purpose ambient awareness.

The design explicitly avoids over-engineering for the initial Minecraft scope while ensuring the foundations support the eventual full-system vision.

User profile adaptation uses TCP/IP-inspired EWMA algorithms for balancing responsiveness with stability.
