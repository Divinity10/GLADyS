# Open Design Questions

This file tracks active architectural discussions that haven't yet crystallized into ADRs. It's shared between collaborators.

**Last updated**: 2026-01-18

---

## 1. Actuator/Effector Subsystem Gap

**Status**: Identified, needs ADR
**Priority**: High
**Proposed**: ADR-0010

### Problem

The architecture shows sensors (input) flowing to Executive which produces speech (TTS output). But GLADyS should also control physical devices:
- Thermostats
- Fans / HVAC
- Humidifiers / dehumidifiers
- Smart lights
- Door locks (high security concern)

**Gap**: No actuator plugin type exists. Skills provide knowledge to Executive, not device control.

### Open Questions

- Should actuators be a new plugin type or an extension of skills?
- What's the command validation / safety bounds model?
- Rate limiting to prevent oscillation (don't toggle thermostat 100x/minute)?
- Confirmation requirements for high-impact actions (door locks)?
- How does the Executive "decide" to actuate vs. speak?

### Possible Approaches

1. **Actuators as new plugin type** - Parallel to sensors and skills, with own manifest schema
2. **Actuators as skill extension** - Skills gain "execute" capability alongside "query"
3. **Actuators via external integration** - Home Assistant / MQTT bridge, not native plugins

---

## 2. Continuous vs. Discrete Data

**Status**: Identified, needs resolution
**Priority**: Medium

### Problem

Salience gateway and memory are designed for **discrete events** ("player took damage"). Environmental sensors produce **continuous streams** (temperature every 5 seconds).

### Open Questions

- Does a temperature reading have "salience"?
- Should 72°F → 73°F enter salience evaluation at all?
- How does episodic memory model time-series data?
- Should continuous data be pre-filtered into discrete events at the sensor?

### Possible Approaches

1. **Sensor-side filtering** - Sensors emit events only on threshold crossings (sensor responsibility)
2. **New data type** - "Metric" type that bypasses salience, goes directly to memory/executive
3. **Salience learns** - Gateway learns to filter low-information continuous data (ML approach)
4. **Hybrid** - Continuous data stored separately, but threshold events enter salience pipeline

---

## 3. Tiered Actuator Security

**Status**: Identified, needs analysis
**Priority**: High (if actuators proceed)

### Problem

ADR-0008 security model is good for data privacy, but physical actuators have different risk profiles:

| Plugin Type | Risk if Compromised |
|-------------|---------------------|
| Game sensor | Annoyance |
| Screen capture | Privacy violation |
| Thermostat | Comfort / pipe freeze |
| Door lock | Physical security breach |

### Open Questions

- Should physical security actuators (locks, garage doors) require higher trust than entertainment plugins?
- Should there be an "actuator trust tier" separate from sensor trust?
- What confirmation UX for dangerous actions?

---

## 4. Latency Budget Diversity

**Status**: Identified, minor concern
**Priority**: Low

### Problem

ADR-0005 defines 1000ms end-to-end budget optimized for conversational gaming. IoT has different needs:
- Safety-critical (smoke alarm): <100ms
- Comfort (thermostat): Can be slow, SHOULD be slow to avoid oscillation

### Open Questions

- Should different event types have different latency budgets?
- How to express this in the architecture without over-engineering?

---

## 5. Learning System Design (ADR-0010)

**Status**: ADR stub created, needs fleshing out
**Priority**: High

### Open Questions

1. **Trigger model**: What triggers learning? Continuous background, periodic batch, or event-driven?
2. **Online vs batch**: Learn incrementally as data arrives, or reprocess periodically?
3. **Feedback loop**: How does the system know if a learned pattern was correct?
4. **Conflicting evidence**: How handle "observation A says X, observation B says not-X"?
5. **Causal vs correlational**: Do we distinguish "X causes Y" from "X and Y coincide"? How?
6. **Computational budget**: Background process or real-time constraints?
7. **Cold start**: New user/environment - what bootstraps learning?

---

## 6. Actuator System Design (ADR-0011)

**Status**: ADR stub created, needs fleshing out
**Priority**: High

### Open Questions

1. **Plugin model**: New plugin type or extend skills?
2. **Command validation**: What prevents dangerous commands?
3. **Rate limiting**: How prevent oscillation (thermostat toggling)?
4. **Feedback**: How do actuators report success/failure? Sync or async?
5. **Dependencies**: Model "can't AC if window open" - how?
6. **Conflict resolution**: Two commands conflict - which wins?
7. **Latency budget**: Same 1000ms as speech or different?
8. **Confirmation UX**: High-impact actions (locks) - require confirmation?

---

## 7. Audit System Design (ADR-0012)

**Status**: ✅ Resolved - see ADR-0012
**Priority**: High

### Resolved (see ADR-0012 Section 3)

1. ✅ **Retention policy**: Per-event-type, configurable (-1=forever, >0=N days, 0=don't audit)
2. ✅ **Tamper protection**: Tiered - Merkle trees for security events, hash-per-record for actions
3. ✅ **User control**: Query + export; no delete before retention expiry; policy hierarchy
4. ✅ **Storage growth**: Tiered storage (hot/warm/cold) with automatic transitions
5. ✅ **Query interface**: Separate from memory (time-range + event-type focused)
6. ✅ **Cryptographic integrity**: Merkle trees for audit_security table

### Remaining Open

1. Plugin manifest schema for declaring emitted event types
2. Export format (JSON lines vs Parquet)
3. Merkle tree implementation choice
4. Cross-device audit sync

---

## 9. Plugin Taxonomy and Processing Pipeline

**Status**: Under discussion, impacts ADR-0003
**Priority**: High

### Problem

The current ADR-0003 defines sensors and skills, but the distinction is unclear. Additionally, skills may need to operate at different points in the processing pipeline (pre-salience vs on-demand).

### Proposed Taxonomy

| Type | Direction | Trigger | Purpose |
|------|-----------|---------|---------|
| **Sensor** | World → Brain | Push (continuous/threshold) | Produces **events** that enter salience gateway |
| **Skill** | Brain ↔ Brain | Varies by subtype | Transforms, analyzes, or provides knowledge |
| **Actuator** | Brain → World | Push (command) | Executes **commands** that change the world |

### Skill Subtypes

Skills are not monolithic - they have different roles:

| Subtype | When it runs | Purpose | Examples |
|---------|--------------|---------|----------|
| **Preprocessor** | Pre-salience (on sensor output) | Transform/enrich raw sensor data | Movement detection, STT, tone analysis, OCR |
| **Query** | On-demand (Executive calls) | Answer questions during reasoning | Knowledge lookup, calculation, API query |
| **Analyzer** | Either | Complex assessment | Threat detection, comfort evaluation |

### Processing Pipeline (Brain-Inspired)

Preprocessors form a DAG, not a linear chain. Like specialized brain cells, some run in parallel, others sequentially:

```
Audio Stream
     │
     ├──→ [Word Recognition] ──┬──→ [Semantic Meaning] → Salience
     │                         │
     └──→ [Tone Detection] ────┘
```

Manifest declares dependencies:
```yaml
plugin_id: semantic_meaning_detector
type: skill
subtype: preprocessor
requires:
  - word_recognition.transcript
  - tone_detection.emotion
```

### Performance Requirements

Preprocessors are latency-critical (hot path):

| Stage | Budget | Rationale |
|-------|--------|-----------|
| Raw sensor → Preprocessor | <50ms | Perceptible lag starts ~100ms |
| Preprocessor chain total | <200ms | Leave room for salience + Executive |
| Full end-to-end | <1000ms | ADR-0005 budget |

Consider: ONNX/TensorRT for edge-optimized models, async execution with caching for heavy ML.

### DAG Design Decision

**Decision**: Design for full DAG from the start (manifest schema, orchestrator interface). Implementation can evolve.

**Rationale**:
- UC3 (Voice) needs parallel STT + Tone from day 1
- UC6 (Multi-modal) likely early - screen + audio fusion
- Boxing ourselves into linear costs more than DAG upfront design
- Manifest declares dependencies; orchestrator builds execution graph

**What this means**:
- Manifest schema supports `requires: [plugin.output, ...]` from day 1
- Orchestrator interface assumes DAG scheduling
- Initial scheduler implementation can be simple (topological sort)
- Complex optimizations (parallel execution, caching) added when metrics justify

### Open Questions

1. **Unified vs separate types**: Should preprocessors be a skill subtype or a fourth plugin type?
2. **Caching strategy**: How cache expensive preprocessor results?
3. **Error handling**: Preprocessor fails - skip it or block the pipeline?
4. **Hot-swap**: Can preprocessors be updated without restarting the system?
5. **DAG validation**: How detect cycles or missing dependencies at manifest load time?
6. **Timeout propagation**: If one node times out, how does it affect downstream nodes?

---

## 10. Integration Plugin Model

**Status**: Resolved (approach selected)
**Priority**: High

### Problem

Most smart home devices connect through ecosystems (Home Assistant, Google Home, Amazon Alexa), not directly. This changes our plugin architecture:

- We don't need hundreds of individual device plugins
- We need **integration plugins** that bridge to these ecosystems
- Each integration exposes many virtual sensors and actuators

### Decision: Start with Home Assistant

| Factor | Home Assistant | Google/Amazon |
|--------|---------------|---------------|
| **Philosophy** | Local-first, privacy-focused | Cloud-dependent |
| **Device breadth** | 2000+ integrations | Large but walled garden |
| **API stability** | Open, well-documented | Proprietary, can change |
| **Development velocity** | Can iterate without account approval | OAuth flows, certification |
| **GLADyS alignment** | Privacy, user control, local processing | Convenience, but cloud dependency |

**Strategy**: Design generic `Integration` interface, implement Home Assistant first, add Google/Amazon when user demand justifies.

### Proposed Integration Manifest

```yaml
plugin_id: home_assistant
type: integration
version: 1.0.0

connection:
  type: websocket
  url: ws://homeassistant.local:8123/api/websocket
  auth: long_lived_token  # reference to secure credential store

expose:
  sensors:
    - entity_id: sensor.living_room_temperature
      as: living_room_temp
      unit: celsius

    - entity_id: binary_sensor.front_door
      as: front_door_open

  actuators:
    - entity_id: climate.nest_thermostat
      as: thermostat
      trust_tier: comfort
      capabilities:
        - set_temperature
        - set_hvac_mode
      rate_limit: 1/minute

    - entity_id: lock.front_door
      as: front_door_lock
      trust_tier: security  # → routes to audit_security table
      capabilities:
        - lock
        - unlock
      confirmation_required: true
```

### Key Design Points

1. **Per-device trust tiers**: Lock is `security`, thermostat is `comfort` - configured in mapping
2. **Rate limiting per actuator**: Prevents oscillation at device level
3. **Confirmation requirements**: High-risk actuators can require user confirmation
4. **Virtual sensors/actuators**: GLADyS sees `front_door_lock`, not `lock.front_door` - abstraction layer

### Open Questions

1. **Credential storage**: Where do long-lived tokens go? (Coordinate with ADR-0008)
2. **Entity discovery**: Auto-discover HA entities or require explicit mapping?
3. **State sync**: How often to poll HA for state changes vs. websocket push?
4. **Offline handling**: HA unavailable - how does GLADyS degrade gracefully?

---

## 11. Latency Profiles (Cross-Cutting)

**Status**: ✅ Resolved
**Priority**: High (critical for orchestrator scheduling)

### Problem

Current latency specs are scattered and too rigid:
- ADR-0005: Fixed 1000ms conversational budget
- ADR-0011: Per-action-type budgets (user-requested, reactive, proactive)
- Section 9: Preprocessor budgets (<50ms/stage)

But latency requirements are **context/domain-driven**, not just operation-type-driven:
- PvP gaming sensor needs <500ms end-to-end
- Thermostat can be slow (and SHOULD be slow to avoid oscillation)
- Safety systems need fast response
- Background learning can be async

Without this, the orchestrator can't prioritize correctly.

### Decision: Latency Profiles

| Profile | End-to-End | Preprocessor Chain | Use Cases |
|---------|------------|-------------------|-----------|
| `realtime` | <500ms | <100ms total | PvP gaming, safety alerts, threat detection |
| `conversational` | <1000ms | <200ms total | Voice interaction, general Q&A |
| `comfort` | <5000ms | <500ms total | Thermostat, lighting, non-urgent IoT |
| `background` | Best-effort | Async OK | Learning, batch analysis, reporting |

### How It Flows (Pull Model)

**Key insight**: Latency requirements flow from ACTION → SENSOR (pull), not sensor → action (push).

1. **Sensors** are agnostic - reusable by any feature, don't declare latency profile
2. **Features/Actions** declare their latency requirements
3. **Validation at startup**: System benchmarks the full chain, fails to load if exceeds budget
4. **Orchestrator** schedules based on profile priority

### Two-Layer Feature Model

| Layer | Description | Validation |
|-------|-------------|------------|
| **Bundles** | Developer ships sensor + preprocessors + skills together | Pre-validated by developer |
| **User-defined** | User composes plugins via configuration | System validates at startup |

### Latency Cost Discovery

Latency costs are **discovered at deployment**, not declared in manifest:
- Performance depends on hardware
- System benchmarks chains at startup
- If benchmark exceeds feature's latency budget → fail to load with error

### Override Hierarchy

```
System Default → Feature/Actuator Override → User Override
```

Example: `realtime` default is <500ms, but a gaming actuator might override to <1000ms, and user could further override to <2000ms.

### Graceful Degradation (Runtime Overload)

When system is overloaded at runtime:

1. **Priority queuing**: `realtime` > `conversational` > `comfort` > `background`
2. **Background suspension**: `background` work pauses entirely under load
3. **Skip optional**: `enhances_with` stages can be dropped when pressed
4. **Single notification**: Warn user once on sustained overload (not spammy)
5. **Safety carve-out**: `realtime` safety events (smoke, security) get dedicated budget - NEVER degraded

### Resolved Questions

1. ✅ **Profile inheritance**: Pull model - features validate their chains, sensors are agnostic
2. ✅ **Mixed profiles**: Same sensor can serve multiple features; each feature validates independently
3. ✅ **Profile degradation**: Priority queuing + background suspension + skip optional + safety carve-out
4. ✅ **Measurement**: Discovery at deployment (benchmarked, not declared)
5. ✅ **Configuration**: Override hierarchy (System → Feature → User)

### Remaining Work

- Security review needed: malicious plugins claiming `background`, bundle trust verification, unsafe user compositions
- ADR-0005: Needs update to define profiles instead of single 1000ms budget
- ADR-0011: Actuator latency becomes profile-based
- Section 9: Preprocessor latency becomes profile-based

---

## 12. Cross-Cutting Integration Questions

**Status**: Open
**Priority**: Medium

### Open Questions

1. **Executive decision**: How choose between speak vs actuate vs both vs neither?
2. **Continuous data**: Temperature every 5s - how enter system without flooding salience?
3. **MVP scope**: Minimum to prove architecture works?
4. **Testing strategy**: Learning systems are non-deterministic - how test?

---

## 13. Output Routing and User Presence

**Status**: Identified, needs design
**Priority**: High

### Problem

The Executive decides WHAT to communicate. But we haven't specified WHERE:

```
Executive → "Someone's at the door" → Output Router → ???
                                            │
                                            ├─→ Computer speakers (if at desk)
                                            ├─→ Google Home (if in that room)
                                            ├─→ Phone notification (if away)
                                            └─→ Smart display (show video + audio)
```

Output is distinct from actuators:
- **Actuator**: changes physical state (thermostat, lock)
- **Output**: delivers information TO the user (speech, notification, display)

### Design Inspiration Sources

| Domain | Relevant Concepts | What It Offers |
|--------|-------------------|----------------|
| **Biology** | Motor neurons, proprioception | Brain learns which "muscle" to activate; body awareness |
| **Cellular/WiFi** | Handoff, roaming, signal strength | User "roams" between devices; follow seamlessly |
| **Networking (QoS)** | Priority queues, traffic classes | Urgent messages get different treatment |
| **Pub/Sub** | Topic subscriptions, routing | Devices subscribe to message types |
| **Human Assistant** | Escalation, context awareness | Adapts channel to situation |
| **Service Mesh** | Retry policies, failover | If first output fails, try another |

### Proposed: Hybrid Model

Combine the best from each domain:

1. **Presence detection** (cellular/wifi) - Track which devices the user is near
2. **Device capabilities** (IoT) - This device has display, that one is audio-only
3. **Message priority** (QoS) - Security alert vs routine notification
4. **Subscription model** (pub/sub) - User preferences: "always send X to phone"
5. **Escalation** (human assistant) - No response on speaker → try phone
6. **Learning** (biology) - Over time, learn "Scott responds faster from X at time Y"

### Human Assistant Analogy

A good human assistant would:
- Tap your shoulder if you're right there
- Call your name if you're in another room
- Text if you're away
- Escalate if urgent and no response

GLADyS should behave similarly.

### Routing Factors

| Factor | Source | Example |
|--------|--------|---------|
| **User location** | Presence sensors, device activity | Keyboard active → at computer |
| **Device availability** | Health checks | Google Home reachable? |
| **Message priority** | Event type | Security = high, routine = low |
| **Time of day** | Clock | 2am → silent notification, not speaker |
| **User preferences** | Configuration + learned | "Security events always to phone" |
| **Content type** | Message metadata | Video doorbell → device with display |
| **Response history** | Learning | "Scott responds from phone evenings" |

### Output Device Types

| Type | Capabilities | Examples |
|------|--------------|----------|
| **Audio** | Speech, tones | Computer speakers, Google Home |
| **Visual** | Text, images, video | Phone notification, smart display |
| **Haptic** | Vibration | Phone, smartwatch |
| **Multi-modal** | Audio + Visual | Smart display, phone |

### Open Questions

1. **Presence detection**: What signals indicate user location? (motion, device activity, GPS)
2. **Escalation policy**: How long to wait before trying next device?
3. **Multi-user**: Multiple users in household - route to correct person?
4. **Privacy**: Don't announce sensitive info on shared speaker?
5. **Output as plugin?**: Is the output router a plugin, or core system?
6. **Acknowledgment**: How know if user received the message?
7. **Do Not Disturb**: User/device-level DND modes?

### Relationship to Actuators

Output devices could be modeled as actuators with special semantics:
- `type: output` vs `type: actuator`
- Or: Output router as separate subsystem that USES actuators

Decision needed: unified model or separate concepts?

---

## Recently Resolved

### 2026-01-18: Audit System Design (ADR-0012)

**Architecture**:
- Audit lives OUTSIDE brain, but readable by it
- Append-only, no compaction, immutable
- Brain can READ audit for context but cannot MODIFY

**Storage**:
- Three tiered tables: `audit_security` (Merkle), `audit_actions` (hash), `audit_observations` (light)
- Event type taxonomy: `category.subject.action` with `source` as separate field
- Tiered storage: hot (SSD) → warm (HDD) → cold (archive)

**Retention**:
- Per-event-type, configurable: -1=forever, >0=N days, 0=don't audit
- Policy hierarchy: System Defaults → Org Policy (locked) → User Preferences
- Security events default to forever; sensor observations default to 30 days

**Access**:
- Separate query interface from memory (structured, not semantic)
- No delete before retention expiry (no exceptions)

See ADR-0012 for full specification.

---

## Reference: Validation Use Cases

These concrete scenarios help validate design decisions. Each should work cleanly with our architecture.

### UC1: Gaming Companion (Aperture)

```
[Game State Sensor] → [Threat Analyzer Skill] → Salience → Executive → Speech
                                                                    ↘ [Game Input Actuator]
```

- Sensor: Reads player health, position, inventory via Aperture API
- Preprocessor: None (structured data)
- Skill: Threat analyzer ("enemies nearby?")
- Executive: Decides to warn player or suggest action
- Actuator (future): Send game commands

### UC2: Environmental Comfort

```
[Temp Sensor] ─────┐
[Humidity Sensor] ─┼→ [Comfort Analyzer] → Salience → Executive → [HVAC Actuator]
[CO2 Sensor] ──────┘
```

- Sensors: Push readings on threshold (not every 5s)
- Skill: Comfort analyzer combines inputs
- Executive: "It's getting warm, should I turn on AC?"
- Actuator: Set thermostat, turn on fan

**Design validation**: How does the comfort analyzer get all three sensor readings? Does it poll memory, or are inputs routed to it?

### UC3: Voice Interaction

```
[Microphone] → [STT Preprocessor] ──┬→ [Semantic Meaning] → Salience → Executive → [TTS]
                                    │
              [Tone Preprocessor] ──┘
```

- Sensor: Microphone captures audio stream
- Preprocessors (parallel): STT → text, Tone → emotion
- Preprocessor (sequential): Semantic meaning from text + tone
- Executive: Responds with appropriate tone

**Design validation**: DAG preprocessor model. Can STT and Tone run in parallel? How does Semantic know when both are ready?

### UC4: Physical Security (High-Risk)

```
[Motion Sensor] → [Person Detector] → Salience → Executive → [Door Lock Actuator]
                                                          ↘ User Confirmation
```

- Sensor: Camera or motion detector
- Preprocessor: Person detection (is someone there?)
- Executive: Decides whether to lock/unlock
- Actuator: Door lock (SECURITY TIER - Merkle audit)
- UX: Requires user confirmation for unlock

**Design validation**: Tiered trust model. Lock commands go to audit_security table. Confirmation flow.

### UC5: Continuous Monitoring (Edge Case)

```
[Temp Sensor every 5s] → ??? → Memory (time-series) → Executive (on query)
```

- Sensor: Temperature every 5 seconds
- Problem: Does every reading go through salience? (No)
- Solution options:
  - Sensor emits only on threshold crossing
  - Separate "metric" path that bypasses salience
  - Preprocessor filters to significant changes

**Design validation**: Continuous vs discrete data handling.

### UC6: Multi-Modal Analysis

```
[Screen Capture] → [OCR] ────────────┐
                                     ├→ [Context Analyzer] → Salience → Executive
[Audio] → [STT] → [Speaker ID] ──────┘
```

- Multiple sensors + preprocessor chains
- Context analyzer combines visual + audio
- Executive has rich multimodal context

**Design validation**: Complex DAG, multiple sensor sources merging.

---

## How to Use This File

1. Add new questions when architectural gaps are identified
2. Update status as discussions progress
3. Move to "Recently Resolved" when an ADR is created or decision is made
4. Reference ADR number when resolved
