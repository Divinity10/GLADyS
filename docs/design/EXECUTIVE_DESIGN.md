# Executive Subsystem Design

**Status**: Draft (in progress)
**Last Updated**: 2026-01-28
**Authors**: Scott, Claude

## Overview

This document defines the generalized executive subsystem - the decision-making component that processes events, generates responses, and learns from outcomes. The design separates **core brain functionality** (domain-agnostic) from **pack-provided knowledge** (domain-specific).

**Related Documents**:
- [ADR-0010](../adr/ADR-0010-Learning-and-Inference.md) - Learning pipeline, Bayesian inference
- [ADR-0014](../adr/ADR-0014-Executive-Decision-Loop-and-Proactive-Behavior.md) - Executive decision loop
- [DESIGN.md](DESIGN.md) - Overall system design

---

## Definition of Done

Design is complete when we can trace every scenario end-to-end on paper without hitting "TBD" in the critical path. Implementation can begin without waiting for design decisions.

---

## Design Scenarios

| # | Scenario | Tests |
|---|----------|-------|
| 1 | Event → high-conf heuristic fires → response delivered | System 1 path |
| 2 | Event → low-conf heuristic → LLM with suggestion → response | System 2 with hint |
| 3 | Event → no heuristic match → LLM from scratch → response | System 2 cold |
| 4 | User gives positive feedback → confidence increases | Explicit feedback |
| 5 | User gives negative feedback → confidence decreases | Explicit feedback |
| 6 | Outcome event observed → correlates to fire → confidence updates | Implicit feedback |
| 7 | LLM generates good response → new heuristic candidate formed | Heuristic formation |

### Scenario Trace Results

| # | Scenario | Status | Implementation Notes |
|---|----------|--------|---------------------|
| 1 | High-conf heuristic fires | ✅ Works | Router uses cached action from `effects_json` |
| 2 | Low-conf → LLM with suggestion | ✅ **Implemented** | HeuristicSuggestion passed through pipeline (2026-01-28) |
| 3 | No heuristic → LLM | ✅ Works | Event queued, Executive calls LLM |
| 4 | Positive feedback | ✅ Works | `ProvideFeedback` RPC implemented |
| 5 | Negative feedback | ✅ Works | `ProvideFeedback` RPC implemented |
| 6 | Outcome → confidence | ✅ Works | `OutcomeWatcher` correlates events |
| 7 | New heuristic formation | ✅ Works | LLM pattern extraction on positive feedback |

**Note**: All scenarios now have working implementations. Scenario 2 was completed 2026-01-28.

---

## Identified Gaps

### Gap 1: HeuristicSuggestion Not Passed to Executive ✅ FIXED (2026-01-28)

**Problem** (resolved): When a low-confidence heuristic matches, the router queues the event but discards the heuristic information.

**Solution implemented**:
- Added `HeuristicSuggestion` message to `executive.proto`
- Router stores heuristic data when fetching and adds to result for low-conf matches
- EventQueue passes suggestion context through to Executive
- Executive includes suggestion in LLM prompt

**Current Proto** (`executive.proto`):
```protobuf
message HeuristicSuggestion {
    string heuristic_id = 1;
    string suggested_action = 2;
    float confidence = 3;
    string condition_text = 4;
}

message ProcessEventRequest {
    Event event = 1;
    bool immediate = 2;
    HeuristicSuggestion suggestion = 3;  // Low-conf heuristic hint
    RequestMetadata metadata = 15;
}
```

**Result**: LLM now sees "a pattern suggests X with 65% confidence" for Scenario 2.

### Gap 2: Pack Registration Mechanism

**Problem**: `OutcomeWatcher` patterns are loaded from `config.outcome_patterns_json` at startup. There's no mechanism for packs to dynamically register their outcome patterns or domain context.

**Current State**: Static JSON config string parsed at server initialization.

**Fix**:
- PoC: Continue using static config (sufficient for testing)
- Release: Filesystem manifest scan (packs declare patterns in `manifest.yaml`)

### Gap 3: Domain Context for LLM

**Problem**: Executive has hardcoded `EXECUTIVE_SYSTEM_PROMPT`. No mechanism for packs to provide domain-specific context.

**Fix**: Include `domain_context` in pack manifest; Executive concatenates active pack contexts into system prompt.

---

## Design Decisions

### Decision 1: Pack Registration Approach

| Option | Description | Verdict |
|--------|-------------|---------|
| A: Startup config | Load from JSON config at startup | **PoC** |
| B: gRPC RegisterPack | Dynamic registration via RPC | Rejected (over-engineering) |
| C: Filesystem manifest | Scan pack directories for `manifest.yaml` | **Release** |

**Rationale**: Option A is already implemented and sufficient for PoC. Option C aligns with existing plugin manifest pattern (ADR-0003). Option B adds unnecessary complexity.

### Decision 2: HeuristicSuggestion Scope

| Option | Includes | Verdict |
|--------|----------|---------|
| A: Minimal | `heuristic_id`, `confidence` | Rejected |
| B: Full context | `heuristic_id`, `suggested_action`, `confidence`, `condition_text` | **Selected** |

**Rationale**: The LLM needs full context to evaluate the suggestion. Minimal option would require an extra RPC to fetch heuristic details.

---

## Proposed Proto Changes

### Add to `executive.proto`:

```protobuf
message ProcessEventRequest {
    Event event = 1;
    bool immediate = 2;
    HeuristicSuggestion suggestion = 3;  // NEW: Low-conf heuristic hint
    RequestMetadata metadata = 15;
}

message HeuristicSuggestion {
    string heuristic_id = 1;
    string suggested_action = 2;   // From effects_json.message
    float confidence = 3;          // Current confidence level
    string condition_text = 4;     // What pattern matched
}
```

### Executive Prompt Integration

When `suggestion` is present, include in LLM system prompt:

```
A learned pattern matched this situation:
- Pattern: "{condition_text}"
- Suggested action: "{suggested_action}"
- Confidence: {confidence:.0%}

Consider this suggestion in your response. You may agree, disagree, or refine it.
```

---

## Component Architecture

### Core Executive (Generalized, Pack-Agnostic)

```
┌─────────────────────────────────────────────────────────────┐
│                      EXECUTIVE SERVICE                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Process    │    │   Provide    │    │    Pack      │  │
│  │    Event     │    │   Feedback   │    │   Registry   │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                    │                   │          │
│         ▼                    ▼                   ▼          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  RESPONSE GENERATOR                  │   │
│  │  ┌─────────────┐              ┌─────────────────┐   │   │
│  │  │  System 1   │              │    System 2     │   │   │
│  │  │ (Heuristic) │              │     (LLM)       │   │   │
│  │  └─────────────┘              └─────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│                           ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  LEARNING SUBSYSTEM                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │  Fire    │  │ Outcome  │  │   Confidence     │   │   │
│  │  │ Recorder │  │ Watcher  │  │    Updater       │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **ProcessEvent** | Route to System 1 or System 2, include suggestion if present |
| **ProvideFeedback** | Accept explicit feedback, update confidence, form new heuristics |
| **Pack Registry** | Load pack manifests, provide outcome patterns and domain context |
| **Response Generator** | System 1: use heuristic effect; System 2: call LLM |
| **Fire Recorder** | Log every heuristic fire with context |
| **Outcome Watcher** | Correlate outcome events to recent fires |
| **Confidence Updater** | Bayesian update: `(1 + successes) / (2 + fires)` |

---

## Data Structures

### Database Tables

#### `heuristics` - Learned patterns
```sql
CREATE TABLE heuristics (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    condition       JSONB NOT NULL,          -- When to fire (semantic match)
    action          JSONB NOT NULL,          -- What to do (effects_json)
    confidence      FLOAT DEFAULT 0.5,       -- Bayesian confidence [0,1]
    fire_count      INTEGER DEFAULT 0,       -- Total times fired
    success_count   INTEGER DEFAULT 0,       -- Successful outcomes
    last_fired      TIMESTAMPTZ,
    frozen          BOOLEAN DEFAULT FALSE,   -- Deprecated heuristics
    origin          TEXT,                    -- 'skill_pack', 'learned', 'seeded'
    origin_id       TEXT,                    -- Reference to source
    condition_embedding VECTOR(384),         -- For semantic matching
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `heuristic_fires` - Fire audit log (Flight Recorder)
```sql
CREATE TABLE heuristic_fires (
    id              UUID PRIMARY KEY,
    heuristic_id    UUID REFERENCES heuristics(id),
    event_id        TEXT NOT NULL,           -- Triggering event
    fired_at        TIMESTAMPTZ DEFAULT NOW(),
    outcome         TEXT DEFAULT 'unknown',  -- 'success', 'fail', 'unknown'
    feedback_source TEXT,                    -- 'explicit', 'implicit', NULL
    feedback_at     TIMESTAMPTZ,
    episodic_event_id UUID                   -- Link to stored event
);
```

#### `feedback_events` - Explicit feedback log
```sql
CREATE TABLE feedback_events (
    id              UUID PRIMARY KEY,
    timestamp       TIMESTAMPTZ DEFAULT now(),
    target_type     TEXT NOT NULL,           -- 'action', 'heuristic', etc.
    target_id       UUID,
    feedback_type   TEXT NOT NULL,           -- 'explicit_positive', 'explicit_negative'
    feedback_value  FLOAT,                   -- -1.0 to 1.0
    weight          FLOAT DEFAULT 1.0
);
```

### In-Memory State

#### `QueuedEvent` (Orchestrator)
```python
@dataclass
class QueuedEvent:
    event_id: str
    event: Any                    # The protobuf Event
    salience: float               # Priority score
    enqueue_time_ms: int
    matched_heuristic_id: str = ""  # If a heuristic matched
```

#### `ReasoningTrace` (Executive)
```python
@dataclass
class ReasoningTrace:
    event_id: str
    response_id: str              # Links feedback to this response
    context: str                  # Event context sent to LLM
    response: str                 # LLM response text
    timestamp: float
    matched_heuristic_id: str | None  # For linking feedback
    predicted_success: float = 0.0
    prediction_confidence: float = 0.0
```
- **Retention**: 300 seconds (5 minutes)
- **Purpose**: Enables ProvideFeedback to extract patterns and update confidence

#### `PendingOutcome` (OutcomeWatcher)
```python
@dataclass
class PendingOutcome:
    heuristic_id: str
    event_id: str                 # Event that triggered fire
    trigger_pattern: str          # What matched
    expected_pattern: str         # Outcome we're waiting for
    fire_time: datetime
    timeout_at: datetime
    predicted_success: float = 0.0
    is_success_outcome: bool = True
```
- **Purpose**: Correlates outcome events to heuristic fires for implicit feedback

---

## State Machines

### Heuristic Fire Outcome

```
                    ┌─────────────┐
                    │   UNKNOWN   │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     ┌──────────┐   ┌──────────┐   ┌──────────┐
     │ SUCCESS  │   │   FAIL   │   │ TIMEOUT  │
     └──────────┘   └──────────┘   └──────────┘
```

| Transition | Trigger | Action |
|------------|---------|--------|
| UNKNOWN → SUCCESS | Positive feedback or positive outcome event | Increment `success_count` |
| UNKNOWN → FAIL | Negative feedback or negative outcome event | Increment `fire_count` only |
| UNKNOWN → TIMEOUT | No feedback within window | No confidence update |

### Heuristic Lifecycle

```
     ┌─────────────┐
     │   ACTIVE    │  confidence >= 0.3
     └──────┬──────┘
            │ confidence < 0.3
            ▼
     ┌─────────────┐
     │ DEPRECATED  │  Still fires, flagged for review
     └──────┬──────┘
            │ manual freeze OR confidence < 0.1
            ▼
     ┌─────────────┐
     │   FROZEN    │  Never fires
     └─────────────┘
```

**Note**: Lifecycle transitions are currently manual (via `frozen` flag). Automatic deprecation based on confidence threshold is a release feature.

---

## Component Interactions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATOR                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────────┐ │
│  │   Router    │───▶│ EventQueue  │───▶│        ExecutiveClient          │ │
│  └──────┬──────┘    └─────────────┘    └────────────────┬────────────────┘ │
│         │                                                │                  │
│         │ query heuristics                               │ ProcessEvent RPC │
│         ▼                                                ▼                  │
│  ┌─────────────┐                              ┌─────────────────────────┐  │
│  │  Salience   │                              │      EXECUTIVE          │  │
│  │   Client    │                              │  ┌─────────────────┐    │  │
│  └──────┬──────┘                              │  │ ProcessEvent    │    │  │
│         │                                     │  │ ProvideFeedback │    │  │
│         │                                     │  └────────┬────────┘    │  │
└─────────┼─────────────────────────────────────┴───────────┼─────────────┴──┘
          │                                                  │
          │ QueryHeuristics                                  │ UpdateConfidence
          ▼                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MEMORY SERVICE                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │   heuristics    │  │ heuristic_fires │  │     feedback_events         │ │
│  │     table       │  │     table       │  │         table               │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Interactions

| From | To | RPC/Method | Purpose |
|------|----|------------|---------|
| Router | Salience | `QueryHeuristics` | Find matching heuristics for event |
| Router | EventQueue | `enqueue()` | Queue low-conf events for LLM |
| EventQueue | ExecutiveClient | `send_event_immediate()` | Send event to Executive |
| ExecutiveClient | Executive | `ProcessEvent` | Get LLM response |
| Executive | Memory | `UpdateHeuristicConfidence` | Update after feedback |
| Executive | Memory | `StoreHeuristic` | Create new heuristic |
| OutcomeWatcher | Memory | `UpdateHeuristicConfidence` | Implicit feedback |
| Router | Subscribers | `broadcast_response()` | Notify UI/sensors of response |

---

## Pack Interface

Packs provide domain-specific knowledge via manifest:

```yaml
# manifest.yaml (in pack directory)
name: game-advisor
version: 1.0.0

executive:
  domain_context: |
    You are advising a player in a survival game. The player's goal is to
    survive and thrive. Prioritize immediate threats over long-term goals.

  outcome_patterns:
    - trigger_pattern: "health"
      outcome_pattern: "player died"
      timeout_sec: 60
      is_success: false

    - trigger_pattern: "health"
      outcome_pattern: "health restored"
      timeout_sec: 120
      is_success: true

    - trigger_pattern: "enemy"
      outcome_pattern: "enemy defeated"
      timeout_sec: 30
      is_success: true
```

### Pack Loading (Release Design)

1. On startup, scan `packs/` directory for `manifest.yaml` files
2. Parse `executive` section from each manifest
3. Register outcome patterns with `OutcomeWatcher`
4. Concatenate domain contexts for LLM system prompt

---

## Data Flow

### Scenario 2: Low-Confidence Heuristic → LLM with Suggestion (Complete Trace)

```
1. Sensor publishes event
         │
         ▼
2. Router.route_event()
   - Query Salience for heuristic match
   - Heuristic found with confidence=0.65 (< 0.7 threshold)
         │
         ▼
3. EventQueue.enqueue(event, salience, matched_heuristic_id)
         │
         ▼
4. Queue worker dequeues event (highest salience first)
         │
         ▼
5. Build HeuristicSuggestion from matched heuristic  [NEW]
   - Fetch heuristic from Memory via GetHeuristic RPC
   - Extract: id, effects_json.message, confidence, condition_text
         │
         ▼
6. ExecutiveClient.send_event_immediate(event, suggestion)  [MODIFIED]
         │
         ▼
7. Executive.ProcessEvent()  [MODIFIED]
   - Include suggestion in LLM prompt:
     "A learned pattern suggests: {action} (65% confidence)"
   - Generate LLM response
   - Store ReasoningTrace (links response_id → heuristic_id)
         │
         ▼
8. Record heuristic fire in Memory
   - INSERT into heuristic_fires (heuristic_id, event_id, outcome='unknown')
   - Register with OutcomeWatcher for implicit feedback
         │
         ▼
9. Return ProcessEventResponse to queue worker
   - response_id, response_text, predicted_success
         │
         ▼
10. Router.broadcast_response()
    - Subscribers (UI, sensors) receive response
    - response_id enables ProvideFeedback correlation
         │
         ▼
11. [Later] User provides feedback OR OutcomeWatcher detects outcome
    - ProvideFeedback(response_id, positive) → updates confidence
    - OutcomeWatcher matches outcome event → updates confidence
```

**Data Created**:
- `heuristic_fires` row with `outcome='unknown'`
- `ReasoningTrace` in Executive memory (5 min TTL)
- `PendingOutcome` in OutcomeWatcher (if pattern matches)

---

## Confidence Update Logic

Per [ADR-0010 §3.12.2](../adr/ADR-0010-Learning-and-Inference.md):

**Confidence measures**: Probability that heuristic's response leads to a **good outcome**.

**Update sources** (in order of reliability):
1. **Explicit feedback**: User thumbs up/down
2. **Implicit outcome**: OutcomeWatcher detects outcome event
3. **Deferred validation**: Batch comparison of S1 vs LLM vs actual outcome

**Formula**: Bayesian Beta-Binomial
```
confidence = (1 + success_count) / (2 + fire_count)
```

**Key principle**: Outcome > User feedback > LLM agreement

---

## Open Questions

1. **LLM Agreement Value**: Is there any value in recording when LLM agrees with a heuristic suggestion? (Currently: no automatic confidence update)

2. **Implicit Requests**: Are all heuristics implicit requests? (Heuristic condition = "what should I do about X?")

3. **Cross-Domain Knowledge**: How do packs share context? (e.g., Calendar needs GPS location from Phone pack)

---

## Design Artifacts Checklist

- [x] Scenario traces (7 scenarios traced)
- [x] Interface definitions (HeuristicSuggestion proto)
- [x] Data structures (3 tables, 3 in-memory structures)
- [x] State machines (Fire outcome, Heuristic lifecycle)
- [x] Component diagram with interactions

**Design Status**: Complete - all scenarios trace without TBD in critical path.

---

## Implementation Checklist

- [x] Add `HeuristicSuggestion` to `executive.proto` ✅ (2026-01-28)
- [x] Update `ProcessEventRequest` with `suggestion` field ✅ (2026-01-28)
- [x] Run `proto_gen.py` ✅ (2026-01-28)
- [x] Update `EventQueue` to build suggestion from matched heuristic ✅ (2026-01-28)
- [x] Update `ExecutiveClient` to pass suggestion ✅ (2026-01-28)
- [x] Update Executive server to include suggestion in LLM prompt ✅ (2026-01-28)
- [ ] Add pack manifest schema for `executive` section (deferred to release)
- [ ] Implement pack manifest loading (deferred to release)

---

## Future Improvements

### Heuristic Selection Scoring (Post-PoC)

**Problem**: When multiple heuristics match an event, current scoring uses only `similarity × confidence`. This ignores useful signals that could improve selection quality.

**Current implementation** ([storage.py:355](../../../src/memory/python/gladys_memory/storage.py)):
```python
score = similarity * confidence
```

**Missing signals**:

| Signal | Why It Matters | Proposed Weight |
|--------|----------------|-----------------|
| **Recency** | Recently successful heuristics more trustworthy | +20% if succeeded in last hour |
| **Origin** | `skill_pack` (human-authored) > `learned` (LLM-generated) until proven | skill_pack: 1.2×, learned: 1.0×, seeded: 0.8× |
| **Habituation** | Avoid spamming same suggestion repeatedly | Decay if fired >3× in 5 minutes |

**Proposed formula**:
```python
score = similarity * confidence * recency_boost * origin_weight * habituation_decay
```

**Example problem**: Two heuristics match "player health is low":
1. `health_v1` — confidence=0.7, last fired 2 weeks ago, origin=learned
2. `health_v2` — confidence=0.65, last fired 10 min ago (success), origin=skill_pack

Current scoring picks #1 (higher base score). But #2 is likely better — it's from a skill pack and recently succeeded.

**Status**: Deferred. Current `similarity × confidence` is sufficient for PoC. Implement when we observe poor heuristic selection in practice.

**Prerequisite**: Need enough heuristics in production to see selection problems. This is an optimization, not a correctness issue.

---

## Related Files

| Purpose | File |
|---------|------|
| Event routing | `src/orchestrator/gladys_orchestrator/router.py` |
| Event queue | `src/orchestrator/gladys_orchestrator/event_queue.py` |
| Executive client | `src/orchestrator/gladys_orchestrator/clients/executive_client.py` |
| Executive server | `src/executive/gladys_executive/server.py` |
| Outcome watcher | `src/orchestrator/gladys_orchestrator/outcome_watcher.py` |
| Executive proto | `proto/executive.proto` |
| Heuristic storage | `src/memory/python/gladys_memory/storage.py` |
