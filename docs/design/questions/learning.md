# Learning Questions

Heuristics, TD learning, pattern formation, and how GLADyS learns from experience.

**Last updated**: 2026-01-25

---

## Open Questions

### Q: TD Learning for Heuristics (§20)

**Status**: Open - needs minimal PoC design
**Priority**: High (core learning mechanism)
**Created**: 2026-01-23

#### Context

ADR-0010 defines the Learning Pipeline with System 1 (heuristics) and System 2 (LLM reasoning). The question: **how do heuristics get created and updated from successful reasoning?**

Current heuristics are assumed to exist (stored in `heuristics` table per ADR-0004 §5.6), but the mechanism for:
1. Creating heuristics from novel reasoning
2. Updating heuristic confidence based on outcomes

...is underspecified.

#### The Learning Loop (TD Learning)

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

#### Minimal PoC Requirements

To prove this architecture is achievable, we need:

1. **Outcome Tracking**: Link action to observable outcome (minimal: user feedback thumbs up/down)
2. **Prediction Recording**: Store expected salience impact with each heuristic fire
3. **Delta Calculation**: `delta = outcome_score - predicted_score`
4. **Confidence Update**: `new_confidence = old_confidence + learning_rate * delta`
5. **Heuristic Creation** (Stretch): Log successful reasoning traces for manual pattern extraction

#### What This Does NOT Require for PoC

- Automatic outcome detection (use explicit user feedback)
- Complex pattern extraction (log traces, create heuristics manually)
- Multi-step credit assignment (single action → single outcome)
- Causal inference (correlation is sufficient for PoC)

#### Open Questions

1. **Outcome attribution**: When user says "that was helpful", which heuristic/action gets credit?
2. **Delayed feedback**: User reacts 10 minutes later - how to correlate?
3. **Negative outcomes**: How to detect "that was wrong" without explicit feedback?
4. **Heuristic extraction**: What pattern format makes sense for automated creation?
5. **Exploration vs exploitation**: Should system occasionally ignore heuristics to learn?
6. **LLM agreement value**: Is there value in the LLM agreeing with a heuristic? If a heuristic fires and the LLM independently reaches the same conclusion, does that signal anything useful (e.g., boost confidence faster)?
7. **Implicit requests**: Are ALL heuristics implicit requests? A heuristic matching an event implies the user wants something done — is there a meaningful distinction between "heuristic fire" and "implicit user request"?

#### Next Steps

1. Add `predictions` table to schema (minimal: heuristic_id, event_id, predicted_outcome, timestamp)
2. Add feedback endpoint to Executive (minimal: event_id + positive/negative)
3. Implement delta calculation and confidence update in Memory
4. Log reasoning traces for future heuristic extraction

---

### Q: Heuristic Learning Infrastructure (§23)

**Status**: Partial - credit assignment UX designed; implementation deferred
**Priority**: Medium (needed for real learning, not PoC)
**Created**: 2026-01-23
**Updated**: 2026-01-24 - Credit assignment UX design agreed

#### Context

These items are required for production-quality heuristic learning but are deferred until the basic feedback loop is working end-to-end. The `feedback_events` table exists but nothing writes to it yet.

#### 23.1 Credit Assignment UX Design (Resolved)

**Design Decision: Silent Learning by Default**

The key insight: **implicit feedback > explicit feedback**. User actions (undo, override, follow-through) are more reliable signals than verbal feedback like "that was helpful."

**Core Principles**:
| Principle | Rationale |
|-----------|-----------|
| **Log, don't ask** | Interrupting workflow is worse than imperfect attribution |
| **Implicit > Explicit** | User actions are more reliable than verbal feedback |
| **Wait for patterns** | Single ambiguous feedback isn't worth clarifying |
| **Ask specific questions** | "Which?" not "Was that helpful?" |

**When to Ask vs Stay Silent**:
- **Stay Silent**: Ambiguous feedback, low-stakes, single occurrence
- **Ask Only When ALL THREE**: High stakes + pattern emerging (2-3x) + specific question possible

**Attribution Confidence Model**: Uses temporal proximity, semantic similarity, historical patterns, and ambiguity penalty to score candidates.

#### 23.2 Credit Assignment Implementation (Deferred)

**Prerequisites**:
- `ProvideFeedback` RPC endpoint (implemented)
- Event → heuristic fire log (missing)
- `feedback_events` table writes (missing)

**Config settings to add**:
- `FEEDBACK_TIME_WINDOW_SECONDS`: How far back to attribute credit (default: 60)
- `FEEDBACK_RECENCY_DECAY`: Exponential decay factor for older events (default: 0.5)
- `ASK_THRESHOLD`: Confidence gap required to ask (starts 0.7, increases to 0.85)
- `DEV_MODE`: Enable verbose logging of all attribution decisions

#### 23.3 Tuning Mode (Deferred)

**Problem**: How do you tune similarity thresholds? You need to see what *almost* matched but didn't.

**Design sketch**: Log near-misses at configurable thresholds (0.5, 0.6, 0.7, 0.8, 0.9) when `TUNING_MODE=true`.

**When to Revisit**: When running load tests or real workloads with meaningful heuristics.

---

### Q: Prediction Baseline Strategy (§27)

**Status**: Designed (PoC: Instrument only; Post-PoC: Implement learning)
**Priority**: Medium
**Created**: 2026-01-24

#### Context

TD learning requires computing prediction error: `error = actual_outcome - predicted_outcome`

The question: **What is the prediction baseline?**

#### Decision: Hybrid Baseline (Interpolation + Extrapolation)

Use a hierarchical fallback strategy:

```python
def get_prediction_baseline(event_embedding, triggered_heuristic_id=None):
    # 1. Direct: This specific heuristic has enough history
    if triggered_heuristic_id and h.fire_count >= 3:
        return h.confidence

    # 2. Similar heuristics: CBR on condition embeddings (extrapolation)
    similar_h = query_similar_heuristics(event_embedding, threshold=0.7)
    if similar_h:
        return weighted_avg([h.confidence for h in similar_h],
                           weights=[h.fire_count for h in similar_h])

    # 3. Similar episodes: Past situations with known outcomes
    similar_episodes = query_similar_episodes(event_embedding, has_outcome=True)
    if similar_episodes:
        return success_rate(similar_episodes)

    # 4. Prior: No relevant experience
    return 0.5
```

#### PoC Scope: Instrument Only

Following "Instrument Now, Analyze Later" recommendation:
1. Add `prediction` and `prediction_confidence` fields to reasoning output
2. Log outcomes (undo detection, explicit feedback, game state)
3. **Do NOT implement TD learning** - just collect data for analysis

#### Proposed Schema (Partially Implemented)

**Note**: The `heuristic_fires` table is now implemented (migration 009). See integration gaps below for remaining work.

```sql
-- These changes are design proposals for future implementation
ALTER TABLE episodic_events ADD COLUMN outcome_type VARCHAR(50);
ALTER TABLE episodic_events ADD COLUMN outcome_source VARCHAR(100);

CREATE TABLE heuristic_fires (
    id UUID PRIMARY KEY,
    heuristic_id UUID REFERENCES heuristics(id),
    event_id UUID REFERENCES episodic_events(id),
    fired_at TIMESTAMPTZ NOT NULL,
    llm_prediction FLOAT,
    llm_confidence FLOAT,
    baseline_prediction FLOAT,
    actual_outcome FLOAT,
    outcome_source VARCHAR(100)
);
```

---

### Q: Learning Loop Integration Gaps (§29)

**Status**: Open - Blockers identified, needs implementation
**Priority**: High (blocks full E2E validation)
**Created**: 2026-01-26

#### Context

Phase 2 (OutcomeWatcher) and Phase 3 (Flight Recorder) are implemented, but there are integration gaps that prevent the full implicit feedback loop from working end-to-end. These were identified during code review when Gemini's tactical fixes were found to use workarounds that don't integrate properly.

#### Gap 1: GetHeuristic RPC Missing from Proto (BLOCKER)

**Problem**: The `memory_client.py` has a `get_heuristic()` method that calls `GetHeuristic` RPC, but this RPC doesn't exist in the proto.

```python
# memory_client.py:234 - This will fail at runtime
request = memory_pb2.GetHeuristicRequest(id=heuristic_id)
response = await self._stub.GetHeuristic(request)
```

**Impact**: OutcomeWatcher needs this to dynamically fetch `condition_text` for pattern matching. Currently worked around by passing `condition_text` directly, but this means the OutcomeWatcher can't look up heuristics it wasn't pre-configured with.

**Fix Required**:
1. Add `GetHeuristic` RPC to `memory.proto`
2. Add `GetHeuristicRequest` and `GetHeuristicResponse` messages
3. Implement handler in `grpc_server.py`

#### Gap 2: feedback_source Not Propagated Through gRPC

**Problem**: `UpdateHeuristicConfidenceRequest` has no `feedback_source` field:

```protobuf
message UpdateHeuristicConfidenceRequest {
    string heuristic_id = 1;
    bool positive = 2;
    float learning_rate = 3;
    float predicted_success = 4;
    // No feedback_source field!
}
```

**Impact**: Even though `memory_client.py` accepts `feedback_source` as a parameter, it can't send it over gRPC. The storage layer then hardcodes `'explicit'`:

```python
# storage.py:598
feedback_source='explicit'  # Always 'explicit', ignoring actual source
```

This means implicit feedback is mislabeled as explicit in the Flight Recorder.

**Fix Required**:
1. Add `feedback_source` field to `UpdateHeuristicConfidenceRequest` in proto
2. Pass the field through in `grpc_server.py` handler
3. Use the parameter in storage instead of hardcoding

#### Gap 3: No E2E Test for Full Implicit Feedback Loop

**Problem**: `test_scenario_5_learning_loop.py` only tests explicit feedback. There's no test that exercises the full flow:

```
Event → Heuristic Match → Action → Outcome Event → OutcomeWatcher → Implicit Feedback → Fire Recorded with source='implicit'
```

**Impact**: We can't verify the implicit feedback loop actually works through the full Orchestrator flow.

**Fix Required**:
- Create E2E test that runs through Orchestrator
- Verify Flight Recorder records `feedback_source='implicit'`
- Verify confidence updates correctly

#### Next Steps

1. Fix Gap 1 (GetHeuristic RPC) - required for dynamic heuristic lookup
2. Fix Gap 2 (feedback_source propagation) - required for correct analytics
3. Create E2E test (Gap 3) - validation that everything works together

---

### Q: Similarity Threshold Strategy (§31)

**Status**: Open — needs empirical data
**Priority**: Medium (affects matching quality)
**Created**: 2026-01-31
**Origin**: Relocated from `docs/research/OPEN_QUESTIONS.md` (design decision, not research question)

Heuristics match incoming events via embedding cosine similarity (pgvector). The current threshold is 0.7 globally.

**The question**: Should the threshold be:
- Global (one number for everything)?
- Per-heuristic (learned from feedback — heuristics that produce false positives tighten their threshold)?
- Per-domain (gaming may need tighter matching than home automation)?
- Adaptive (starts loose, tightens as confidence grows)?

At 0.7, "user wants ice cream" matches "user wants frozen dessert" (0.78) but not "email about meeting" (0.69). Is that the right boundary?

**Relevant**: ADR-0010 Section 3.2, `heuristics.similarity_threshold`

**When to revisit**: When running load tests or real workloads with meaningful heuristics. See also §23.3 (Tuning Mode).

---

### Q: Conflicting Heuristic Resolution (§32)

**Status**: Open — design decision needed
**Priority**: Medium
**Created**: 2026-01-31
**Origin**: Relocated from `docs/research/OPEN_QUESTIONS.md`

When multiple heuristics match an event, the highest `similarity * confidence` score wins. This is a simple argmax.

**The question**: Is argmax the right strategy? Alternatives:
- Weighted voting across matching heuristics
- Escalate to System 2 when top-2 scores are close (deliberation trigger)
- Domain-specific resolution strategies
- Hierarchical heuristics (some override others)

**Relevant**: ADR-0010 Section 3.1 (escalation triggers)

---

## Resolved

### R: Semantic Heuristic Matching (§28)

**Status**: Resolved (2026-01-25)
**Priority**: Critical - Fixed

#### Problem Statement

The current heuristic matching system uses word overlap to find relevant heuristics for incoming events. This produces false positives when sentences share structural words but have completely different meanings.

**Example failure case**:
- Heuristic condition: "Mike Mulcahy sent an email about killing his neighbor"
- Event text: "Mike Mulcahy sent an email about meeting at 1pm"
- Word overlap: {Mike, Mulcahy, sent, email, about} = 5 words
- **Incorrectly matches!** despite completely different semantic meaning

#### Solution: Embedding-Based Semantic Matching

Replace word overlap with vector similarity using embeddings. "killing neighbor" and "meeting at 1pm" will have very different vectors despite sharing structural words.

**Implementation**: See [§22 Heuristic Data Structure](#r-heuristic-data-structure-cbr--fuzzy-matching-22) for the schema and matching algorithm using pgvector.

**Status**: Migration 008 deployed, embeddings backfilled, semantic matching verified working.

---

### R: Learning System Design (§5)

**Decision**: See ADR-0010
**Date**: 2026-01-XX
**ADR**: [ADR-0010](../../adr/ADR-0010-Learning-Pipeline.md)

Resolved questions:
1. **Trigger model**: Event-driven with background consolidation
2. **Online vs batch**: Online for heuristics, batch for deeper patterns
3. **Feedback loop**: Explicit (user) + implicit (outcome observation)
4. **Conflicting evidence**: Bayesian confidence updates
5. **Computational budget**: Background process with priority queuing
6. **Cold start**: Built-in heuristics + pack-provided heuristics

---

### R: Heuristic Condition Matching (§17)

**Status**: Superseded by §22
**Date**: 2026-01-23

Original design used exact key-value matching. Superseded by embedding-based fuzzy matching in §22 because:
- Exact matching is too brittle for natural language conditions
- Without fuzzy logic, GLADyS is just an expert system
- Semantic similarity via embeddings is brain-like and well-studied

---

### R: Heuristic Storage Model (§21)

**Decision**: Transaction log pattern
**Date**: 2026-01-23

Use a **transaction log pattern** for heuristic modifications:
- `heuristics` table: Current state only (fast to query)
- `heuristic_history` table: Append-only modification log (audit trail)

**Schema**:
```sql
CREATE TABLE heuristics (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  condition_json JSONB NOT NULL,
  effects_json JSONB NOT NULL,
  confidence FLOAT DEFAULT 0.5,
  origin TEXT NOT NULL,  -- 'built_in', 'pack', 'learned', 'user'
  origin_id TEXT,
  learning_rate FLOAT DEFAULT 0.1,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE heuristic_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  heuristic_id UUID REFERENCES heuristics(id),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  modification_type TEXT NOT NULL,  -- 'create', 'confidence_update', etc.
  field_changed TEXT,
  old_value JSONB,
  new_value JSONB,
  reason TEXT,
  trigger_event_id UUID,
  user_id UUID
);
```

**Rationale**: Fast lookup via current state table, full audit trail via history table, supports revert and debugging.

---

### R: Heuristic Data Structure - CBR + Fuzzy Matching (§22)

**Decision**: Case-Based Reasoning with embedding similarity
**Date**: 2026-01-23

#### Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Approach** | Case-Based Reasoning (CBR) | More brain-like than behavior trees |
| **Structure** | Flat list with competition | Highest (similarity × confidence) wins |
| **Matching** | Embedding similarity via pgvector | Without fuzzy logic, we're just an expert system |
| **Learning** | TD learning updates confidence | Heuristics improve based on feedback |
| **Formation** | LLM-assisted pattern extraction | Reasoning → Heuristic migration |

#### Schema

```sql
CREATE TABLE heuristics (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  condition_text TEXT,                    -- Human-readable
  condition_embedding VECTOR(384),        -- Semantic vector for fuzzy match
  similarity_threshold FLOAT DEFAULT 0.7, -- Min cosine similarity
  effects_json JSONB NOT NULL,
  confidence FLOAT DEFAULT 0.5,
  origin TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_heuristics_embedding ON heuristics
  USING ivfflat (condition_embedding vector_cosine_ops);
```

#### Matching Algorithm

```
1. Generate embedding for incoming event context
2. Query pgvector: SELECT *, 1 - (condition_embedding <=> input) as similarity
   WHERE similarity > threshold
3. Score each match: score = similarity × confidence
4. Winner = argmax(score)
5. Execute winner's effects_json
```

#### Heuristic Formation Flow

```
1. Event arrives → no heuristic match → send to Executive (LLM)
2. Executive reasons → produces response
3. User provides positive feedback
4. Ask LLM to extract generalizable pattern
5. Generate embedding for condition text
6. Store as new heuristic with confidence=0.3 (low, must earn trust)
7. Next similar event → heuristic matches → LLM skipped
```

---

## Reference: Validation Use Cases

These concrete scenarios help validate design decisions:

### UC1: Gaming Companion (Fire Detection)
```
[Game Sensor] → [Threat Analyzer] → Salience → Executive → Speech/Action
```
Tests: Heuristic fire, TD learning from "that warning was helpful"

### UC2: Learning from Experience
```
Novel event → LLM reasons → User thumbs up → Pattern extracted → New heuristic
Next similar event → Heuristic fires → LLM skipped
```
Tests: Heuristic formation, semantic matching, confidence updates
