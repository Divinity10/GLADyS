# Resource Allocation: Accuracy-Latency Tradeoff

How GLADyS allocates limited compute to maximize response quality and timeliness — two goals that are inherently in tension.

**Last updated**: 2026-01-31

---

## Framing

The core problem is NOT "how to handle high event volume." High volume is one manifestation. The actual problem: **GLADyS has a finite compute budget and must decide how to spend it across events that vary in urgency, complexity, and importance.**

This shows up as:
- A fire event repeating 100x/second — volume problem, but really a "don't re-spend budget on redundant work" problem
- A single complex reasoning request — no volume, but latency is high because the work is genuinely hard
- 200 Minecraft events/second — volume AND complexity, because each event might matter

The System 1/2 architecture already embodies this tradeoff: heuristics are fast/approximate (low cost, lower accuracy ceiling), LLM reasoning is slow/accurate (high cost, higher accuracy ceiling). The question is how to make good allocation decisions at runtime.

### Why This Matters for Phase 1

Phase 1's convergence test assumes low volume (manual events). But the **design of the heuristic firing threshold IS a resource allocation decision** — "when is a heuristic good enough to skip the LLM?" That's accuracy-latency tradeoff at its most basic. Getting the framing right now prevents rework later.

---

## Open Questions

### Q: What models exist for balancing competing objectives under resource constraints?

**Status**: Research needed
**Priority**: High (framing question — affects all Phases)
**Created**: 2026-01-31

#### Context

GLADyS must balance two objectives in tension:
- **Timeliness**: Respond quickly (latency)
- **Accuracy**: Respond correctly (quality)

Spending more compute improves accuracy but increases latency. Spending less reduces latency but risks wrong answers.

#### Research Areas

These are known fields that study this class of problem. Research needed to evaluate applicability:

| Field | Concept | Potential Relevance |
|-------|---------|---------------------|
| **Decision theory** | Expected utility maximization | Formal framework for choosing between options with uncertain outcomes under constraints |
| **Multi-objective optimization** | Pareto frontiers, weighted objectives | Finding the best tradeoff curve between accuracy and latency |
| **ML serving systems** | Cascade models, early exit, speculative execution | Proven patterns for "try cheap first, escalate if needed" |
| **Real-time systems** | Anytime algorithms, imprecise computation | Algorithms that produce progressively better answers as time allows |
| **Cognitive science** | System 1/2 (Kahneman), dual-process theory | GLADyS's architecture already draws from this — how deep does the analogy go? |
| **Economics** | Explore-exploit, optimal stopping, multi-armed bandits | When to use what you know vs. invest in learning more |
| **Queueing theory** | Priority scheduling, admission control | How to order and selectively drop work under load |

#### Questions to Answer

1. Is there a formal model that maps well to GLADyS's System 1/2 switching? (Not just analogy — actual math we could implement)
2. What system architectures support this class of problem? (Patterns, not products)
3. How do cascade/early-exit models handle the "confidence threshold" decision? (Directly analogous to heuristic firing threshold)
4. Is "expected value" the right objective function? Or is it risk-adjusted expected value (penalize wrong answers more than slow answers)?

#### Relationship to Existing Design

- **System 1/2 (ADR-0010)**: Already the core architecture. This question asks: is the switching logic optimal?
- **Latency profiles (infrastructure.md §4/§11)**: Defines latency budgets per context. This question asks: how to stay within budget while maximizing accuracy?
- **Confidence threshold**: Currently a static config value. This question asks: should it be dynamic?
- **§30 (Orchestrator vs Executive boundary)**: Proposes Executive decides heuristic-vs-LLM. This question provides the theoretical basis for HOW it decides.

---

### Q: Dynamic Heuristic Behavior

**Status**: Open — design needed
**Priority**: Medium (Phase 2 implementation, Phase 1 framing)
**Created**: 2026-01-31

#### Problem

Current heuristics are static: "if condition matches, then response." This breaks under two real scenarios:

**Scenario A — Redundant processing**: Fire event at 20 feet fires 100x/second. Each invocation re-evaluates the same situation. The system should recognize "I already processed this" and reuse the prior response.

**Scenario B — Meaningful change within repetition**: Fire moves from 20 → 19 feet (ignore) → 18 feet (significant change — process). The system needs to detect when a repeated event carries new information.

#### Possible Approaches

These are not mutually exclusive:

**1. Meta-heuristics (suppression rules)**

A layer that decides whether to invoke heuristic evaluation at all.

```
If similar event processed within T seconds → reuse last response
```

- Pro: Simple, massive volume reduction
- Con: Needs good "similar" definition; risks missing meaningful changes
- Where: Could live in preprocessor, orchestrator, or salience

**2. Conditional suppression ("unless Z")**

Extend heuristic conditions with exception clauses.

```
If similar event processed within T seconds → suppress
UNLESS key value changes by >= threshold (e.g., salience axis shifts +/- 10%)
```

- Pro: Preserves meaningful changes
- Con: More complex, needs per-axis thresholds, tuning surface grows
- Where: Salience or heuristic evaluation layer

**3. Event-response map (short-circuit cache)**

Cache recent event→response pairs. For matching events, replay the cached response without hitting executive at all.

```
event_hash → { response, timestamp, confidence }
```

- Pro: Fastest possible path for exact/near repeats
- Con: Stale responses if context changed; needs invalidation strategy
- Where: Orchestrator or a new "response cache" layer
- Relationship: This IS a form of System 1 — a cache over System 2 outputs

**4. Preprocessor filtering (domain-aware)**

Domain-specific preprocessors that understand event semantics and can filter/aggregate before orchestrator sees events.

- Pro: Domain knowledge improves both accuracy AND performance; parallel processing
- Con: Per-domain work; requires sensor contract design
- Where: Between sensor and orchestrator

#### Relationship to Resource Allocation

All four approaches are strategies for **reducing compute spend on low-value work** so budget is available for high-value work. They differ in where the decision is made (before vs during vs after evaluation) and what information is available at that point.

#### Design Decision Needed

These mechanisms could be:
- **Same mechanism at different layers** (a general "should I process this?" gate)
- **Complementary layers** (preprocessor handles domain-specific, orchestrator handles general)
- **Evolutionary** (start with #1, add #2 when data shows which changes matter)

See also: §36 (Event Condensation Strategy) in cross-cutting.md — overlapping concern.

---

### Q: Concurrent Event Processing

**Status**: Open — design needed
**Priority**: Medium (Phase 2 implementation, configurable stub in Phase 1)
**Created**: 2026-01-31

#### Problem

The orchestrator worker loop processes one event at a time (`event_queue.py:177-198`). The executive handles one event per RPC call (`gladys_executive/server.py:375-456`). LLM responses have variable latency (seconds). This means the system processes events at LLM speed regardless of how fast the heuristic path could handle them.

#### Current Bottleneck

```
Event Queue → [Worker dequeues 1] → [Process 1] → [Wait for LLM...] → [Done] → [Dequeue next]
```

During the LLM wait, the queue grows and heuristic-path events that could resolve in <100ms sit idle.

#### Options

| Approach | Change | Benefit | Risk |
|----------|--------|---------|------|
| **N concurrent workers** | Configurable worker pool in event_queue | Parallel processing, heuristic events don't wait behind LLM events | Resource contention; need to handle ordering |
| **Separate queues by path** | Heuristic queue (fast) + LLM queue (slow) | Fast path never blocked by slow path | How to know the path before evaluation? |
| **Async dispatch** | Fire-and-forget to executive, collect responses | Non-blocking orchestrator | Response ordering; harder error handling |
| **Batched LLM calls** | Send N events as one prompt | Fewer LLM round-trips | Attribution harder; quality may drop |

#### Recommendation

Start with configurable concurrent workers (N=1 for Phase 1, increase for Phase 2). This is the simplest change that unblocks the most value. Other approaches are refinements.

#### Implementation Note

The `_worker_loop` in `event_queue.py` could become N workers pulling from the same priority queue. The priority queue already handles ordering. Key design question: should workers be typed (fast-path vs slow-path) or generic?

---

### Q: Sensor Event Contract Design

**Status**: Open — design needed
**Priority**: High (Phase 1 W1 prerequisite)
**Created**: 2026-01-31

#### Context

Runescape exploratory work revealed real sensor characteristics:
- Event volume can be very high (up to 200/sec for game state)
- Events have required and conditional fields depending on event type
- Field presence is constrained by other field values (e.g., `damage_type: "fire"` implies `damage_per_tick`, `duration`, `max_dmg` exist)

#### Design Needed

**1. Composable event interfaces**

The sensor contract is NOT a single flat schema. It's a composition of interfaces, where a concrete event conforms to multiple interfaces determined by its attributes.

```
Base Event Interface (all events, GLADyS core):
  { event_type, event_time, event_source, ... }

+ Delivery Pattern Interface (determined by event_type, GLADyS core):
  event_type: "event"  → { }  (push — something happened, base fields sufficient)
  event_type: "poll"   → { poll_interval, previous_value? }  (periodic state snapshot)
  event_type: "stream" → { sample_rate, sequence_id }  (continuous data — not Phase scope)

+ Domain Interface (pack-defined, e.g. gaming.combat, home.climate):
  { damage_type, spell_type, ... }

+ Domain Sub-Interface (conditional on domain fields):
  damage_type: "fire" → { damage_per_tick, duration, max_dmg }
  damage_type: "physical" → { damage_amount, armor_reduction }
```

A concrete event = base + delivery pattern interface + applicable domain interfaces + applicable domain sub-interfaces. The `event_type` is a GLADyS-owned top-level discriminator that determines delivery-pattern attributes. Domain content is orthogonal — a `poll` from a temperature sensor and a `poll` from a game state checker share delivery-pattern attributes but have completely different domain payloads.

The sensor/pack manifest declares which interfaces the sensor can produce and the discriminator rules.

**Why event_type matters for volume management**: The orchestrator can apply different dedup/suppression strategies per delivery pattern without needing domain knowledge. `poll` events with unchanged values are prime suppression candidates. `event` types inherently signal "something changed." `stream` events need windowing/aggregation. This is a natural integration point between the sensor contract and the resource allocation problem.

**Design questions for interface composition**:
- Who defines interfaces? Base = GLADyS core. Domain = packs. Cross-domain (e.g., `location: {x, y, z, zone}` used by both gaming and home automation) = where?
- Who validates composition? Does the orchestrator check that all required fields from each claimed interface are present, or is it trust-based?
- How does the consumer know what it's getting? Options: (a) inspect discriminator fields to infer interfaces, (b) event self-describes with an interface list, (c) consumer looks up sensor's manifest to know what interfaces it produces
- How are interfaces declared? JSON Schema with `$ref` composition? A simpler manifest format? Code-level type definitions?
- Interface versioning: when a domain interface adds a field, how is backward compatibility handled?

**2. Driver → Sensor interface**

- Driver (mod/integration) sends raw data to sensor
- Protocol between driver and sensor is driver-specific (whatever works for that integration)
- Sensor normalizes to the composable interface model above
- This boundary is where domain-specific format converts to GLADyS-standard format

**3. Sensor → Orchestrator interface**

- JSON over gRPC (PublishEvents RPC already exists)
- Sensor batching: should sensors batch events or send individually?
- Backpressure: how does orchestrator signal "slow down" to sensor?

**4. Preprocessor role**

- When should a sensor include a preprocessor vs send raw events?
- Preprocessors handle: enrichment, filtering, aggregation, state tracking
- Preprocessors must be stateless or have well-defined state scope (no shared mutable state)
- Decision: preprocessor as part of sensor pack, or as separate orchestrator-side component?

#### Sensor Type Patterns

| Pattern | How it works | Examples | Volume profile |
|---------|-------------|----------|---------------|
| **`event` (push)** | Driver sends events when things happen | Game combat, Discord message, doorbell ring | Bursty — zero to hundreds/sec |
| **`poll` (periodic)** | Sensor periodically checks state | File watcher, system monitor, temperature | Steady — configurable interval |
| **`stream` (continuous)** | Continuous data flow | Audio, video, real-time telemetry | Constant high — not Phase scope |

These map to the `event_type` discriminator in the base event interface. Each pattern has different delivery-pattern attributes and different volume management characteristics.

Phase 1 needs one sensor. The contract should accommodate `event` and `poll` patterns. `stream` is deferred.

#### Open Questions

1. Should the event schema be self-describing (fields declare their own types) or schema-referenced (point to a schema definition)?
2. How much validation does the orchestrator do on incoming events? (Fail fast vs permissive)
3. Should conditional field rules live in the sensor manifest or in the event schema?

---

## Resolved

*(None yet — all questions in this file are open)*


