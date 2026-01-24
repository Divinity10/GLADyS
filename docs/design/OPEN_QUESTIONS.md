# Open Design Questions

This file tracks active architectural discussions that haven't yet crystallized into ADRs. It's shared between collaborators.

**Last updated**: 2026-01-23 (benchmark verification complete, dev workflow documented)

---

## Section Status Summary

**Quick navigation for architecture review phase.**

| Section | Topic | Status | Notes |
|---------|-------|--------|-------|
| §1 | Actuator/Effector Gap | ⚠️ Stale | Predates ADR-0011 - needs review |
| §2 | Continuous vs Discrete | 🟡 Open | Still underspecified |
| §3 | Tiered Actuator Security | 🟡 Open | Partially in ADR-0011 |
| §4 | Latency Budget Diversity | ✅ Resolved | See §11 |
| §5 | Learning System | ✅ Resolved | See ADR-0010 |
| §6 | Actuator System | ✅ Resolved | See ADR-0011 |
| §7 | Audit System | ✅ Resolved | See ADR-0012 |
| §9 | Plugin Taxonomy | 🟡 Open | DAG questions remain |
| §10 | Integration Plugin Model | ✅ Resolved | HA first approach |
| §11 | Latency Profiles | ✅ Resolved | Profiles defined |
| §12 | Cross-Cutting Integration | 🟡 Open | Still unresolved |
| §13 | Output Routing | 🔴 Gap | Not addressed in any ADR |
| §14 | Architectural Gaps | 🟡 Partial | Some resolved, some open |
| §15 | Deployment Model | 🔴 Gap | NEW - deployment configs, resource constraints |
| §16 | ADR-0004 Schema Gaps | 🟡 Partial | Some resolved, some open |
| §17 | Heuristic Condition Matching | ✅ Superseded | See §22 - fuzzy matching required for PoC |
| §18 | Orchestrator Language | ✅ Resolved | Python - see SUBSYSTEM_OVERVIEW.md §3, ORCHESTRATOR_IMPL_PROMPT.md |
| §19 | PoC vs ADR-0005 Gaps | 🟡 Open | Simplified contracts for MVP |
| §20 | TD Learning for Heuristics | 🟡 Open | Confidence updates designed in §22; feedback endpoint needed |
| §21 | Heuristic Storage Model | ✅ Resolved | Transaction log pattern for modifications |
| §22 | Heuristic Data Structure | ✅ Resolved | CBR + fuzzy matching + heuristic formation |
| §23 | Heuristic Learning Infrastructure | 🟡 Open | Credit assignment + tuning mode (deferred) |

**Legend**: ✅ Resolved | 🟡 Partially resolved / Open | 🔴 Critical gap | ⚠️ May be stale

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

## 14. Architectural Gaps (Identified 2026-01-18)

**Status**: Cataloged, needs triage
**Priority**: Varies

Gap analysis performed after ADR-0010/0011/0012 completion. These represent missing or underspecified components.

### High Priority (Core Architecture)

#### ✅ 14.1 Salience Subsystem (Resolved)
**Gap**: The central routing mechanism is referenced in ADR-0001 but never specified.

**Resolution**: ADR-0013 (Salience Subsystem) - covers pipeline architecture, attention budget, context profiles, Executive feedback, embedding model strategy, habituation decay.

#### ✅ 14.2 Executive Decision Loop (Resolved)
**Gap**: ADR-0001 shows Executive as a box, ADR-0010 provides System 1/2, but the actual decision algorithm isn't specified.

**Resolution**: ADR-0014 (Executive Decision Loop) - covers decision framework, personality integration, proactive scheduling, skill orchestration, output routing.

### Medium Priority (User Experience)

#### 14.3 Output Routing / User Presence
**Gap**: Executive decides WHAT to say; WHERE to deliver it is unspecified.

**Questions**:
- How is user presence detected?
- Device capability awareness?
- Escalation policy (tap shoulder → text → call)?
- Multi-user privacy on shared speakers?

**Recommendation**: ADR-0014 or detailed design doc

**Reference**: memory.md Section 13 (Output Routing and User Presence)

#### ✅ 14.4 Personality / Persona (Resolved)
**Gap**: How GLADyS "feels" to interact with is touched on in ADR-0001 but not specified.

**Resolution**: ADR-0015 (Personality Subsystem) - MVP uses Response Model only:
- **Response Model** (user-adjustable ±0.2): Communication traits (bipolar -1/+1), humor (frequency + weighted styles), affect, interaction
- **Two-tier customization**: Response (bounded by pack), Safety (full user control)
- Irony vs sarcasm distinction: irony is a communication mode affecting all speech, not just humor
- Pack-based monetization model with customization bounds
- **Forward-compatible**: Manifest supports optional `identity` block for future implementation

**Deferred**: Identity Model (Big 5 traits + derivation rules) preserved in [PERSONALITY_IDENTITY_MODEL.md](PERSONALITY_IDENTITY_MODEL.md) for future consideration if personality drift or pack quality issues emerge.

#### 14.5 Multi-User / Household
**Gap**: Mentioned as open question in ADR-0010 but it's architectural.

**Questions**:
- Whose preferences win when users conflict?
- Per-user profiles vs household consensus?
- Privacy between household members?
- Voice identification for personalization?

**Recommendation**: Design doc first, ADR when decisions solidify

### Lower Priority (Operational)

#### 14.6 Error Handling / Graceful Degradation
**Gap**: Scattered mentions but no coherent strategy.

**Questions**:
- What happens when subsystems fail?
- User communication about failures?
- Self-healing behaviors?
- Fallback chains?

**Recommendation**: Design doc

#### 14.7 Upgrade / Migration
**Gap**: Not addressed.

**Questions**:
- Schema migration for memory/audit?
- Plugin version compatibility?
- Rolling upgrades?

**Recommendation**: Defer until closer to v1.0

#### 14.8 Testing Strategy
**Gap**: Not addressed.

**Questions**:
- How do you regression test a learning system?
- Simulation environments?
- Preventing learned behavior drift?

**Recommendation**: Defer until implementation phase

### Documentation Gaps

- **GLOSSARY.md**: Created 2026-01-18 - defines terms from neuroscience, ML, and project-specific concepts
- ~~**PERSONALITY.md**: Needed~~ → Covered by ADR-0015 (Personality Subsystem)
- ~~**EXECUTIVE_LOOP.md**: Needed~~ → Covered by ADR-0014 (Executive Decision Loop)
- **PERSONALITY_IDENTITY_MODEL.md**: Created 2026-01-19 - preserves deferred Big 5 Identity Model design for future implementation
- **PERSONALITY_TEMPLATES.md**: Created 2026-01-19 - 11 test archetypes for personality validation

---

## 15. Deployment Model and Resource Constraints (Identified 2026-01-20)

**Status**: Open
**Priority**: High (affects architecture decisions)

### Problem

ADR-0001 states "local-first" but this doesn't address:
- What if user doesn't have a gaming rig?
- What combinations of local/network/cloud are supported?
- Where can the database live?
- What are minimum hardware requirements?

### Deployment Spectrum

| Configuration | Example | Implications |
|---------------|---------|--------------|
| **Fully local** | Gaming rig | Ideal. All processing on single machine. |
| **Local network** | Home server + client | Database/LLM on server, sensors on client. 1-5ms network latency. |
| **Remote cloud** | Cloud LLM API | Privacy concerns. 50-200ms network latency. Data residency questions. |

### Open Questions

1. **Minimum specs**: What hardware is required to run GLADyS at all?
2. **Database locality**: Can PostgreSQL be remote (local network or cloud)?
3. **LLM locality**: Local-only? Cloud fallback? User choice?
4. **Hybrid configurations**: Which components can be split across machines?
5. **Privacy vs performance trade-off**: When is remote acceptable? How does user control this?

### Relationship to ADRs

- **ADR-0001**: Says "local-first" but doesn't define deployment configurations
- **ADR-0008**: Security model assumes local processing but doesn't address network boundaries
- **ADR-0004**: Memory design assumes local database (50ms query target)

### What This Is NOT About

This is NOT about:
- Fine-tuning LLMs (learning happens in preference layer per ADR-0010, not model weights)
- Needing "model control" for self-learning (ADR-0010 uses EWMA + Bayesian, not LLM training)

The LLM is a black box. The question is: where does that black box live?

---

## 16. ADR-0004 Memory Schema Gaps (Identified 2026-01-19)

**Status**: Partially resolved (2026-01-19)
**Priority**: High (foundational)

Deep review of ADR-0004 against ADR-0007, ADR-0009, ADR-0010, ADR-0012 reveals significant gaps. ADR-0004 was written before the learning and compaction ADRs and needs reconciliation.

### 15.1 Schema Gaps (Missing Tables/Fields)

#### ✅ Bayesian Pattern Storage (Resolved)
**Gap**: ADR-0010 Section 3.3 specifies Bayesian model storage (`model_type`, `params`, `context_tags`, staleness tracking). ADR-0004 has no schema for this.

**Resolution**: Added `learned_patterns` table (ADR-0004 Section 5.5)

#### ✅ Heuristic Store (Resolved)
**Gap**: ADR-0010 Section 3.2 defines a Heuristic Store for System 1 fast rules. No table exists.

**Resolution**: Added `heuristics` table (ADR-0004 Section 5.6)

#### ✅ Feedback Events (Resolved)
**Gap**: ADR-0007 Section 4.3 defines `feedback_events` table. Not in ADR-0004.

**Resolution**: Added `feedback_events` table (ADR-0004 Section 5.7)

#### ✅ Episodes Table (Resolved)
**Gap**: No first-class episode entity - only `episode_id` reference on events.

**Resolution**: Added `episodes` table (Section 5.8) and `episode_events` junction table (Section 5.9)

#### ✅ Staleness Tracking (Resolved)
**Gap**: No staleness tracking on semantic_facts for drift detection.

**Resolution**: Added `observation_count`, `last_observed`, `expected_period`, `variance_recent` to `semantic_facts` (Section 5.2)

#### User Profile Schema Drift
**Gap**: ADR-0004's `user_profile` table has simple EWMA fields (`short_term`, `long_term`, `stability`). ADR-0007's `AdaptiveParameter` model adds:
- `bayesian_alpha`, `bayesian_beta` (Bayesian confidence)
- `bounds_min`, `bounds_max` (safety bounds)
- `frozen` (learning freeze)

**Need**: Reconcile schemas.

### 15.2 Cross-ADR Consistency Issues

#### ADR-0004 vs ADR-0009 (Compaction)
| Aspect | ADR-0004 | ADR-0009 | Action |
|--------|----------|----------|--------|
| Compaction policy | Nightly consolidation | Configurable tiers | ADR-0004 should defer to ADR-0009 |
| Summary storage | `summarized_into UUID` | Richer schema with `topic`, `salience_aggregate` | Add `memory_summaries` table |
| Provenance | `source_episodes UUID[]` | Hash-based minimal metadata | May need schema for hash provenance |

#### ADR-0004 vs ADR-0010 (Learning)
| Aspect | ADR-0004 | ADR-0010 | Action |
|--------|----------|----------|--------|
| Fact derivation | LLM-based `FactExtractor` | Pattern Detector subsystem | ADR-0010 implies structured pipeline |
| Confidence decay | Not mentioned | Staleness detection | ✅ Added staleness fields to semantic_facts |
| Context-aware beliefs | Not mentioned | Context-specific beliefs | Add context_tags |
| Learning profiles | Not mentioned | Per-domain learning rates | Extend user_profile |

#### ADR-0004 vs ADR-0012 (Audit)
**Critical distinction** (from design discussions): Audit is ground truth; memory can contradict.

**Gap**: ADR-0004 doesn't acknowledge this. Need guidance on when Executive queries Memory vs Audit:
- Memory: context, patterns, beliefs (mutable, may be wrong)
- Audit: "what actually happened" (immutable, always accurate)

### 15.3 Performance Concerns

#### HNSW Index on High-Volume Table
```sql
CREATE INDEX idx_episodic_embedding ON episodic_events
    USING hnsw (embedding vector_cosine_ops);
```
HNSW indices are expensive to maintain on append-heavy tables. Consider:
- Partial index (only non-archived)
- Index rebuild during sleep mode
- IVFFlat alternative (faster writes)

#### GIN Index on JSONB Salience
Slow to update on high-frequency writes. Consider extracting frequently-queried dimensions to dedicated columns.

#### Partition Boundary Management
ADR-0004 shows `FOR VALUES FROM (now() - interval '1 day')` but `now()` is evaluated at table creation. Need scheduled job for partition management (not specified).

### 15.4 Extensibility Concerns

#### Embedding Model Lock-in
`embedding vector(384)` hardcodes dimension to all-MiniLM-L6-v2. Switching models requires schema migration.

**Options**:
1. Make dimension configurable
2. Document migration strategy
3. Store embedding model ID alongside vector

#### Event Schema Versioning
`structured JSONB` is flexible but no:
- Schema registry for event types
- Validation strategy
- Versioning for format changes

#### Multi-User Support
ADR-0004 assumes single user. Multi-user households need:
- `user_id` on `user_profile`
- Privacy between household members
- Conflict resolution for entity interpretations

### 15.5 Open Questions

**High Priority**:
1. ✅ Where do Bayesian model parameters from ADR-0010 live? → `learned_patterns` table (Section 5.5)
2. How does Executive know when to query Memory vs Audit?
3. What's the embedding migration strategy when models change?
4. ✅ Where does `expected_period` for staleness come from? → Configured per-pattern, stored in learned_patterns/semantic_facts
5. How are context tags applied? Manual or automatic inference?

**Medium Priority**:
6. ✅ Under what load does L2 warm buffer become necessary? → Skip for MVP; add when flush latency >100ms observed
7. Who creates new time partitions? Scheduled job? Orchestrator?
8. When entities merge, who updates `entity_ids` arrays in `episodic_events`?
9. How does Memory Controller know when "sleep mode" is active?
10. Do L4 (cold) queries auto-warm results to L1?

**Lower Priority**:
11. What's the memory footprint of caching 1000 events with embeddings?
12. How efficient are cross-partition queries?
13. What's the write amplification from GIN indexes?

### 15.6 Recommended Changes

**Immediate (Pre-Implementation)**:
1. ✅ Add Bayesian storage schema for ADR-0010 learned patterns → `learned_patterns` (Section 5.5)
2. ✅ Add `feedback_events` table from ADR-0007 → Section 5.7
3. ✅ Add staleness tracking to `semantic_facts` → Section 5.2
4. Document Memory vs Audit query routing
5. Document partition management strategy

**Short-Term**:
6. Reconcile `user_profile` schema with ADR-0007's `AdaptiveParameter`
7. ✅ Add `heuristics` table for System 1 rules → Section 5.6
8. Define embedding migration strategy
9. Add `context_tags` to `semantic_facts`

**Medium-Term**:
10. ✅ Evaluate L2 necessity → Skip for MVP (decision documented in memory.md Section 18)
11. Design schema versioning for event types
12. Plan for multi-user support

### 15.7 Inspiration Sources

| Source | Relevance |
|--------|-----------|
| CPU Cache Hierarchy | Direct inspiration for L0-L4 design |
| LSM Trees (RocksDB) | Write-optimized storage, tiered compaction |
| Hippocampal Indexing Theory | Neuroscience basis for semantic/episodic split |
| Complementary Learning Systems | Fast episodic + slow semantic validates dual-store |
| Facebook FAISS | ANN search tradeoffs (IVF vs HNSW) |
| Pinecone Architecture | Metadata filtering + vector search |

---

## 17. Heuristic Condition Matching (Memory Subsystem)

**Status**: ✅ Superseded by §22
**Priority**: N/A
**Created**: 2026-01-21
**Superseded**: 2026-01-23 - Fuzzy matching via embeddings is required, not optional. See §22 for final design.

### Context

The Memory subsystem's Rust fast path includes heuristic lookup for System 1 responses. A heuristic has:
- **Condition**: When to fire (stored as JSONB)
- **Action**: What to do (stored as JSONB)
- **Confidence**: How reliable (0.0-1.0)

The question: How does the Rust fast path match an incoming event context against stored heuristic conditions?

### Design Decision: Simple Exact-Match for MVP

**Approach**: Start with exact key-value matching on condition fields.

A condition like:
```json
{"source": "discord", "event_type": "user_joined"}
```

Matches if the incoming event context has those exact values. Additional fields in the context are ignored (partial match).

**Rationale**:
1. Covers common use cases (source-specific rules, event-type rules)
2. Simple to implement in Rust (no complex query engine)
3. Fast (<1ms matching against cached heuristics)
4. JSONB schema allows future extension without migration

### Future Extensions (Not MVP)

When simple matching proves insufficient, consider:

| Extension | Use Case | Complexity |
|-----------|----------|------------|
| Pattern matching | `{"raw_text": {"$contains": "hello"}}` | Medium |
| Numeric comparisons | `{"temperature": {"$gt": 75}}` | Medium |
| Embedding similarity | `{"embedding_similar_to": <vector>}` | High |
| Boolean logic | `{"$or": [...], "$and": [...]}` | Medium |

### Implementation Notes

- Matching happens in Rust (`find_heuristics()` in [lib.rs](../../src/memory/rust/src/lib.rs:154))
- Heuristics are cached in L0 for fast access
- Python storage handles persistence; Rust handles hot-path matching
- When to implement: Phase 3 (Orchestrator integration) when the full event flow is wired up

### Open Questions

1. **Wildcard support**: Should `{"source": "*"}` match any source?
2. **Null handling**: Does missing field in context fail match or pass?
3. **Case sensitivity**: Is `"Discord"` == `"discord"`?
4. **Nested matching**: Support `{"context.user.role": "admin"}`?

### Relationship to Other Components

- **ADR-0010**: Defines heuristics as System 1 learned rules
- **ADR-0004**: Defines `heuristics` table schema (JSONB condition/action)
- **Orchestrator**: Will call Memory fast path to check for matching heuristics before invoking LLM

---

## 19. PoC Implementation vs ADR-0005 Spec Gaps

**Status**: Tracked for post-MVP
**Priority**: Low (intentional simplification)
**Created**: 2026-01-22

### Context

The PoC implementation uses simplified gRPC contracts compared to ADR-0005 specifications. This is intentional - the ADR defines the target architecture, while the PoC proves the core concept with minimal viable contracts.

### SalienceGateway Service

| Aspect | ADR-0005 §4.5 Spec | PoC Implementation |
|--------|--------------------|--------------------|
| Package | `gladys.v1` | `gladys.memory` |
| Service name | `SalienceGatewayService` | `SalienceGateway` |
| RPCs | `EvaluateEvent`, `EvaluateEventBatch`, `ModulateSalience` | `EvaluateSalience` only |
| Request | Full `Event` + `EvaluationContext` | Flat fields (event_id, source, raw_text, structured_json, entity_ids) |
| Response | Enriched event + relevant memories + user profile + should_process | Salience vector + from_cache + matched_heuristic_id |

### Rationale for Simplification

1. **Minimal viable path**: PoC needs to prove event → salience → routing works
2. **Avoid premature complexity**: Rich context can be added when needed
3. **Faster iteration**: Simpler contracts = faster debugging
4. **Memory retrieval deferred**: `relevant_memories` in response requires additional Memory integration

### Post-MVP Expansion Path

When expanding to full ADR-0005 spec:

1. Add `EvaluateEventBatch` for throughput optimization
2. Add `ModulateSalience` for Executive feedback loop
3. Expand request to include `EvaluationContext` (active goals, focus entities)
4. Expand response to include relevant memories and user profile snapshot
5. Migrate to `gladys.v1` package for consistency

### No Action Required

This is documentation of intentional scope limitation, not a bug or oversight.

---

## 20. Heuristic Learning via TD Learning (Reward Prediction Error)

**Status**: Open - needs minimal PoC design
**Priority**: High (core learning mechanism)
**Created**: 2026-01-23

### Context

ADR-0010 defines the Learning Pipeline with System 1 (heuristics) and System 2 (LLM reasoning). The question: **how do heuristics get created and updated from successful reasoning?**

Current heuristics are assumed to exist (stored in `heuristics` table per ADR-0004 §5.6), but the mechanism for:
1. Creating heuristics from novel reasoning
2. Updating heuristic confidence based on outcomes

...is underspecified.

### The Learning Loop (TD Learning)

The proposed mechanism follows **Temporal Difference (TD) Learning** - specifically reward prediction error:

```
1. Event arrives → SalienceGateway evaluates (current heuristics)
2. Orchestrator routes to Executive (System 2 reasoning)
3. Executive produces response/action
4. System observes OUTCOME
5. Compare: actual_outcome vs predicted_outcome
6. If outcome BETTER than prediction → strengthen heuristic / increase salience
7. If outcome WORSE than prediction → weaken heuristic / decrease salience
8. If novel pattern succeeds → CREATE new heuristic
```

**Key insight**: This is how biological brains work. The dopamine system signals prediction error, not reward itself. "Better than expected" drives learning, not "good outcome."

### Minimal PoC Requirements

To prove this architecture is achievable, we need:

#### 1. Outcome Tracking (Simplest Case)
**What**: Link an action to its observable outcome
**Minimal**: User feedback (thumbs up/down on response)
**Example**: "That fire warning was helpful" → positive outcome for threat→alert heuristic

#### 2. Prediction Recording
**What**: Before action, record what we expected to happen
**Minimal**: Store expected salience impact with each heuristic fire
**Example**: Heuristic H1 predicted "user will appreciate warning" with confidence 0.7

#### 3. Delta Calculation
**What**: Compare prediction to reality
**Minimal**: `delta = outcome_score - predicted_score`
**Example**: User thumbs-up (1.0) vs prediction (0.7) → delta = +0.3 → strengthen

#### 4. Confidence Update
**What**: Adjust heuristic confidence based on delta
**Minimal**: `new_confidence = old_confidence + learning_rate * delta`
**Example**: confidence 0.7 + (0.1 * 0.3) = 0.73

#### 5. Heuristic Creation (Stretch Goal)
**What**: When novel reasoning succeeds, extract pattern as new heuristic
**Minimal**: Log successful reasoning traces for manual pattern extraction
**Later**: LLM-assisted pattern extraction from successful traces

### What This Does NOT Require for PoC

- ❌ Automatic outcome detection (use explicit user feedback)
- ❌ Complex pattern extraction (log traces, create heuristics manually)
- ❌ Multi-step credit assignment (single action → single outcome)
- ❌ Causal inference (correlation is sufficient for PoC)

### Implementation Sketch

```
# Simplified flow for PoC

# On heuristic fire:
prediction = {
    "heuristic_id": "H123",
    "predicted_outcome": 0.7,  # confidence
    "timestamp": now(),
    "event_id": "E456"
}
store(prediction)

# On user feedback:
outcome = get_feedback(event_id="E456")  # 1.0 or 0.0
prediction = lookup_prediction(event_id="E456")
delta = outcome - prediction.predicted_outcome
update_heuristic_confidence(
    heuristic_id=prediction.heuristic_id,
    delta=delta,
    learning_rate=0.1
)
```

### Relationship to Existing ADRs

| ADR | Relevance |
|-----|-----------|
| ADR-0004 §5.6 | `heuristics` table has `confidence`, `fire_count`, `success_count` fields |
| ADR-0007 | EWMA for adaptive parameters - same principle applies to confidence |
| ADR-0010 | Learning Pipeline - TD learning fits into System 1 adaptation |
| ADR-0012 | Audit trail captures events for outcome correlation |

### Open Questions

1. **Outcome attribution**: When user says "that was helpful", which heuristic/action gets credit?
2. **Delayed feedback**: User reacts 10 minutes later - how to correlate?
3. **Negative outcomes**: How to detect "that was wrong" without explicit feedback?
4. **Heuristic extraction**: What pattern format makes sense for automated creation?
5. **Exploration vs exploitation**: Should system occasionally ignore heuristics to learn?

### Next Steps

1. Add `predictions` table to schema (minimal: heuristic_id, event_id, predicted_outcome, timestamp)
2. Add feedback endpoint to Executive (minimal: event_id + positive/negative)
3. Implement delta calculation and confidence update in Memory
4. Log reasoning traces for future heuristic extraction

### Why This Matters

Without TD learning, heuristics are static. With it, GLADyS can:
- Get better at threat detection over time
- Learn user-specific salience patterns
- Reduce LLM calls by strengthening reliable heuristics
- Self-correct when heuristics prove wrong

---

## 21. Heuristic Storage Model (Transaction Log)

**Status**: ✅ Resolved
**Priority**: High (foundational for learning)
**Created**: 2026-01-23

### Decision

Use a **transaction log pattern** for heuristic modifications:

- `heuristics` table: Current state only (fast to query)
- `heuristic_history` table: Append-only modification log (audit trail)

### Schema

```sql
-- Current state only
CREATE TABLE heuristics (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  condition_json JSONB NOT NULL,
  effects_json JSONB NOT NULL,       -- salience modifiers + actions
  confidence FLOAT DEFAULT 0.5,
  origin TEXT NOT NULL,              -- 'built_in', 'pack', 'learned', 'user'
  origin_id TEXT,                    -- pack ID, training ID, or null
  learning_rate FLOAT DEFAULT 0.1,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Append-only transaction log
CREATE TABLE heuristic_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  heuristic_id UUID REFERENCES heuristics(id),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  modification_type TEXT NOT NULL,   -- 'create', 'confidence_update', 'effects_change', 'revert'
  field_changed TEXT,                -- 'confidence', 'effects_json', etc.
  old_value JSONB,
  new_value JSONB,
  reason TEXT,                       -- 'positive_feedback', 'training', 'manual', 'pack_update'
  trigger_event_id UUID,             -- what caused this change
  user_id UUID                       -- for multi-user (nullable for MVP)
);

-- Index for common queries
CREATE INDEX idx_heuristic_history_heuristic_id ON heuristic_history(heuristic_id);
CREATE INDEX idx_heuristic_history_timestamp ON heuristic_history(timestamp);
```

### Rationale

| Concern | How Transaction Log Addresses It |
|---------|----------------------------------|
| **Fast lookup** | Query `heuristics` directly - no joins needed |
| **Revert capability** | Find last good state in history, apply |
| **Audit trail** | Full record of why/when changes happened |
| **Learning analysis** | Plot confidence over time from history |
| **Multi-user ready** | Add `user_id` to history; user-scoped views later |
| **Pack updates** | Compare origin version to current, merge or warn |
| **Debugging** | See exactly what changed and why |

### Modification Types

| Type | When Used |
|------|-----------|
| `create` | New heuristic added (from pack, learning, or user) |
| `confidence_update` | TD learning adjusted confidence |
| `effects_change` | Action or salience modifiers changed |
| `condition_change` | Matching condition was refined |
| `revert` | Rolled back to previous state |
| `disable` | Heuristic deactivated (not deleted) |

### Relationship to Other Systems

- **ADR-0012 (Audit)**: Similar append-only pattern; heuristic_history is learning-specific audit
- **ADR-0010 (Learning)**: TD learning writes to heuristic_history
- **feedback_events**: Trigger for confidence updates; linked via `trigger_event_id`

### Open for Future

- Multi-user: Add `user_id` to create user-scoped heuristic variants
- Pack versioning: Track which pack version created/modified a heuristic
- Conflict resolution: When pack updates conflict with user modifications

---

## 22. Heuristic Data Structure (CBR + Fuzzy Matching + Heuristic Formation)

**Status**: ✅ Resolved
**Priority**: High (foundational for PoC)
**Created**: 2026-01-23
**Updated**: 2026-01-23 - Revised to CBR approach with heuristic formation

### Context

Following §21 (Transaction Log), we needed to finalize the heuristic data structure. After design discussion, we chose **Case-Based Reasoning (CBR)** over behavior trees for PoC, as it's more brain-like and simpler to implement.

**Critical insight**: Without heuristic formation, GLADyS is just "a fancy chatbot" - it can respond, but it can't learn new patterns from experience.

### Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Approach** | Case-Based Reasoning (CBR) | More brain-like than behavior trees; well-studied |
| **Structure** | Flat list with competition | Highest (similarity × confidence) wins |
| **Matching** | Embedding similarity via pgvector | Without fuzzy logic, we're just an expert system |
| **Learning** | TD learning updates confidence | Heuristics improve based on feedback |
| **Formation** | LLM-assisted pattern extraction | Reasoning → Heuristic migration (the differentiator) |
| **Tree fields** | Keep in schema, don't implement | Forward-compatible for post-PoC |

### Why CBR Over Behavior Trees

| Aspect | Behavior Trees | CBR |
|--------|---------------|-----|
| Brain-like? | No (explicit control flow) | Yes (associative memory) |
| Conflict resolution | Tree traversal | Competition (winner takes all) |
| Learning | Modify tree structure | Adjust confidence weights |
| Complexity | Medium | Low |
| Interpretability | High (trace path) | Medium (see which fired) |

For PoC, CBR proves the core concept with less machinery. Tree structure can be added post-PoC if needed.

### Why Fuzzy Matching is Required

**Without fuzzy logic, GLADyS is just an expert system.** The PoC must prove brain-like semantic matching works.

Fuzzy matching enables:
- "That looks like fire" matching against learned fire patterns
- Novel inputs matching similar-enough stored conditions
- Gradual degradation (close match = lower confidence) instead of binary fail

### Heuristic Formation: The Differentiator

This is what makes GLADyS a brain, not a chatbot. Without it, we have static patterns that get tuned but never grow.

**Flow**:
```
1. Event arrives → no heuristic match → send to Executive (LLM)
2. Executive reasons → produces response
3. User provides feedback (positive/negative)
4. If positive: ask LLM to extract generalizable pattern
5. LLM outputs: condition description + action template
6. Generate embedding for condition text
7. Store as new heuristic with confidence=0.3 (low, must earn trust)
8. Next similar event → heuristic matches → LLM skipped
```

**Pattern Extraction Prompt**:
```
You just helped with this situation:

Context: {event context}
Your response: {llm response}
User feedback: positive

Extract a generalizable heuristic:
- condition: A general description of when this pattern applies
- action: What to do when the condition matches

Be general enough to match similar situations, specific enough to be useful.
Output as JSON: {"condition": "...", "action": {...}}
```

**Garbage Heuristic Mitigation**:
1. Low initial confidence (0.3) - must prove useful
2. TD learning reduces confidence if outcomes are bad
3. Manual review before activation (post-PoC option)

### Schema (Extends §21)

```sql
CREATE TABLE heuristics (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,

  -- Condition: fuzzy (embedding)
  condition_text TEXT,                    -- Human-readable, used for embedding
  condition_embedding VECTOR(384),        -- Semantic vector for fuzzy match
  similarity_threshold FLOAT DEFAULT 0.7, -- Min cosine similarity to match

  -- Effects (salience modifiers + actions)
  effects_json JSONB NOT NULL,

  -- Forward-compatible: tree structure (not implemented in PoC)
  next_heuristic_ids UUID[],              -- Reserved for future tree traversal
  is_terminal BOOLEAN DEFAULT true,       -- Reserved for future tree traversal

  -- Learning (from §21)
  confidence FLOAT DEFAULT 0.5,
  learning_rate FLOAT DEFAULT 0.1,
  origin TEXT NOT NULL,                   -- 'built_in', 'pack', 'learned', 'user'
  origin_id TEXT,                         -- Pack ID, reasoning trace ID, etc.

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector index for semantic search
CREATE INDEX idx_heuristics_embedding ON heuristics
  USING ivfflat (condition_embedding vector_cosine_ops);
```

### Matching Algorithm (CBR)

```
1. Generate embedding for incoming event context
2. Query pgvector: SELECT *,
     1 - (condition_embedding <=> input_embedding) as similarity
   FROM heuristics
   WHERE 1 - (condition_embedding <=> input_embedding) > similarity_threshold
3. Score each match: score = similarity × confidence
4. Winner = argmax(score)
5. Execute winner's effects_json
6. Log: heuristic_id, similarity, confidence, event_id (for observability)
```

### Prior Art

| System | What We Borrowed |
|--------|------------------|
| **Case-Based Reasoning** | Store examples, match by similarity, adapt |
| **Prototype Learning** | Similarity-based classification |
| **Associative Memory** | Pattern completion, competition |
| **k-NN** | Nearest neighbor for action selection |

### Example: Heuristic Formation Flow

```
Event: "Player health dropped to 15% while fighting skeleton"
→ No heuristic match (novel situation)
→ LLM Response: "Watch out! You're low on health. Consider healing."
→ User: 👍 (positive feedback)

Pattern Extraction:
LLM outputs: {
  "condition": "Player health critically low during combat",
  "action": {"type": "alert", "message": "Low health - consider healing"}
}

→ Generate embedding for "Player health critically low during combat"
→ Store heuristic:
  - origin: "learned"
  - origin_id: "reasoning_trace_abc123"
  - confidence: 0.3

Next time:
Event: "Player at 20% health fighting zombie"
→ Embedding similar to "Player health critically low during combat"
→ Heuristic fires → immediate alert → LLM skipped
```

### What This Proves (PoC Goals)

| Goal | How It's Proven |
|------|-----------------|
| Sensor → Response | Event flow through system |
| Fast path (heuristics) | Heuristic match skips LLM |
| Slow path (reasoning) | LLM handles novel situations |
| Fuzzy matching | Embedding similarity handles variation |
| Learning | Confidence updates from feedback |
| **Heuristic formation** | Reasoning traces become new heuristics |

### Tuning Levers

| Lever | Effect |
|-------|--------|
| Add examples | Cover more cases (via heuristic formation) |
| Remove examples | Eliminate bad patterns |
| Adjust confidence | Strengthen/weaken specific heuristics |
| Adjust similarity_threshold | Global or per-heuristic sensitivity |
| Learning rate | How fast feedback changes confidence |
| Initial confidence for new heuristics | How cautious about new patterns (default 0.3) |

### Observability (Post-PoC: "MRI" System)

For PoC, minimal logging:
- Which heuristic fired
- Similarity score
- Confidence at time of fire
- Event ID for correlation

Post-PoC expansion:
- Visualization of heuristic activations
- Confidence trends over time
- Heuristic formation history
- Reasoning trace viewer

### Relationship to Other Systems

| Component | Interaction |
|-----------|-------------|
| **Memory (Rust)** | Caches heuristics in L0; executes fast-path matching |
| **Memory (Python)** | Stores heuristics; generates embeddings for conditions |
| **SalienceGateway** | Returns matched heuristic effects as salience modifiers |
| **Executive** | Receives feedback; triggers pattern extraction |
| **TD Learning (§20)** | Updates confidence based on outcome feedback |
| **Transaction Log (§21)** | Records all heuristic modifications |

### Implementation Additions Needed

| Component | Status | Work |
|-----------|--------|------|
| LLM integration | ✅ Have it | - |
| Heuristic storage | ✅ Have it | - |
| Embedding generation | ✅ Have it | - |
| Feedback endpoint | ❌ Need it | Add `ProvideFeedback` to Executive proto |
| Pattern extraction prompt | ❌ Need it | LLM prompt engineering |
| Heuristic creation flow | ❌ Need it | Wire feedback → extraction → storage |

### Open for Future

- **Tree structure**: Schema supports `next_heuristic_ids`, implement when conditional branching needed
- **Compound actions**: Schema supports `effects_json` array, implement when needed
- **A/B testing**: Multiple heuristics compete for exploration vs exploitation
- **Automatic negative feedback**: Infer bad outcomes without explicit user input

---

## 23. Heuristic Learning Infrastructure (Deferred to Post-PoC)

**Status**: Open - deferred until prerequisites met
**Priority**: Medium (needed for real learning, not PoC)
**Created**: 2026-01-23

### Context

These items are required for production-quality heuristic learning but are deferred until the basic feedback loop is working end-to-end. The `feedback_events` table exists but nothing writes to it yet.

### 23.1 Credit Assignment (Feedback Time Window)

**Problem**: When a user says "that was helpful", which heuristic gets credit? The most recent? All heuristics fired in the last N seconds?

**Current state**: No feedback endpoint exists. The feedback → heuristic correlation isn't implemented.

**Design sketch**:
```python
# Config settings (now in config.py pattern)
FEEDBACK_TIME_WINDOW_SECONDS = 60  # How far back to look for heuristics
DEV_MODE = False  # Enable verbose logging of credit assignment

# On feedback:
1. Find all heuristic fires in last FEEDBACK_TIME_WINDOW_SECONDS
2. Weight by recency: newer = more credit
3. Update confidence for each weighted by credit share
4. If DEV_MODE: log full attribution breakdown
```

**Prerequisites**:
- `ProvideFeedback` RPC endpoint (implemented ✅)
- Feedback → event_id correlation (missing)
- Heuristic fire tracking (have `fire_count`, need timestamp log)
- `feedback_events` table writes (missing)

**Config settings to add**:
- `FEEDBACK_TIME_WINDOW_SECONDS`: How far back to attribute credit (default: 60)
- `FEEDBACK_RECENCY_DECAY`: Exponential decay factor for older events (default: 0.5)
- `DEV_MODE`: Enable verbose logging of all attribution decisions

### 23.2 Tuning Mode (Near-Miss Logging)

**Problem**: How do you tune similarity thresholds? You need to see what *almost* matched but didn't.

**Current state**: Heuristic matching only logs fires, not near-misses.

**Design sketch**:
```python
# Config settings
TUNING_MODE = False
TUNING_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]  # Show what would match at each

# On event evaluation:
if TUNING_MODE:
    for threshold in TUNING_THRESHOLDS:
        matches = query_heuristics(similarity > threshold)
        log.info(f"At threshold {threshold}: {len(matches)} matches")
        for m in matches:
            log.info(f"  - {m.name}: sim={m.similarity:.2f}, conf={m.confidence:.2f}")
```

**Prerequisites**:
- Significant event traffic through SalienceGateway
- Heuristics with meaningful conditions (not just test data)
- Observability infrastructure (ADR-0006 stack)

**Config settings to add**:
- `TUNING_MODE`: Enable near-miss logging (default: False)
- `TUNING_THRESHOLDS`: List of thresholds to evaluate (default: [0.5, 0.6, 0.7, 0.8, 0.9])
- `TUNING_LOG_LEVEL`: Logging verbosity for tuning output (default: INFO)

### Why Deferred

| Item | Prerequisite | Status |
|------|-------------|--------|
| Credit assignment | Feedback endpoint | ✅ Implemented |
| Credit assignment | Event → heuristic fire log | ❌ Missing |
| Credit assignment | `feedback_events` writes | ❌ Missing |
| Tuning mode | Real traffic | ❌ Need integration test load |
| Tuning mode | Meaningful heuristics | ❌ Only test heuristics exist |

### When to Revisit

Revisit credit assignment when:
1. Integration tests show feedback flowing end-to-end
2. At least 3 heuristics exist and are being evaluated
3. User can trigger explicit feedback via Executive

Revisit tuning mode when:
1. Running load tests or real workloads
2. Threshold tuning is actively needed
3. Observability stack (Grafana/Loki) is deployed

### Relationship to Other Systems

| System | Interaction |
|--------|-------------|
| **Config (config.py)** | Will add settings for both features |
| **feedback_events table** | Credit assignment writes here |
| **heuristic_history table** | Records confidence changes from credit |
| **Observability (ADR-0006)** | Tuning mode logs go to Loki |
| **§20 (TD Learning)** | Credit assignment feeds into confidence updates |
| **§22 (CBR Schema)** | Tuning mode evaluates against this schema |

---

## How to Use This File

1. Add new questions when architectural gaps are identified
2. Update status as discussions progress
3. Move to "Recently Resolved" when an ADR is created or decision is made
4. Reference ADR number when resolved
