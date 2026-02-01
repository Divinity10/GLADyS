# Cross-Cutting Questions

Topics that span multiple subsystems: audit, output routing, integration, and architectural gaps.

**Last updated**: 2026-01-31

---

## Open Questions

### Q: Cross-Context Salience Strategy (§35)

**Status**: Open — design decision
**Priority**: Medium
**Created**: 2026-01-31
**Origin**: Relocated from `docs/research/OPEN_QUESTIONS.md`

When a doorbell rings during a gaming session, two contexts apply: gaming (primary) and home (the doorbell's domain). Currently, we evaluate with both profiles and take the maximum salience.

**The question**: Is "max across contexts" the right rule? Alternatives:
- Switching cost (brief reduced sensitivity during context change)
- Persistent background monitoring (some contexts always run)
- Priority ordering (safety contexts always override)

**Relevant**: ADR-0013 Section 5.3.1

---

### Q: Event Condensation Strategy (§36)

**Status**: Open — design decision
**Priority**: Medium
**Created**: 2026-01-31
**Origin**: Relocated from `docs/research/OPEN_QUESTIONS.md`
**See also**: [resource-allocation.md](resource-allocation.md) — Dynamic Heuristic Behavior section covers the broader accuracy-latency framing that subsumes this question

Some sensors produce high-frequency data — a motion sensor firing hundreds of times per hour, a game emitting damage events every tick, a temperature sensor reporting every second. Most are repetitive. Storing and processing each individually is wasteful, but naive deduplication destroys information the learning pipeline needs.

**Possible approaches** (not mutually exclusive):
- **Sensor-level rate limiting**: Sensors fire on intervals, batching events with timestamp lists
- **Orchestrator-level condensation**: Recent event map merges identical events within a time window
- **Storage-level compression**: Identical events stored as one record with timestamp array

**Design questions**:
- What's the right condensation unit? By exact match, embedding similarity, or source?
- Does condensation interact with habituation? (Double-filtering risk)
- What temporal features matter enough to preserve? (Bursts, periodicity, acceleration)
- Should condensation be a preprocessor function? (Requires state — see §37)

**Relevant**: ADR-0013 Section 6.3 (overload handling), ADR-0004 Section 4 (memory hierarchy)

---

### Q: Orchestrator vs Executive Responsibility Boundary (§30)

**Status**: Resolved — implemented in W3 (branch `poc1/closed-loop-learning`)
**Priority**: High (affects PoC architecture)
**Created**: 2026-01-26
**Resolved**: 2026-01-31

#### Problem

The current PoC has the Orchestrator deciding whether to use a heuristic or invoke Executive reasoning:

```
Current flow:
Event → Salience (returns heuristic match) → Orchestrator decides:
  - High confidence + high salience → execute heuristic, skip Executive
  - Otherwise → send to Executive
```

**Issue**: The Orchestrator is making a *decision*, but decision-making is the Executive's domain. The Orchestrator should be a **dispatcher**, not a **decider**.

#### Proposed: Executive Decides

```
Proposed flow:
Event → Salience (returns heuristic match) → Orchestrator ALWAYS sends to Executive:
  - event data
  - salience evaluation
  - matched heuristic (if any) + confidence

Executive decides:
  - High confidence heuristic? → use it, skip LLM
  - Low confidence heuristic? → use LLM, maybe informed by heuristic
  - No heuristic? → full reasoning
  - Overloaded? → rate limit, use heuristic only, or drop low-priority
  - Low urgency + low salience? → no response needed
```

#### Why Executive Should Decide

The Executive has context the Orchestrator doesn't:

| Context | Why It Matters |
|---------|----------------|
| **Current load** | Can decide to use heuristic-only when overloaded |
| **Conversation state** | "We're in the middle of something" affects priority |
| **Active goals** | Heuristic might conflict with current goal |
| **User preferences** | Some users want more/less reasoning |
| **Response history** | "I just said this" - avoid repetition |

#### Separation of Concerns

| Concern | Should Belong To |
|---------|------------------|
| "Is this urgent?" | Salience |
| "Route to which subsystem?" | Orchestrator |
| "Use heuristic or reason?" | **Executive** |
| "What action to take?" | Executive |
| "Which actuator/output?" | Executive (or Output Router) |

#### Exception: Emergency Fast-Path

For truly critical situations (safety alerts, threat detection), the Orchestrator may execute immediately and inform the Executive after:

```
if heuristic.confidence >= 0.95 AND salience.urgency == CRITICAL:
    # Emergency fast-path: execute immediately, inform Executive after
    execute(heuristic)
    notify_executive(event, heuristic, "executed_fast_path")
```

This is more like a hardware interrupt than a decision.

#### Executive Responses When Overloaded

When the Executive is under load, it can respond with:

1. **Rate limit signal** - Tell Orchestrator to slow down
2. **Heuristic-only mode** - Accept heuristic without reasoning
3. **No response needed** - Low urgency events can be dropped
4. **Batch mode** - Accumulate and process together

#### Impact on PoC

Current PoC implementation in `router.py` would need to change:
- Remove confidence threshold logic from Orchestrator
- Always send to Executive with heuristic context attached
- Add fast-path exception for critical urgency only

#### Resolution

Implemented in W3. Answers to the open questions:

1. **Yes** — implemented in PoC on `poc1/closed-loop-learning` branch
2. **Emergency fast-path**: confidence >= 0.95 AND threat >= 0.9 (Orchestrator short-circuits)
3. **Rate limiting**: Deferred to post-PoC

Key implementation files:
- `src/services/orchestrator/gladys_orchestrator/router.py` — always forwards to Executive, emergency fast-path only
- `src/services/executive/gladys_executive/server.py` — heuristic fast-path (confidence >= 0.7, configurable via `EXECUTIVE_HEURISTIC_THRESHOLD`)

---

### Q: Orchestrator Coordination Model (§31)

**Status**: Open - needs design
**Priority**: High (affects scalability and reliability)
**Created**: 2026-01-26
**See also**: [resource-allocation.md](resource-allocation.md) — Concurrent Event Processing section addresses §31.1 and §31.5 specifically

#### Context

The Orchestrator coordinates between sensors, Memory/Salience, and Executive. Several related design questions need answers before the PoC becomes the product.

#### Questions

##### 31.1 Multi-Threading for Sensor Volume

**Question**: Should the Orchestrator be multi-threaded to handle varying sensor volumes?

**Current state**: Single-threaded asyncio event loop.

**Options**:
1. **Keep single-threaded asyncio** - Simpler, sufficient if we don't block
2. **Thread pool for CPU-bound work** - Already have ThreadPoolExecutor for gRPC
3. **Multiple event loops** - One per sensor category (high-volume vs low-volume)
4. **External message queue** - Redis/RabbitMQ to decouple ingestion from processing

**Consideration**: asyncio handles I/O concurrency well. The question is whether we have CPU-bound work that blocks the loop.

##### 31.2 Communication System (Sync/Async/Queue)

**Question**: What communication pattern between Orchestrator and Executive?

**Current state**: Synchronous gRPC calls (Orchestrator waits for Executive response).

**Options**:
1. **Keep sync gRPC** - Simple, request-response semantics
2. **Async gRPC with callbacks** - Non-blocking, but complex error handling
3. **Message queue** - Decouple completely, Executive pulls work
4. **Streaming gRPC** - Bidirectional stream for ongoing conversation

**Consideration**: Sync is fine if Executive responds quickly. If LLM reasoning takes seconds, we block the Orchestrator event loop.

##### 31.3 Simultaneous Subsystem Calls

**Question**: Should Orchestrator send to multiple subsystems in parallel?

**Current state**: Sequential calls (Salience → then route based on result).

**Options**:
1. **Keep sequential** - Simpler, Salience result informs routing
2. **Parallel fan-out** - Send to Memory + Salience + Executive simultaneously
3. **Speculative execution** - Start Executive while waiting for Salience, abort if not needed

**Consideration**: Parallel improves latency but wastes resources if we don't need all results.

##### 31.4 Action Routing to Actuators

**Question**: How are Executive decisions routed to the correct actuator?

**Current state**: Not implemented. Executive returns response text, no actuator integration.

**Design needed**:
- Does Executive specify actuator directly? ("turn on light in kitchen")
- Or does a separate Action Router interpret intent?
- How are actuator capabilities discovered?
- What happens if actuator is unavailable?

**Related**: ADR-0011 (Actuators) defines the actuator interface but not the routing.

##### 31.5 Back-Pressure and Overload

**Question**: What happens when sensors produce faster than we can process?

**Current state**: Events pile up in asyncio queues. No back-pressure. Eventually OOM.

**Options**:
1. **Drop oldest** - Discard events that have been waiting too long
2. **Drop lowest priority** - Keep urgent, discard background
3. **Sample** - Process 1 in N events during overload
4. **Signal back-pressure** - Tell sensors to slow down
5. **Batch aggressively** - Combine multiple events into one

**Consideration**: Need different strategies for different event types. Safety events should never be dropped.

---

### Q: PoC Validation Scope (§32)

**Status**: Open - needs definition
**Priority**: High (guides all implementation decisions)
**Created**: 2026-01-26

#### Context

The PoC will eventually morph into the product. We need clarity on what the PoC must prove and in what sequence, to avoid both over-engineering and under-engineering.

#### Questions

##### 32.1 What Do We Need to Prove?

Core hypotheses to validate:

| Hypothesis | What Would Prove It |
|------------|---------------------|
| Heuristics can replace LLM reasoning | Same quality response, <100ms vs >1s |
| TD learning improves heuristics | Confidence correlates with outcome accuracy |
| Salience reduces noise | Fewer irrelevant events reach Executive |
| Semantic matching works | Similar situations match similar heuristics |
| Multi-sensor integration | Events from different sensors combine coherently |

##### 32.2 Sequence of Proof

What order should we validate hypotheses?

**Proposed**:
1. **Single sensor → heuristic → response** (current PoC scope)
2. **Feedback → confidence update** (partially implemented)
3. **Heuristic creation from reasoning** (not implemented)
4. **Multi-sensor fusion** (not implemented)
5. **Actuator integration** (not implemented)

##### 32.3 How Do We Measure Success?

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Heuristic hit rate | >50% of events | Dashboard counter |
| Response latency (heuristic) | <100ms p95 | Prometheus histogram |
| Response latency (reasoning) | <3s p95 | Prometheus histogram |
| Confidence accuracy | Confidence correlates with thumbs up/down | Statistical analysis |
| False positive rate | <10% irrelevant responses | User feedback |

##### 32.4 How Do We Fine-Tune?

What knobs exist for tuning system behavior?

| Parameter | Current | Tunable? |
|-----------|---------|----------|
| Similarity threshold | 0.7 | Yes (per-heuristic) |
| Learning rate | 0.1 | Yes (per-heuristic) |
| Moment window | 100ms | Yes (config) |
| High salience threshold | 0.7 | Yes (config) |
| Outcome wait time | 60s | Yes (config) |

##### 32.5 How/When Do We Benchmark?

**Questions**:
- What load should we test? (events/second)
- What's the baseline to compare against?
- When do we run benchmarks? (CI? Manual?)
- What hardware assumptions?

##### 32.6 Testing Strategy

**Questions** (also in §14.8):
- How do you regression test a learning system?
- What's deterministic vs non-deterministic?
- Simulation environments for sensors?
- How to prevent learned behavior drift?

---

### Q: Cross-Cutting Integration Questions (§12)

**Status**: Open
**Priority**: Medium

#### Questions

1. **Executive decision**: How choose between speak vs actuate vs both vs neither?
2. **Continuous data**: Temperature every 5s - how enter system without flooding salience? (See [data-types.md](data-types.md))
3. **MVP scope**: Minimum to prove architecture works?
4. **Testing strategy**: Learning systems are non-deterministic - how test?

---

### Q: Output Routing and User Presence (§13)

**Status**: Gap - needs design
**Priority**: High

#### Problem

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

#### Design Inspiration Sources

| Domain | Relevant Concepts | What It Offers |
|--------|-------------------|----------------|
| **Biology** | Motor neurons, proprioception | Brain learns which "muscle" to activate |
| **Cellular/WiFi** | Handoff, roaming, signal strength | User "roams" between devices |
| **Networking (QoS)** | Priority queues, traffic classes | Urgent messages get different treatment |
| **Pub/Sub** | Topic subscriptions, routing | Devices subscribe to message types |
| **Human Assistant** | Escalation, context awareness | Adapts channel to situation |
| **Service Mesh** | Retry policies, failover | If first output fails, try another |

#### Proposed: Hybrid Model

Combine the best from each domain:

1. **Presence detection** (cellular/wifi) - Track which devices the user is near
2. **Device capabilities** (IoT) - This device has display, that one is audio-only
3. **Message priority** (QoS) - Security alert vs routine notification
4. **Subscription model** (pub/sub) - User preferences: "always send X to phone"
5. **Escalation** (human assistant) - No response on speaker → try phone
6. **Learning** (biology) - Over time, learn "Scott responds faster from X at time Y"

#### Human Assistant Analogy

A good human assistant would:
- Tap your shoulder if you're right there
- Call your name if you're in another room
- Text if you're away
- Escalate if urgent and no response

GLADyS should behave similarly.

#### Routing Factors

| Factor | Source | Example |
|--------|--------|---------|
| **User location** | Presence sensors, device activity | Keyboard active → at computer |
| **Device availability** | Health checks | Google Home reachable? |
| **Message priority** | Event type | Security = high, routine = low |
| **Time of day** | Clock | 2am → silent notification, not speaker |
| **User preferences** | Configuration + learned | "Security events always to phone" |
| **Content type** | Message metadata | Video doorbell → device with display |
| **Response history** | Learning | "Scott responds from phone evenings" |

#### Open Questions

1. **Presence detection**: What signals indicate user location?
2. **Escalation policy**: How long to wait before trying next device?
3. **Multi-user**: Multiple users in household - route to correct person?
4. **Privacy**: Don't announce sensitive info on shared speaker?
5. **Output as plugin?**: Is the output router a plugin, or core system?
6. **Acknowledgment**: How know if user received the message?
7. **Do Not Disturb**: User/device-level DND modes?

#### Relationship to Actuators

Output devices could be modeled as actuators with special semantics:
- `type: output` vs `type: actuator`
- Or: Output router as separate subsystem that USES actuators

Decision needed: unified model or separate concepts?

---

### Q: Architectural Gaps Inventory (§14)

**Status**: Partial - some resolved, some open
**Priority**: Varies
**Created**: 2026-01-18

Gap analysis performed after ADR-0010/0011/0012 completion.

#### Resolved Gaps

| Gap | Resolution |
|-----|------------|
| Salience Subsystem | ADR-0013 |
| Executive Decision Loop | ADR-0014 |
| Personality / Persona | ADR-0015 |

#### Medium Priority (User Experience)

##### 14.3 Output Routing / User Presence
See [§13 above](#q-output-routing-and-user-presence-13)

##### 14.5 Multi-User / Household
**Gap**: Mentioned as open question in ADR-0010 but it's architectural.

**Questions**:
- Whose preferences win when users conflict?
- Per-user profiles vs household consensus?
- Privacy between household members?
- Voice identification for personalization?

**Recommendation**: Design doc first, ADR when decisions solidify

#### Lower Priority (Operational)

##### 14.6 Error Handling / Graceful Degradation
**Gap**: Scattered mentions but no coherent strategy.

**Questions**:
- What happens when subsystems fail?
- User communication about failures?
- Self-healing behaviors?
- Fallback chains?

##### 14.7 Upgrade / Migration
**Gap**: Not addressed.

**Questions**:
- Schema migration for memory/audit?
- Plugin version compatibility?
- Rolling upgrades?

**Recommendation**: Defer until closer to v1.0

##### 14.8 Testing Strategy
**Gap**: Not addressed.

**Questions**:
- How do you regression test a learning system?
- Simulation environments?
- Preventing learned behavior drift?

#### Documentation Gaps (Resolved)

| Doc | Status |
|-----|--------|
| GLOSSARY.md | Created 2026-01-18 |
| PERSONALITY_IDENTITY_MODEL.md | Created 2026-01-19 (deferred Big 5 design) |
| PERSONALITY_TEMPLATES.md | Created 2026-01-19 (11 test archetypes) |

---

### Q: PoC vs ADR-0005 Spec Gaps (§19)

**Status**: Tracked for post-MVP (intentional simplification)
**Priority**: Low
**Created**: 2026-01-22

#### Context

The PoC implementation uses simplified gRPC contracts compared to ADR-0005 specifications. This is intentional - the ADR defines the target architecture, while the PoC proves the core concept with minimal viable contracts.

#### SalienceGateway Service

| Aspect | ADR-0005 §4.5 Spec | PoC Implementation |
|--------|--------------------|--------------------|
| Package | `gladys.v1` | `gladys.memory` |
| Service name | `SalienceGatewayService` | `SalienceGateway` |
| RPCs | `EvaluateEvent`, `EvaluateEventBatch`, `ModulateSalience` | `EvaluateSalience` only |
| Request | Full `Event` + `EvaluationContext` | Flat fields (event_id, source, raw_text, etc.) |
| Response | Enriched event + relevant memories + user profile | Salience vector + from_cache + matched_heuristic_id |

#### Rationale for Simplification

1. **Minimal viable path**: PoC needs to prove event → salience → routing works
2. **Avoid premature complexity**: Rich context can be added when needed
3. **Faster iteration**: Simpler contracts = faster debugging
4. **Memory retrieval deferred**: `relevant_memories` requires additional integration

#### Post-MVP Expansion Path

1. Add `EvaluateEventBatch` for throughput optimization
2. Add `ModulateSalience` for Executive feedback loop
3. Expand request to include `EvaluationContext` (active goals, focus entities)
4. Expand response to include relevant memories and user profile snapshot
5. Migrate to `gladys.v1` package for consistency

**No Action Required**: This is documentation of intentional scope limitation.

---

## Resolved

### R: Audit System Design (§7)

**Decision**: See ADR-0012
**Date**: 2026-01-18
**ADR**: [ADR-0012](../../adr/ADR-0012-Audit-Subsystem.md)

#### Architecture

- Audit lives OUTSIDE brain, but readable by it
- Append-only, no compaction, immutable
- Brain can READ audit for context but cannot MODIFY

#### Storage

- Three tiered tables: `audit_security` (Merkle), `audit_actions` (hash), `audit_observations` (light)
- Event type taxonomy: `category.subject.action` with `source` as separate field
- Tiered storage: hot (SSD) → warm (HDD) → cold (archive)

#### Retention

- Per-event-type, configurable: -1=forever, >0=N days, 0=don't audit
- Policy hierarchy: System Defaults → Org Policy (locked) → User Preferences
- Security events default to forever; sensor observations default to 30 days

#### Access

- Separate query interface from memory (structured, not semantic)
- No delete before retention expiry (no exceptions)

#### Remaining Open

1. Plugin manifest schema for declaring emitted event types
2. Export format (JSON lines vs Parquet)
3. Merkle tree implementation choice
4. Cross-device audit sync

---

### R: Orchestrator Language (§18)

**Decision**: Python
**Date**: 2026-01-22

See:
- [SUBSYSTEM_OVERVIEW.md §3](../SUBSYSTEM_OVERVIEW.md)
- [ORCHESTRATOR_IMPL_PROMPT.md](../ORCHESTRATOR_IMPL_PROMPT.md)

Rationale: ML ecosystem, rapid prototyping, team familiarity. Performance-critical paths handled by Rust memory fast-path.

---

## Reference: Validation Use Cases

### UC3: Voice Interaction (DAG Processing)

```
[Microphone] → [STT Preprocessor] ──┬→ [Semantic Meaning] → Salience → Executive → [TTS]
                                    │
              [Tone Preprocessor] ──┘
```

Tests: DAG preprocessor model, parallel execution

### UC6: Multi-Modal Analysis

```
[Screen Capture] → [OCR] ────────────┐
                                     ├→ [Context Analyzer] → Salience → Executive
[Audio] → [STT] → [Speaker ID] ──────┘
```

Tests: Complex DAG, multiple sensor sources merging
