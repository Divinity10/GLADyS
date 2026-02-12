# GLADyS Glossary

Terms and concepts used in GLADyS design. Many derive from neuroscience, reflecting the brain-inspired architecture.

---

## Architecture

### Executive
The decision-making component of GLADyS. Receives filtered, processed information from salience and decides what to do: speak, actuate, stay silent, or ask for clarification. Implemented as an LLM with access to memory and learned heuristics.

See: ADR-0001, ADR-0010

### Orchestrator
The core that manages event routing, scheduling, and system coordination. The "nervous system" that connects components but doesn't make decisions.

See: ADR-0001

### Salience
*Salience network identified by Seeley et al. (2007) in "Dissociable Intrinsic Connectivity Networks for Salience Processing and Executive Control." Centered on anterior insula and anterior cingulate cortex.*

The subsystem that determines what's "important" or "attention-worthy" from the stream of sensor data and events. Not everything that happens deserves Executive attention. Salience filters, prioritizes, and routes.

**Key functions:**
- Filter noise from signal
- Prioritize competing stimuli
- Route to appropriate processing (System 1 vs System 2)
- Manage attention budget

**Status:** Referenced in ADR-0001 but not fully specified. Identified as architectural gap.

### System 1 / System 2
*Daniel Kahneman, "Thinking, Fast and Slow" (2011). Built on decades of work with Amos Tversky on cognitive biases. Terminology from Stanovich & West (2000).*

| System | Speed | Characteristics | GLADyS Implementation |
|--------|-------|-----------------|----------------------|
| **System 1** | Fast | Heuristics, pattern matching, automatic | Learned rules, can bypass LLM |
| **System 2** | Slow | Deliberate reasoning, complex decisions | LLM (Executive) |

System 1 handles familiar situations; System 2 engages for novelty, low confidence, or high stakes.

See: ADR-0010

---

## Plugins

### Sensor
A component that captures information from the world and delivers normalized events to the orchestrator. Supports both push (immediate) and poll (periodic) delivery patterns.

**Direction:** World → Brain
**Structure:** Driver (capture) + Adapter (normalization/protocol)
**Examples:** Microphone, temperature sensor, game state reader, doorbell, email monitor

See: SENSOR_ARCHITECTURE.md, ADR-0003

### Skill
A plugin that operates within the brain. Transforms, analyzes, or answers questions. Has subtypes.

**Direction:** Brain â†” Brain

See: ADR-0003, [questions/plugins.md](questions/plugins.md) §9

### Preprocessor
*Subtype of Skill*

Transforms raw sensor data before salience evaluation. Operates pre-attention.

**Characteristics:**
- Latency-critical: <50ms per stage, <200ms total chain
- Forms a DAG (parallel/sequential execution)
- Examples: Speech-to-text, movement detection, wake word detection

### Query Skill
*Subtype of Skill*

Answers Executive questions on-demand. Not in the real-time path.

**Examples:** Weather lookup, calendar query, knowledge base search

### Analyzer Skill
*Subtype of Skill*

Complex assessment that can run either on-demand or in background.

**Examples:** Threat assessment, sentiment analysis, anomaly detection

### Actuator
A plugin that affects the physical world. Executes commands from the Executive.

**Direction:** Brain → World

**Examples:** Thermostat control, door lock, light switch, game input

See: ADR-0011

### Integration Plugin
A bridge to external ecosystems (Home Assistant, Google Home) that exposes their devices as virtual sensors and actuators.

See: ADR-0011

### Sensor Protocol
The language-agnostic contract that all GLADyS adapters must implement to communicate with the orchestrator. Covers registration, event publishing, heartbeats, health reporting, recovery, capture/replay, and flow control.

See: SENSOR_ARCHITECTURE.md §3

### Driver
A lightweight, application-specific component that captures events from a target application and sends them to an adapter. Drivers are polyglot and run inside or alongside the application they monitor; they are a sensor-internal concern.

**Language:** Polyglot (native to target app)
**Direction:** App → driver → adapter → orchestrator

See: SENSOR_ARCHITECTURE.md §1.1

### Delivery Pattern
The mechanism by which a driver collects data from its target. Phase 2 supports **push** (driver sends events when they occur) and **poll** (adapter periodically checks state) patterns.

See: SENSOR_ARCHITECTURE.md §2.3

### Sensor Manifest
A YAML configuration file that declares a sensor's identity, capabilities (event types), heartbeats, and dependencies. Used by the orchestrator for registration, dead-sensor detection, and capacity planning.

See: SENSOR_ARCHITECTURE.md §10

### Intent
A routing hint provided by an adapter indicating whether an event expects a response.

| Intent | Routing |
|--------|---------|
| `actionable` | Full pipeline: salience → executive → response |
| `informational` | Store as context in memory only; no pipeline routing |
| `unknown` | Default; let salience decide routing |

See: SENSOR_ARCHITECTURE.md §2.2

### evaluation_data
A secondary data bucket in an event containing solution or "cheat" data. Stored for learning and evaluation, but stripped by the orchestrator before the Executive sees it to prevent leaking the answer.

See: SENSOR_ARCHITECTURE.md §2.2

### Skill Pack
A logical unit of distribution grouping related components for a specific domain. Typically includes a sensor, a domain skill, and associated heuristics.

---

## Memory

### Episodic Memory
*Endel Tulving (1972). Distinguished from semantic memory in "Episodic and Semantic Memory" in Organization of Memory.*

Raw event storage - what happened, when, in what context. The "what did I experience?" layer.

**Characteristics:**
- Append-only (within retention period)
- Time-indexed
- Source for pattern extraction
- Subject to compaction over time

See: ADR-0004, ADR-0009

### Semantic Memory
*Endel Tulving (1972). General knowledge independent of personal experience, contrasted with episodic memory.*

Derived knowledge - patterns, beliefs, learned associations. The "what do I know?" layer.

**Characteristics:**
- Abstracted from episodes
- Confidence-tracked
- Subject to decay and update
- Includes preferences, causal beliefs, factual knowledge

See: ADR-0004, ADR-0009, ADR-0010

### Memory Compaction
The process of summarizing or discarding episodic data while preserving semantic insights. Balances storage constraints against information value.

See: ADR-0009

### Staleness
How overdue an observation is relative to expected frequency.

```
staleness = (time_since_last - expected_period) / std_dev(period)
```

High staleness triggers confidence decay.

See: ADR-0010

---

## Learning

### EWMA (Exponentially Weighted Moving Average)
*Standard statistical technique used in finance, signal processing, and ML.*

A technique for tracking values that gives more weight to recent observations. Used for preference tracking.

See: ADR-0007

### Bayesian Belief Model
*Foundational probability theory concept. Modern conjugate prior framework covered in standard ML and Bayesian statistics coursework.*

Statistical models that track uncertainty and update with evidence. GLADyS uses conjugate priors for efficiency.

**MVP Models:**
| Model | Data Shape | Example |
|-------|------------|---------|
| Beta-Binomial | Binary outcomes | "Did user accept suggestion?" |
| Normal-Gamma | Continuous values | "Preferred temperature" |
| Gamma-Poisson | Rate/count data | "Gathering completion rate" |

See: ADR-0010

### Prior Strength
The "effective sample size" of a Bayesian belief. Strong priors resist change from single observations; weak priors adapt quickly.

See: ADR-0010

### Punishment Detection
*From behavioral economics: detecting negative feedback signals to improve system behavior.*

Behavioral signals that indicate user dissatisfaction, used to adjust heuristic confidence.

| Signal | Weight |
|--------|--------|
| Explicit negative feedback | 1.0 |
| Action undone within 60s | 0.8 |
| Suggestion ignored 3+ times | 0.3 |

See: ADR-0010

### Source-domain Scoping
A mechanism using an event's `source` field as a hard filter in heuristic matching. Prevents cross-domain false matches by ensuring heuristics only fire for the domain where they were learned.

See: SENSOR_ARCHITECTURE.md §2.5

---

## Safety & Trust

### Trust Tier
Security classification for actuators based on risk profile.

| Tier | Risk | Audit | Confirmation |
|------|------|-------|--------------|
| `comfort` | Low | `audit_actions` | Optional |
| `security` | High | `audit_security` (Merkle) | Required by default |
| `safety` | Critical | `audit_security` (Merkle) | Always required |

See: ADR-0011

### Safety Bounds
Hard limits on actuator parameters that cannot be bypassed, even by the Executive.

**Example:** Thermostat min 55°F (prevent pipe freeze), max 85°F (prevent heat exhaustion)

See: ADR-0011

---

## Technology

### SSE (Server-Sent Events)
A web standard for pushing real-time updates from server to client over HTTP. Unlike WebSockets, SSE is one-directional (server → client only) and works over standard HTTP connections. GLADyS uses SSE in the Dashboard to stream live event updates and responses without polling.

### FUN (Functional Unified Nexus)
The REST API gateway for external access to GLADyS subsystems. Used by the Dashboard, CLI tools, tests, and future integrations. The Dashboard is one consumer of the FUN API, not the API itself. *The 'U' is for 'U Monster.'*

### gRPC
Google's high-performance RPC framework using Protocol Buffers (protobuf) for typed message serialization. GLADyS uses gRPC for all service-to-service communication. Proto definitions live in `proto/` and are the source of truth for service contracts.

### Capture/Replay
A protocol-level feature for recording and replaying event streams at two boundaries: driver-to-adapter (raw) and adapter-to-orchestrator (normalized). Enables development and testing without live target applications or sensors.

See: SENSOR_ARCHITECTURE.md §4

### PublishEvent / PublishEvents
The gRPC unary RPCs used by adapters to send normalized events to the orchestrator. `PublishEvent` is for single events; `PublishEvents` is a batch transport for high-volume sensors (e.g., RuneScape).

See: SENSOR_ARCHITECTURE.md §1.3, §3

---

## Performance

### Latency Profile
Performance tier that determines scheduling priority and timeout budgets.

| Profile | End-to-End | Use Cases |
|---------|------------|-----------|
| `realtime` | <500ms | Combat warnings, safety alerts |
| `conversational` | <1000ms | Voice interaction |
| `comfort` | <5000ms | Thermostat, lighting |
| `background` | Best-effort | Learning, batch analysis |

See: [questions/infrastructure.md](questions/infrastructure.md) §11

### Sleep Mode
Low-activity period when heavy batch processing (pattern detection, embedding generation) can run. Activated after user idle for configurable duration.

See: ADR-0010

---

## Audit

### Audit Log
Append-only record of system actions. Distinct from memory - audit is ground truth; memory can contradict (and that's expected).

See: ADR-0012

### Merkle Tree
Cryptographic structure for tamper-evident logging. Used for high-security audit events.

See: ADR-0012

---

## Design Philosophy

### Revealed Preference
*Economics concept (Samuelson, 1938) extended by behavioral economics (Thaler, Kahneman).*

GLADyS learns from user behavior patterns in addition to explicit preferences.

See: ADR-0010

### Observability vs Explainability
- **Observability:** User can see current beliefs and system state (required)
- **Explainability:** System can justify its decisions (optional)

GLADyS prioritizes effectiveness over explainability - it serves the user, doesn't justify itself.

See: ADR-0010

---

## Adding Terms

When adding new terms:
1. Use the appropriate category or create a new one
2. Note the source discipline if borrowed (neuroscience, economics, etc.)
3. **Include attribution** for academic/theoretical concepts
4. Reference relevant ADRs
5. Include practical examples where helpful

---

## References

Foundational sources for concepts used in GLADyS. These ideas have diffused widely through popular books, coursework, and articles.

**Cognitive Psychology / Neuroscience:**
- Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.
- Pinker, S. (1997). *How the Mind Works*. Modular cognitive architecture, computational theory of mind.
- Pinker, S. (1994). *The Language Instinct*. Language processing fundamentals.
- Tulving, E. (1972). Episodic and semantic memory. In *Organization of Memory*.
- Seeley, W. W., et al. (2007). Dissociable intrinsic connectivity networks for salience processing and executive control. *Journal of Neuroscience*, 27(9).

**Behavioral Economics / Decision Theory:**
- Thaler, R. & Sunstein, C. (2008). *Nudge*.
- Thaler, R. (2015). *Misbehaving: The Making of Behavioral Economics*. (Nobel Prize 2017)
- Kahneman, D. & Tversky, A. Prospect theory and cognitive biases (1970s-80s). (Nobel Prize 2002)
- Samuelson, P. A. (1938). Revealed preference.

**Statistics / Machine Learning:**
- Gelman, A., et al. (2013). *Bayesian Data Analysis* (3rd ed.). CRC Press.
- Standard ML coursework covering Bayesian methods, conjugate priors, EWMA.

