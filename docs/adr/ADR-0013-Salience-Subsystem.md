# ADR-0013: Salience Subsystem

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2026-01-19 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Salience |
| **Tags** | salience, attention, filtering, routing |
| **Depends On** | ADR-0001, ADR-0003, ADR-0005, ADR-0010 |

---

## 1. Context and Problem Statement

The Salience Gateway is referenced throughout the GLADyS architecture (ADR-0001 Section 7) but never fully specified. It sits at the critical junction between perception (sensors/preprocessors) and cognition (Executive), determining what deserves attention.

Without specification, we cannot:

- Implement the filtering logic that prevents Executive overload
- Define the attention budget that bounds processing cost
- Establish contracts between sensors, salience, and Executive
- Integrate learned heuristics (ADR-0010) into salience evaluation

**Core problem**: How do we decide what's "important" from a continuous stream of events, in a way that's computationally bounded, context-aware, and learnable?

---

## 2. Decision Drivers

1. **Bounded attention**: The Executive (LLM) is expensive. Most events don't need its attention. Salience must filter aggressively.

2. **Context sensitivity**: What's salient in gaming (threat detection) differs from home automation (comfort deviation). One-size-fits-all thresholds won't work.

3. **Learning integration**: ADR-0010 defines heuristics and learned patterns. Salience should leverage these for fast evaluation (System 1).

4. **Latency budget**: ADR-0001 allocates 100ms for salience evaluation. Must be achievable with or without GPU.

5. **Graceful degradation**: Under load, salience should prioritize safety-critical events, not crash or drop randomly.

6. **Feedback responsiveness**: Executive modulation (suppress, heighten, habituate) must affect salience in real-time.

---

## 3. Decision

We implement the Salience Gateway as a stateful filtering and routing component with:

- **Multi-stage evaluation**: Fast heuristic check (System 1) → optional deep evaluation (embedding-based)
- **Attention budget**: Token-based capacity with priority queuing
- **Context profiles**: Domain-specific thresholds and dimension weights
- **Learning integration**: Heuristics from ADR-0010 as first-pass filters
- **Executive feedback**: Real-time modulation of thresholds and suppression lists

---

## 4. Architecture Overview

### 4.1 Position in Pipeline

```
Sensors → Preprocessors → [SALIENCE GATEWAY] → Executive
                              ↓         ↑
                           Memory    Feedback
```

### 4.1.1 The "Amygdala" Architecture

Salience and Memory's fast path work together as the functional equivalent of the brain's amygdala - the fast threat/opportunity detector:

- **Salience Gateway** (Python): Receives events, applies evaluation pipeline, routes based on scores
- **Memory Fast Path** (Rust): Provides heuristic lookup, novelty detection, pattern matching (<5ms)
- **Together**: Fast context-aware salience evaluation without LLM latency

Per ADR-0001 §5.1, Salience and Memory share a process to avoid IPC overhead on this hot path. The Python Salience layer queries the Rust fast path for:

- Threat/opportunity pattern matches (heuristics table)
- Novelty scores (recent event similarity)
- Context retrieval (what does this event mean in current situation?)

This enables the Stage 2 heuristic evaluation (5-20ms) without requiring embedding generation or LLM inference for most events.

The Salience Gateway:

- **Receives**: Processed events from preprocessors (or raw events from sensors without preprocessors)
- **Outputs to Executive**: Filtered, prioritized events that warrant attention
- **Outputs to Memory**: All events (salience scores attached) for episodic storage
- **Receives from Executive**: Modulation signals (suppress, heighten, habituate)

### 4.2 Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     SALIENCE GATEWAY                             │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │   Intake     │ → │  Evaluator   │ → │   Attention Manager  │ │
│  │   Buffer     │   │  Pipeline    │   │                      │ │
│  └──────────────┘   └──────────────┘   │  • Budget tracking   │ │
│                           ↓            │  • Priority queue    │ │
│                    ┌──────────────┐    │  • Executive dispatch│ │
│                    │   Context    │    └──────────────────────┘ │
│                    │   Manager    │              ↓              │
│                    │              │    ┌──────────────────────┐ │
│                    │ • Domain     │    │   Memory Writer      │ │
│                    │ • Thresholds │    │                      │ │
│                    │ • Weights    │    │  All events + scores │ │
│                    └──────────────┘    └──────────────────────┘ │
│                           ↑                                      │
│                    ┌──────────────┐                              │
│                    │  Modulation  │ ← Executive feedback         │
│                    │  Controller  │                              │
│                    └──────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Salience Computation

### 5.1 Evaluation Pipeline

Events pass through a multi-stage pipeline, with early exit for efficiency:

```
Event → [Suppression Check] → [Heuristic Eval] → [Deep Eval?] → [Threshold Gate] → Output
             ↓ drop                  ↓                               ↓ drop
                              scores + fast                    below threshold
```

**Stage 1: Suppression Check** (~1ms)

- Check suppression list (Executive said "ignore X")
- Check habituation cache (seen this pattern recently)
- Early exit if suppressed

**Stage 2: Heuristic Evaluation** (~5-20ms)

- Apply learned heuristics (ADR-0010 System 1)
- Rule-based dimension scoring
- Fast, no model inference

**Stage 3: Deep Evaluation** (optional, ~50-80ms)

- Embedding generation for semantic matching
- Small model inference for nuanced dimensions
- Only triggered when heuristics are uncertain or event is potentially high-salience

**Stage 4: Threshold Gating**

- Compare computed salience vector against context-specific thresholds
- Events below all thresholds → memory only (not Executive)
- Events above any threshold → attention queue

### 5.2 Dimension Computation

Each salience dimension (from ADR-0001 Section 7.1) has specific computation strategies:

| Dimension | Computation Method | Notes |
|-----------|-------------------|-------|
| threat | Heuristic rules + learned patterns | Fast path critical for gaming |
| opportunity | Pattern matching + goal alignment | Requires goal context |
| humor | Lightweight classifier | Core to personality - include in MVP |
| novelty | Similarity to recent events | Embedding-based, can cache |
| goal_relevance | Active goal matching | Requires Executive context |
| social | Entity recognition (is person?) | Preprocessor output |
| emotional | Sentiment/tone from preprocessor | Audio tone, text sentiment |
| actionability | Domain-specific rules | "Can I do something about this?" |
| habituation | Recency-weighted frequency | Fast lookup in cache |

**MVP Dimensions**: threat, opportunity, goal_relevance, novelty, humor, habituation. Humor is core to personality (Murderbot-style interaction).

### 5.3 Context-Aware Evaluation

Different domains have different salience profiles:

```yaml
contexts:
  gaming:
    active_dimensions: [threat, opportunity, goal_relevance]
    weights:
      threat: 2.0        # Amplify threat detection
      opportunity: 1.5
      goal_relevance: 1.0
    thresholds:
      threat: 0.3        # Lower threshold = more sensitive
      opportunity: 0.5
      goal_relevance: 0.6

  home:
    active_dimensions: [threat, novelty, actionability]
    weights:
      threat: 1.0
      novelty: 1.5       # Unusual events matter more at home
      actionability: 1.0
    thresholds:
      threat: 0.5        # Higher threshold = less jumpy
      novelty: 0.4
      actionability: 0.6
```

**Context Detection**: Orchestrator signals active context based on:

- Active application (Minecraft → gaming)
- Time of day
- Sensor availability (gaming sensors active → gaming context)
- Explicit user mode switch

### 5.3.1 Cross-Context Event Routing

Events may arrive from sources outside the primary context (e.g., doorbell during gaming). We use a **hybrid claim model**:

1. Event arrives with source metadata (`source: home_assistant.doorbell`)
2. Primary context (gaming) evaluates first
3. If source doesn't match primary context's domain, check if another active context claims it
4. Claiming context's thresholds/weights apply to that event

**Source claims** (configured per context):

```yaml
context_claims:
  home:
    claims_sources: ["home_assistant.*", "ring.*", "nest.*"]

  gaming:
    claims_sources: ["minecraft.*", "aperture.*", "runelite.*"]

  work:
    claims_sources: ["slack.*", "teams.*", "calendar.*"]
```

**Conflict resolution** (both contexts claim same source):

- Evaluate with BOTH profiles
- Take MAX salience across contexts
- Log which context "won" for learning

**Rationale**: This ensures a doorbell event during gaming gets evaluated with home-appropriate sensitivity (likely higher threat/novelty), not gaming thresholds that would filter it out.

### 5.4 Learning Integration

The Salience Gateway reads from ADR-0010's learning stores:

**Heuristics** (heuristics table):

- Fast rules: "If event.source = 'minecraft' AND event.type = 'damage' THEN threat = 0.8"
- Applied in Stage 2 (heuristic evaluation)

**Learned Patterns** (learned_patterns table):

- Bayesian beliefs about what's typically salient
- "Player usually cares about inventory changes" → boost goal_relevance for inventory events

**Feedback Integration**:

- When Executive acts on an event → positive signal
- When Executive ignores a forwarded event → negative signal
- Salience learns what the Executive actually wants

### 5.5 Cold Start (Bootstrap)

Before learning has accumulated, salience uses conservative defaults:

**Phase 1: First hours (no learning data)**

- All thresholds start LOW (0.3 across dimensions) → forward more, filter less
- No active suppression patterns
- Context = "general" until domain detected

**Phase 2: Context detection kicks in**

- Orchestrator detects active app → switches to domain-specific profile
- Bootstrap profiles ship with sensible defaults:

```yaml
bootstrap_contexts:
  gaming:
    detection:
      process_match: ["minecraft", "runelite", "java"]  # RuneLite is Java
    thresholds: {threat: 0.2, opportunity: 0.4, goal_relevance: 0.5, humor: 0.3}
    note: "Threat-sensitive, humor-enabled"

  home:
    detection:
      sensor_active: ["home_assistant_integration"]
    thresholds: {threat: 0.4, novelty: 0.3, actionability: 0.5, humor: 0.4}
    note: "Novelty-focused, moderate sensitivity"

  general:
    detection:
      fallback: true
    thresholds: {all: 0.4}
    note: "Conservative middle ground"
```

**Phase 3: Learning refines (days/weeks)**

- Feedback adjusts thresholds per pattern
- Heuristics accumulate from Executive behavior
- Suppression patterns learned from user corrections

**Design principle**: Better to forward too much early (annoy user) than miss important events (lose trust). Learning will tighten filtering over time.

---

## 6. Attention Budget

### 6.1 Capacity Model

The Executive has bounded processing capacity. We model this as a token budget:

```
Budget = tokens_per_tick × tick_rate

Example:
  tokens_per_tick = 1000  (roughly one event with context)
  tick_rate = 1 Hz
  budget = 1000 tokens/second
```

**Token costs** (approximate):

| Item | Tokens |
|------|--------|
| Event context (source, type, timestamp) | 50 |
| Event payload (description) | 100-500 |
| Relevant memory retrieval | 200-500 |
| Salience rationale | 50-100 |

### 6.2 Priority Queuing

When events exceed budget, priority queue determines what reaches Executive:

```
Priority Score = weighted_salience × urgency_factor × recency_bonus

where:
  weighted_salience = Σ(dimension_score × dimension_weight)
  urgency_factor = f(threat_level, time_sensitivity)
  recency_bonus = decay function (newer = higher)
```

**Queue behavior**:

- Events enqueue with priority score
- Highest priority dequeued first
- Events expire after TTL (default: 5 seconds for gaming, 30 seconds for home)
- Expired events logged to memory but never reach Executive

### 6.3 Overload Handling

When queue depth exceeds threshold (sustained overload):

1. **Raise thresholds**: Temporarily increase salience thresholds (filter more aggressively)
2. **Collapse similar events**: Merge "5 damage events in 2 seconds" → "sustained damage"
3. **Safety carve-out**: Threat events with score > 0.9 bypass normal queue (dedicated budget)
4. **Notify Executive**: "High event volume - some events may be dropped"
5. **Log for learning**: Overload periods are learning opportunities (what got dropped? was it actually important?)

---

## 7. Filtering and Routing

### 7.1 Routing Decisions

Every event gets one of these outcomes:

| Outcome | Condition | Destination |
|---------|-----------|-------------|
| **Forward** | Above threshold, within budget | Executive + Memory |
| **Queue** | Above threshold, over budget | Priority queue → Executive + Memory |
| **Store** | Below threshold (not interesting) | Memory only |
| **Suppress** | Actively blocked (Executive command or habituation) | Debug log only |

**Store vs Suppress distinction**:

- **Store**: Low salience scores, but not blocked. Goes to memory for potential retrospective analysis.
- **Suppress**: Actively inhibited by Executive command ("stop telling me about X") or habituation limit. This is an explicit signal, not just "low scores."

This mirrors biological inhibition: GABA-mediated suppression is an active process, distinct from simply not reaching activation threshold.

### 7.2 Memory Routing

All events (except dropped) go to memory with salience scores attached:

```protobuf
message SalienceAnnotatedEvent {
  Event event = 1;
  SalienceVector salience = 2;
  RoutingOutcome outcome = 3;  // FORWARDED, QUEUED, STORED_ONLY, DROPPED
  string context = 4;          // Active context at evaluation time
}
```

This enables:

- Retrospective analysis ("what did I miss?")
- Learning signal ("events I dropped but user asked about later")
- Episode construction (salience informs episode boundaries)

### 7.3 Executive Interface

Events forwarded to Executive include:

```protobuf
message SalientEvent {
  Event event = 1;
  SalienceVector salience = 2;
  repeated MemoryContext relevant_memories = 3;  // Pre-fetched context
  string suggested_response_type = 4;  // URGENT, INFORMATIONAL, OPPORTUNISTIC
  float confidence = 5;  // How confident are we this deserves attention?
}
```

**suggested_response_type** hints:

- `URGENT`: High threat, needs immediate response
- `INFORMATIONAL`: Worth mentioning when convenient
- `OPPORTUNISTIC`: Good moment for proactive engagement

---

## 8. Executive Feedback

### 8.1 Modulation Signals

Executive can send real-time feedback to adjust salience behavior:

```protobuf
message SalienceModulation {
  oneof modulation {
    Suppress suppress = 1;        // "Stop alerting me about X"
    Heighten heighten = 2;        // "Watch for X specifically"
    Habituate habituate = 3;      // "This is now normal"
    AdjustThreshold adjust = 4;   // "Be more/less sensitive to dimension Y"
  }
}

message Suppress {
  EventPattern pattern = 1;       // What to suppress
  Duration duration = 2;          // How long (or until manually cleared)
}

message Heighten {
  EventPattern pattern = 1;       // What to watch for
  float boost = 2;                // Multiplier for salience scores
  Duration duration = 3;
}

message Habituate {
  EventPattern pattern = 1;       // What's now normal
  float decay_rate = 2;           // How quickly to restore sensitivity
}
```

### 8.2 Feedback Learning

Modulation signals become learning data:

- Repeated `suppress` for pattern X → learn to reduce base salience
- Repeated `heighten` for pattern Y → learn to increase base salience
- Executive action on event → positive reinforcement
- Executive ignore of forwarded event → negative signal (should we have filtered?)

---

## 9. gRPC Interface

### 9.1 Service Definition

```protobuf
service SalienceGateway {
  // Stream events from preprocessors/sensors
  rpc StreamEvents(stream Event) returns (stream SalienceAck);

  // Get current salience state
  rpc GetState(Empty) returns (SalienceState);

  // Executive feedback
  rpc Modulate(SalienceModulation) returns (ModulationAck);

  // Configuration
  rpc SetContext(ContextSwitch) returns (ContextAck);
  rpc UpdateThresholds(ThresholdUpdate) returns (ThresholdAck);
}
```

### 9.2 Salience → Executive Stream

```protobuf
service ExecutiveIngress {
  // Salience streams salient events to Executive
  rpc StreamSalientEvents(stream SalientEvent) returns (stream ExecutiveAck);
}
```

---

## 10. Performance Requirements

| Metric | Target | Rationale |
|--------|--------|-----------|
| Heuristic evaluation latency | <20ms P95 | Most events should be fast |
| Deep evaluation latency | <80ms P95 | Within 100ms budget |
| Events/second throughput | >100 | Gaming can be high-frequency |
| Memory overhead | <100MB | Caches, queues, state |
| Queue depth before overload | 50 events | Tunable per context |

---

## 11. Embedding Model Strategy

### 11.1 Model Options

| Model | Dim | Latency | Quality | License | Notes |
|-------|-----|---------|---------|---------|-------|
| all-MiniLM-L6-v2 | 384 | ~5ms | Good | Apache 2.0 | Current ADR-0004 default, widely used |
| all-mpnet-base-v2 | 768 | ~15ms | Better | Apache 2.0 | Higher quality, 2x storage |
| gte-small | 384 | ~5ms | Good | MIT | Alibaba, good benchmark scores |
| nomic-embed-text | 768 | ~10ms | Good | Apache 2.0 | 8K context window |
| bge-small-en | 384 | ~5ms | Good | MIT | BAAI, strong on MTEB |

**MVP recommendation**: all-MiniLM-L6-v2

- Matches ADR-0004 schema (384 dimensions)
- Fast enough for 80ms deep-eval budget
- Well-understood, large community
- Good baseline to improve from

### 11.2 Evaluation Criteria

When evaluating a model change:

| Criterion | How to Measure | Target |
|-----------|----------------|--------|
| **Inference latency** | Benchmark on target hardware (CPU, no GPU) | <10ms P95 |
| **Search quality** | Manual eval: "Does this find what I expect?" | Subjective but important |
| **MTEB benchmark** | Published scores for retrieval tasks | >0.4 on retrieval |
| **Memory footprint** | Model size + (dim × 4 bytes × row count) | <500MB total for 100K events |
| **License** | Commercial use allowed? | Apache 2.0 or MIT |
| **Context window** | Max input tokens | >512 tokens |

### 11.3 Triggers for Re-evaluation

| Trigger | Action |
|---------|--------|
| Semantic search complaints ("why didn't you find X?") | Evaluate search quality with test queries |
| Latency exceeds 80ms P95 | Profile, consider smaller model |
| New model shows >10% MTEB improvement | Benchmark on our data |
| Dimension change needed for quality | Plan migration (see 11.4) |

### 11.4 Migration Impact Assessment

**Same dimension change** (e.g., all-MiniLM-L6-v2 → gte-small):

- **Schema**: No change
- **Data**: Existing embeddings semantically drift (query with new model, data has old embeddings)
- **Strategy**: Incremental re-embedding during sleep mode
- **Tracking**: Add `embedding_model VARCHAR(64)` to tables, prioritize same-model matches
- **Disruption**: LOW - search quality degrades gracefully, improves as re-embedding completes

**Different dimension change** (e.g., 384 → 768):

- **Schema**: Column type change (`vector(384)` → `vector(768)`)
- **Data**: Full re-embedding required, can't mix dimensions
- **Strategy**:
  1. Add new column `embedding_768 vector(768)`
  2. Re-embed incrementally during sleep mode
  3. Switch queries to new column when >90% complete
  4. Drop old column
- **Disruption**: MEDIUM-HIGH - requires careful migration, temporary storage overhead

**Recommendation**: Design for same-dimension changes being routine. Avoid dimension changes unless quality gap is significant (>15% on benchmarks). The 384→768 jump doubles storage and requires schema migration.

### 11.5 Schema Preparation

To make model changes easier, ADR-0004 tables should track embedding provenance:

```sql
-- Suggested addition to episodic_events, semantic_facts, episodes, learned_patterns
embedding_model VARCHAR(64) DEFAULT 'all-MiniLM-L6-v2',
embedding_version INTEGER DEFAULT 1  -- Increment on re-embedding
```

This enables:

- Query-time filtering by model (prioritize same-model matches)
- Tracking re-embedding progress
- Rollback if new model underperforms

---

## 12. Habituation Decay

### 12.1 Decay Model

Suppressed patterns recover sensitivity over time using **exponential decay**:

```
sensitivity(t) = 1 - (1 - min_sensitivity) × e^(-t / tau)

where:
  t = time since last suppression
  tau = time constant (context-specific)
  min_sensitivity = floor (never fully suppress)
```

**Why exponential?**

- Matches biological habituation recovery
- Fast initial recovery, slow asymptotic approach to full sensitivity
- Single parameter (tau) to tune
- Can approximate linear with large tau if needed

### 12.2 Configuration

```yaml
habituation:
  tau_seconds:
    gaming: 60       # Fast recovery - gaming is dynamic
    home: 300        # Slower - home events less urgent
    work: 180        # Moderate
    default: 120     # 2 minutes

  min_sensitivity: 0.1   # Never fully suppress (10% floor)

  burst_detection:
    threshold: 5         # Events in window triggers burst mode
    window_seconds: 10   # Window for burst detection
    burst_tau: 30        # Faster recovery during burst
```

**min_sensitivity**: Ensures even heavily habituated patterns can break through if they become extreme (e.g., doorbell rings 10 times → something's wrong).

**burst_detection**: If the same pattern fires repeatedly in a short window, we enter "burst mode" with faster recovery - the system recognizes something unusual is happening.

### 12.3 Implementation

```python
def get_sensitivity(pattern_id: str, context: str) -> float:
    last_suppression = get_last_suppression_time(pattern_id)
    if last_suppression is None:
        return 1.0

    elapsed = now() - last_suppression
    tau = config.habituation.tau_seconds.get(context, config.habituation.tau_seconds.default)
    min_sens = config.habituation.min_sensitivity

    sensitivity = 1 - (1 - min_sens) * math.exp(-elapsed / tau)
    return sensitivity
```

---

## 13. Open Questions

1. ✅ **Embedding model selection**: Resolved - start with all-MiniLM-L6-v2, evaluation criteria and migration strategy documented (Section 11).

2. ✅ **Habituation decay**: Resolved - exponential decay with configurable tau per context (Section 12).

3. ✅ **Cross-context events**: Resolved - hybrid claim model (Section 5.3.1).

4. ✅ **Cold start**: Resolved - conservative bootstrap thresholds (Section 5.5).

5. **Multi-user**: Different users have different salience preferences - deferred to post-MVP.

---

## 12. Consequences

### 12.1 Positive

1. **Bounded Executive load**: Attention budget prevents runaway costs
2. **Context-appropriate filtering**: Gaming mode vs home mode have different sensitivities
3. **Learning integration**: Salience improves over time
4. **Graceful degradation**: Overload is handled, not crashed through

### 12.2 Negative/Risks

1. **Tuning complexity**: Many thresholds and weights to configure
2. **False negatives**: Aggressive filtering might miss important events
3. **Context switching latency**: Changing contexts requires threshold reload
4. **Learning cold start**: Poor initial filtering until heuristics learned

### 12.3 Mitigations

- Start with conservative thresholds (forward more, filter less)
- Log all routing decisions for retrospective analysis
- Provide "safety net" paths for high-threat events
- Bootstrap with reasonable defaults, learn quickly

---

## 13. Related Decisions

- ADR-0001: GLADyS Architecture (defines salience dimensions, feedback loop)
- ADR-0003: Plugin Manifest Specification (sensors declare event types)
- ADR-0005: gRPC Service Contracts (communication patterns)
- ADR-0010: Learning and Inference (heuristics, patterns that feed salience)

---

## 14. Notes

The brain's salience network (Seeley et al., 2007) provides inspiration but not specification. Key insight: salience is not a single score but a vector of dimensions, and what's "salient" depends on context and current goals.

The attention budget concept borrows from cognitive psychology (limited attention capacity) and rate limiting (token buckets). The priority queue ensures that when capacity is exceeded, the most important events still get through.

MVP should start with simple heuristic rules and conservative thresholds, then learn appropriate filtering over time. It's better to forward too much initially than to miss important events.
