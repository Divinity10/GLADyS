# GLADyS Subsystem Overview

**Purpose**: Single document explaining what each subsystem does, how they connect, and what's unspecified. Intended for team onboarding and design validation.

**Last Updated**: 2026-01-20

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Subsystem Summary](#2-subsystem-summary)
3. [Orchestrator](#3-orchestrator)
4. [Sensors](#4-sensors)
5. [Salience](#5-salience)
6. [Memory](#6-memory)
7. [Executive](#7-executive)
8. [Actuators](#8-actuators)
9. [Personality](#9-personality)
10. [Audit](#10-audit)
11. [Data Flow](#11-data-flow)
12. [Language Recommendations](#12-language-recommendations)
13. [Open Questions](#13-open-questions)

---

## 1. System Context

### What Is GLADyS?

GLADyS (Generalized Logical Adaptive Dynamic System) is a **local-first, adaptive AI assistant** that:
- Observes the user's environment through sensors (games, smart home, screen, audio)
- Decides what's worth paying attention to (salience)
- Remembers context and learns preferences (memory)
- Decides when and how to respond (executive)
- Takes action through speech or device control (actuators)
- Does all of this with a consistent personality

### Brain-Inspired Architecture

The architecture draws inspiration from neuroscience, but **does not slavishly copy it**. Evolution optimized for biological constraints (parallel neurons, chemical signaling, ~100ms response times). We have different constraints (sequential cores, digital buses, user expectations).

| Brain Region | GLADyS Analog | Notes |
|--------------|---------------|-------|
| Sensory organs | Sensors | Input from world |
| Sensory cortices | Preprocessors | Early feature extraction |
| Thalamus | Orchestrator | Routing, synchronization |
| Amygdala + Hippocampus | Salience + Memory | What matters, what to remember |
| Prefrontal cortex | Executive | Decision-making |
| Motor cortex | Actuators | Output to world |

**Caution**: Don't push the analogy too far. The brain's solutions are optimal for wetware, not silicon.

---

## 2. Subsystem Summary

| Subsystem | ADR(s) | Primary Responsibility | Hot Path? | Language (Revised) |
|-----------|--------|------------------------|-----------|---------------------|
| **Orchestrator** | ADR-0001, ADR-0005 | Event routing, DAG execution, synchronization | Yes | Python* |
| **Sensors** | ADR-0003 | World → Events | Yes | Python |
| **Salience** | ADR-0013 | Filter what matters | Yes | Python |
| **Memory** | ADR-0004, ADR-0009, ADR-0010 | Store, retrieve, learn | **Yes** | Rust + Python* |
| **Executive** | ADR-0014 | Decide and respond | Yes | Flexible (C#/Python) |
| **Actuators** | ADR-0011 | Commands → World | Partial | Python |
| **Personality** | ADR-0015 | Communication style | No | Data (YAML) |
| **Audit** | ADR-0012 | Tamper-proof logging | No | Python |

*See §12 for language reassessment. Memory has Rust fast path + Python storage path.

---

## 3. Orchestrator

### What It Does

The orchestrator is the **central nervous system** of GLADyS. It:

1. **Receives events** from all sensors via gRPC
2. **Routes events** to preprocessors based on plugin manifests
3. **Executes the preprocessor DAG** - some run in parallel, others wait for dependencies
4. **Synchronizes multi-modal inputs** - correlates audio with video with game state
5. **Forwards processed events** to the Salience Gateway
6. **Manages plugin lifecycle** - start, stop, health check, restart
7. **Enforces latency budgets** - tracks time through pipeline, drops or degrades if over budget

### What It Doesn't Do

- Does NOT decide what's important (that's Salience)
- Does NOT store data long-term (that's Memory)
- Does NOT generate responses (that's Executive)
- Does NOT contain ML models (those are in Sensors/Salience/Executive)

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Communication protocol | gRPC | ADR-0005 |
| Plugin model | YAML manifests | ADR-0003 |
| Latency budget | 1000ms end-to-end (conversational) | ADR-0005 |

### Synchronization Model (Resolved)

**Approach**: Lazy synchronization via Memory. Sensors emit events, Orchestrator creates moments.

| Concept | Definition |
|---------|------------|
| **Event** | Raw signal from sensor with timestamp |
| **Collection interval** | How often a sensor samples/emits events (sensor-determined) |
| **Moment** | Events accumulated by Orchestrator within configurable time window (Orchestrator-determined) |
| **Context** | Collection of recent moments across sources (retrieved from Memory) |

**Key distinction**: Collection interval ≠ batching. Sensors emit events at their natural rate. The Orchestrator accumulates them into "moments" for Executive consumption.

**Typical collection intervals** (sensor guidelines, not requirements):

| Sensor Type | Collection Interval | Notes |
|-------------|---------------------|-------|
| Game events | Real-time/async | Events as they occur |
| Temperature | 5 min | Changes slowly |
| CGM (glucose) | 1-5 min | Medical device rate |
| Doorbell | Real-time | Event on ring/motion |
| Email | 15 min | Check periodically |
| Audio | Continuous | Stream with chunking |

**Moment window** (Orchestrator setting, configurable):
- Default: 50-100ms for real-time scenarios (gaming, conversation)
- Configurable per context
- MVP: Static setting; post-MVP: learned/dynamic adjustment
- High-salience events bypass moment accumulation (immediate to Executive)

**Synchronization approach**:
1. Events flow **asynchronously** to Memory with timestamps
2. Orchestrator does **NOT** correlate across sources - it routes only
3. Memory enables **temporal queries**: "what happened in the last N seconds from all sources?"
4. Executive requests context from Memory when it needs multi-source correlation
5. **Clock tick** (1 Hz) drives proactive scheduling, not event synchronization

**Rationale**: The brain synchronizes because neurons are slow and parallel. We can query Memory faster than neurons fire. Let Memory handle temporal correlation, not Orchestrator.

### ⚠️ Remaining Unspecified

| Question | Impact | Notes |
|----------|--------|-------|
| **DAG execution semantics** | Parallel vs sequential? Configurable per-edge? | ADR-0003 shows dependencies but not execution model |
| **Backpressure handling** | What if downstream can't keep up? | Queue? Drop? Throttle sensors? |

### Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| Event routing latency | <5ms | Per hop |
| DAG execution overhead | <50ms total | For full preprocessor chain |
| Throughput | >100 events/sec | Sustained |
| Memory footprint | TBD | Depends on buffering strategy |

### Language Decision

**Language**: Python

**ADR-0001 originally said Rust**, rationale was "performance-critical routing." This was updated to Python after sync model resolution and architecture review (2026-01-21).

**Why Python is correct** (confirmed after deep dive 2026-01-21):

1. **Amygdala architecture**: Salience + Memory fast path (Rust) together form the "amygdala" - the fast threat/opportunity detector. They share a process per ADR-0001. The heavy evaluation happens there, not in Orchestrator.

2. **Orchestrator's actual job**:
   - Receives events from sensors/preprocessors
   - Queries Salience+Memory for salience score (I/O call)
   - Routes based on score: HIGH → immediate to Executive, LOW → accumulate for next tick
   - Manages clock ticks, plugin lifecycle, health checks
   - This is I/O + simple comparison, NOT compute-intensive

3. **Context comes from Memory**: Threat patterns, semantic knowledge, domain rules all stored in Memory. Salience applies those patterns. Orchestrator doesn't need this knowledge - it just routes based on returned scores.

4. **Performance is achievable**: <5ms per hop with Python gRPC (~1-3ms local). >100 events/sec with asyncio. The compute-heavy work is in Salience+Memory's Rust fast path.

**Note**: See Section 12 for where Rust IS justified (Memory fast path, audio pipeline).

---

## 4. Sensors

### What They Do

Sensors are **plugins that observe the world** and emit events. They:

1. **Connect to external systems** - Aperture API, Home Assistant, microphone, screen capture
2. **Transform raw input into structured events** - JSON payloads with typed fields
3. **Tag events with metadata** - timestamps, source, context hints
4. **Push events to Orchestrator** via gRPC

### Types of Sensors

| Type | Examples | Event Rate | Notes |
|------|----------|------------|-------|
| **Discrete event** | Doorbell, game events | Low (1-10/min) | Easy - event per occurrence |
| **Continuous stream** | Temperature, audio | High (10-1000/sec) | Needs threshold filtering or chunking |
| **On-demand** | Screen capture | Variable | User or system triggered |

### Key Sensors for MVP

| Sensor | Source | Events Emitted | Priority |
|--------|--------|----------------|----------|
| Home Assistant Integration | HA WebSocket | Device state changes | MVP (UC-04 Doorbell) |
| Aperture (Minecraft) | Aperture API | Game state, combat, inventory | First Release (UC-01) |
| Microphone (PTT) | Local audio device | Audio chunks on hotkey | MVP (UC-11 Voice) |
| Wake Word + VAD | Audio preprocessor | Wake word detected, speech segments | Post-MVP (Rust audio service) |

### Voice Activation Decision (Resolved)

| Phase | Activation Method | Rationale |
|-------|-------------------|-----------|
| **MVP** | Press-to-talk | Simpler. Gaming users have hands on keyboard anyway. |
| **Post-MVP** | Wake word (local) | Hands-free for home automation. Local processing avoids cloud creepiness. |

**Press-to-talk for MVP**:
- Hotkey triggers voice capture
- No always-on listening
- No VAD complexity
- Simplifies MVP scope significantly

**Wake word for Post-MVP**:
- Requires always-on audio capture
- Needs VAD (Voice Activity Detection) to segment speech
- Local wake word model (e.g., OpenWakeWord, Porcupine)
- This is the **legitimate Rust project**: real-time audio DSP benefits from Rust

### ⚠️ Remaining Unspecified

| Question | Impact |
|----------|--------|
| **Continuous data filtering** | Does sensor filter, or does it emit everything and let salience decide? |
| **Aperture API details** | What exactly does Aperture expose? What events, what rate? |

### Performance Characteristics

- Sensors are I/O bound, not CPU bound
- Python is fine - network and API calls dominate

### Language Consideration

**ADR-0001 says**: Python

**Assessment**: ✅ Appropriate. ML preprocessing uses Python ecosystem. I/O bound work.

---

## 5. Salience

### What It Does

Salience is the **attention filter**. It decides what's worth forwarding to the Executive. It:

1. **Receives processed events** from Orchestrator
2. **Evaluates importance** across multiple dimensions
3. **Manages attention budget** - can't process everything
4. **Applies habituation** - repeated stimuli become less salient over time
5. **Forwards salient events** to Executive

### Salience Dimensions (ADR-0013)

| Dimension | What It Measures |
|-----------|------------------|
| threat | Potential harm to user/system |
| opportunity | Potential benefit |
| goal_relevance | Related to current user goals |
| novelty | How unexpected/new |
| habituation | Suppression from repetition |

(Full design has 9 dimensions; MVP may use 5)

### Pipeline Stages

1. **Suppression Check** (<1ms) - Is this event type globally suppressed?
2. **Heuristic Evaluation** (5-20ms) - Rule-based scoring
3. **Deep Evaluation** (50-80ms, optional) - ML-based scoring for uncertain cases
4. **Threshold Gate** - Forward if above threshold for active context

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Dimensions | 9 (reducible to 5 for MVP) | ADR-0013 |
| Habituation model | Exponential decay with min_sensitivity | ADR-0013 |
| Deep evaluation | Optional, skippable for MVP | ADR-0013, ARCHITECTURE_REVIEW |

### ⚠️ Unspecified

| Question | Impact |
|----------|--------|
| **Deep evaluation trigger** | When is heuristic confidence low enough to invoke deep eval? |
| **Context detection** | How does system know "user is gaming" vs "user is at home"? |

### Performance Characteristics

- Heuristic path: 5-20ms
- Deep eval path: 50-80ms (ML inference)
- Throughput: >100 events/sec

### Language Consideration

**ADR-0001 says**: Python

**Assessment**: ✅ Appropriate. ML models (if using deep eval) need Python ecosystem.

---

## 6. Memory

### What It Does

Memory is **how GLADyS remembers**. It:

1. **Stores episodic events** - what happened, when, what context
2. **Extracts semantic facts** - derived understanding from episodes
3. **Tracks user preferences** - via EWMA adaptation
4. **Supports retrieval** - by time, embedding similarity, or entity
5. **Compacts over time** - old events consolidated into summaries

### Storage Architecture

| Tier | What | Latency | Notes |
|------|------|---------|-------|
| L0 | Working context | <1ms | In-memory, current conversation |
| L3 | Long-term storage | <50ms | PostgreSQL + pgvector |

(L1/L2/L4 deferred for MVP)

### Core Tables (MVP)

| Table | Purpose |
|-------|---------|
| episodic_events | Raw events with embeddings |
| entities | Named things (people, places, games) |
| user_profile | Preference parameters with EWMA |
| feedback_events | Thumbs up/down signals |

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Database | PostgreSQL + pgvector | ADR-0004 |
| Embedding model | all-MiniLM-L6-v2 (384 dims) | ADR-0004 |
| Adaptation algorithm | Dual-timescale EWMA | ADR-0007 |

### ⚠️ Unspecified

| Question | Impact |
|----------|--------|
| **Memory vs Audit routing** | When does Executive query Memory vs Audit? |
| **Embedding migration** | What happens when embedding model changes? |
| **Partition management** | Who creates new time partitions? |

### Performance Characteristics

- Write: <10ms for event insert
- Read (embedding search): <50ms for top-k
- Background jobs: compaction, fact extraction (during idle)

### Two-Layer Architecture (Updated 2026-01-20)

Memory now has **two layers** matching the System 1 / System 2 split:

| Layer | Language | Handles | Latency Target |
|-------|----------|---------|----------------|
| **Fast Path** | Rust | L0 working memory, heuristic matching, novelty detection, reasoning cache | <5ms |
| **Storage Path** | Python | PostgreSQL queries, embedding generation, batch operations | <50ms |

**Rationale**: The real optimization isn't Rust vs Python everywhere. It's:
- Skip the LLM when possible (System 1 fast path)
- Use LLM only for novel situations (System 2 slow path)

The Rust fast path handles what's called on every event:
- Novelty detection (embedding similarity check)
- Heuristic lookup (learned System 1 responses)
- Reasoning cache (situation → previous LLM result)

Python handles what's I/O bound anyway:
- PostgreSQL queries (network latency dominates)
- Embedding generation (ML model bound)

See ADR-0010 §3.15 for full specification.

### Language Consideration

**ADR-0001 says**: Python

**Updated Assessment** (2026-01-20): **Hybrid Rust/Python**. Fast path (novelty detection, heuristics) in Rust for <5ms latency. Storage path in Python (I/O bound work where language doesn't matter).

---

## 7. Executive

### What It Does

The Executive is **the decision-maker**. It:

1. **Receives salient events** from Salience Gateway
2. **Decides whether to respond** - not everything needs a reaction
3. **Decides response type** - Alert, Observation, Quip, etc.
4. **Decides timing** - now, soon, later, or scheduled
5. **Generates response content** - via LLM with personality
6. **Routes output** - to TTS, text display, or actuators

### Decision Framework (ADR-0014)

1. **Relevance**: Should GLADyS care about this?
2. **Timing**: Interrupt now, queue for later, or schedule proactively?
3. **Response Type**: What kind of response fits?
4. **Content**: What specifically to say/do?

### Response Types

| Type | Use Case |
|------|----------|
| Alert | Urgent, needs attention (doorbell, threat) |
| Observation | Commentary on current situation |
| Suggestion | Proactive recommendation |
| Quip | Personality-driven humor |
| Check-in | Proactive "how's it going" |

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| LLM strategy | Cloud API for MVP, local for v2 | ARCHITECTURE_REVIEW |
| Proactive scheduling | MVP-required | ARCHITECTURE_REVIEW (S-EXE-6 REJECTED) |
| Personality integration | Response Model traits applied to LLM prompts | ADR-0015 |

### ⚠️ Unspecified

| Question | Impact |
|----------|--------|
| **Which LLM** | Claude? GPT-4? Local Llama? Decision pending. |
| **Goal management** | Where do user goals come from? |
| **Multi-turn handling** | How track conversation state across turns? |
| **Fallback behavior** | What if LLM times out or errors? |

### Performance Characteristics

- Decision logic: <100ms
- LLM inference: 200-500ms (local) or 500-2000ms (cloud)
- This is the **dominant latency** in the system

### Language Consideration

**ADR-0001 says**: C#

**Rationale given**: Team expertise (Mike strongest in C#)

**Honest assessment**:
- The Executive is mostly prompt assembly + LLM API calls + decision logic
- This is not performance-critical (LLM dominates)
- C# is fine if Mike is implementing
- Python would also work (simpler interop with ML code)
- **Recommendation**: Use whatever the implementer is fastest in

---

## 8. Actuators

### What They Do

Actuators are **how GLADyS affects the world**. They:

1. **Receive commands** from Executive
2. **Translate to device-specific calls** - Home Assistant API, game input, etc.
3. **Enforce safety constraints** - rate limiting, trust tiers, bounds checking
4. **Report feedback** - success/failure, device state

### Trust Tiers (ADR-0011)

| Tier | Examples | Confirmation | Audit Level |
|------|----------|--------------|-------------|
| Comfort | Thermostat, lights | No | Standard |
| Security | Door locks, cameras | Yes | Merkle tree |
| Safety | Smoke alarm response | No (auto) | Merkle tree |

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Integration model | Home Assistant first | ADR-0011 |
| Rate limiting | Per-actuator configurable | ADR-0011 |
| Confirmation UX | Required for security tier | ADR-0011 |

### ⚠️ Unspecified

| Question | Impact |
|----------|--------|
| **Lock confirmation UX** | What's the actual flow? Push notification? Voice challenge? |
| **Gaming actuators** | How does Aperture fit? Can GLADyS send game inputs? |
| **Credential storage** | Where do Home Assistant tokens live? |

### Language Consideration

**ADR-0001 says**: Python (via integration plugins)

**Assessment**: ✅ Appropriate. API calls, async I/O.

---

## 9. Personality

### What It Does

Personality is **how GLADyS communicates**. It's data, not code:

1. **Defines communication style** - formal/casual, verbose/terse, ironic/literal
2. **Configures humor** - frequency and style weights
3. **Sets boundaries** - what's off-limits for this persona
4. **Adjusts to context** - different behavior under threat vs celebration

### Response Model Traits (ADR-0015)

| Category | Traits |
|----------|--------|
| Communication | irony, literalness, directness, formality, verbosity |
| Humor | frequency + style weights (observational, self-deprecating, punny, absurdist, dark) |
| Affect | warmth, energy |
| Interaction | proactivity, confidence |

All traits are bipolar (-1 to +1) except humor frequency (0-1).

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Model | Response Model only for MVP | ADR-0015 |
| User customization | ±0.2 from pack base | ADR-0015 |
| Pack system | Personality + skills bundled | ADR-0003, ADR-0015 |

### Language Consideration

Personality is **configuration, not code**. Stored in YAML manifests, applied by Executive.

---

## 10. Audit

### What It Does

Audit is the **tamper-proof record**. It:

1. **Logs all significant actions** - commands, decisions, state changes
2. **Maintains integrity** - hash chains, Merkle trees for security events
3. **Supports query** - but NOT by the brain for reasoning (Memory does that)
4. **Enforces retention** - configurable per event type

### Audit Tables (ADR-0012)

| Table | Integrity | Use Case |
|-------|-----------|----------|
| audit_security | Merkle tree | Security-tier actuator commands |
| audit_actions | Hash per record | General actions |
| audit_observations | Light | Sensor events (high volume) |

### Key Design Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Integrity model | Tiered (Merkle for security, hash for actions) | ADR-0012 |
| Retention | Per-event-type configurable | ADR-0012 |
| Access | Read-only for brain | ADR-0012 |

### Language Consideration

**ADR-0001 says**: Python

**Assessment**: ✅ Appropriate. Database operations, low performance sensitivity.

---

## 11. Data Flow

### Primary Pipeline (Event → Response)

```
[Sensor] → [Orchestrator] → [Preprocessor DAG] → [Salience] → [Executive] → [Output/Actuator]
              ↑                                      ↓
              └────────────────────────────────────[Memory]
```

### Latency Budget (Conversational Profile)

| Stage | Budget | Cumulative |
|-------|--------|------------|
| Sensor → Orchestrator | 50ms | 50ms |
| Orchestrator routing | 5ms | 55ms |
| Preprocessor DAG | 150ms | 205ms |
| Salience | 50ms | 255ms |
| Memory query | 50ms | 305ms |
| Executive decision | 100ms | 405ms |
| LLM inference | 400ms | 805ms |
| TTS | 150ms | 955ms |
| **Buffer** | 45ms | **1000ms** |

### Critical Path

The LLM call dominates. Everything else is optimization at the margin.

---

## 12. Language Recommendations

### Current ADR-0001 Choices

| Component | Language | Rationale |
|-----------|----------|-----------|
| Orchestrator | Rust | "Performance-critical routing" |
| Sensors, Salience, Memory, Actuators, Audit | Python | ML ecosystem |
| Executive | C# | Team expertise |

### Reassessment (2026-01-20)

| Component | Keep/Change | Reasoning |
|-----------|-------------|-----------|
| **Orchestrator** | **Change → Python** | Sync model resolved: lazy via Memory. Orchestrator is message passing, not temporal correlation. Rust no longer justified. |
| **Sensors** | Keep Python | I/O bound, ML preprocessing |
| **Salience** | Keep Python | ML models |
| **Memory** | **Change → Hybrid Rust/Python** | Two-layer architecture: Rust fast path (novelty detection, heuristics, L0 cache) + Python storage path (PostgreSQL, embeddings). Rust is justified for the hot path called on every event. |
| **Executive** | **Flexible** | Not performance-critical. Use whatever implementer is fastest in. C# fine if Mike builds. |
| **Actuators** | Keep Python | I/O bound, API calls |
| **Audit** | Keep Python | Database operations |
| **Audio Service** | **NEW: Rust** | Post-MVP wake word + VAD. Real-time DSP benefits from Rust. This is the legitimate Rust project. |

### Team Skills Context

| Person | Strongest | Also Knows | Learning |
|--------|-----------|------------|----------|
| Mike | C# | - | Other languages |
| Scott | C#, C++, Python, Java | Many others | Rust |
| Leah | Python | C#, Java | - |

### Honest Take

The polyglot architecture adds complexity:
- 3 languages = 3 build systems, 3 debugging environments
- gRPC boundaries add latency and schema maintenance

**Revised recommendation after analysis**:
- **MVP**: Python for most subsystems + Rust for Memory fast path + C# Executive if Mike builds it
- **Post-MVP**: Add Rust audio service for wake word/VAD

**Why this works**:
- Memory fast path in Rust is justified: <5ms target, called on every event
- Scott learns Rust via Memory subsystem (real use case, not artificial)
- Python handles I/O-bound work (bottleneck is LLM, not our code)
- C# Executive is valid if Mike is fastest there
- Audio service provides second Rust project post-MVP

**Net change from ADR-0001**:
- Orchestrator: Rust → Python (sync model doesn't require Rust)
- Memory: Python → Hybrid Rust/Python (fast path justifies Rust)
- Audio Service: NEW addition (Rust, post-MVP)

---

## 13. Open Questions

### ✅ Resolved This Session (2026-01-20)

| Question | Resolution |
|----------|------------|
| **Synchronization model** | Lazy sync via Memory. Orchestrator routes only. Memory handles temporal queries. |
| **Wake word / VAD** | Press-to-talk for MVP. Wake word (Rust audio service) post-MVP. |
| **Orchestrator language** | Python (Rust no longer justified after sync model resolution) |
| **Memory language** | **Hybrid Rust/Python**: Rust for fast path (novelty, heuristics, L0 cache), Python for storage path (PostgreSQL, embeddings). See ADR-0010 §3.15. |

### Blocking Implementation

| Question | Subsystem | Impact |
|----------|-----------|--------|
| **Which LLM** | Executive | Affects latency budget, API contracts |
| **Lock confirmation UX** | Actuators | Safety-critical, needs design |

### Should Resolve Pre-MVP

| Question | Subsystem |
|----------|-----------|
| Context detection algorithm | Salience |
| Memory vs Audit query routing | Memory |
| Credential storage | Actuators |
| LLM fallback behavior | Executive |

### Can Defer

| Question | Subsystem |
|----------|-----------|
| Embedding migration strategy | Memory |
| Multi-user support | Memory |
| Gaming actuators (Aperture input) | Actuators |
| Deep salience evaluation triggers | Salience |

---

## Appendix: Quick Reference

### What Calls What

```
Sensor      → Orchestrator  (gRPC: SensorEvent)
Orchestrator → Preprocessor (gRPC: ProcessEvent)
Preprocessor → Orchestrator (gRPC: ProcessedEvent)
Orchestrator → Salience     (gRPC: EvaluateEvent)
Salience    → Memory       (gRPC: QueryContext)
Salience    → Executive    (gRPC: SalientEvent)
Executive   → Memory       (gRPC: QueryContext, StoreEvent)
Executive   → Actuator     (gRPC: Command)
Executive   → TTS          (gRPC: Speak)
All         → Audit        (gRPC: LogEvent)
```

### Key ADRs by Subsystem

| Subsystem | Primary ADR | Supporting ADRs |
|-----------|-------------|-----------------|
| Orchestrator | ADR-0001 | ADR-0005 (gRPC) |
| Sensors | ADR-0003 | - |
| Salience | ADR-0013 | ADR-0007 (adaptation) |
| Memory | ADR-0004 | ADR-0009 (contracts), ADR-0007 (EWMA) |
| Executive | ADR-0014 | ADR-0015 (personality) |
| Actuators | ADR-0011 | ADR-0008 (security) |
| Personality | ADR-0015 | ADR-0003 (manifests) |
| Audit | ADR-0012 | - |
