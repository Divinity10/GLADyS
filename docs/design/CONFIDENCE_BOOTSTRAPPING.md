# Confidence Bootstrapping Design

**Status**: Draft
**Last Updated**: 2026-02-08
**Authors**: Scott, Claude
**Resolves**: `docs/design/questions/confidence-bootstrapping.md`, EXECUTIVE_DESIGN.md Open Question #1

**Related**:

- [ADR-0010](../adr/ADR-0010-Learning-and-Inference.md) — Learning pipeline, Bayesian inference
- [ADR-0014](../adr/ADR-0014-Executive-Decision-Loop-and-Proactive-Behavior.md) — Executive decision loop
- [EXECUTIVE_DESIGN.md](EXECUTIVE_DESIGN.md) — Executive component architecture
- [SALIENCE_MODEL.md](SALIENCE_MODEL.md) — Salience dimensions, habituation

---

## Problem

Learned heuristics start at confidence 0.3. The firing threshold is 0.7. A heuristic can only gain confidence through feedback on its fires. But it can't fire until it reaches the threshold. It stays at 0.3 forever.

Confirmed during Phase 1: every learned heuristic stayed at 0.3, and every event routed to the LLM regardless of how many similar events had been handled before.

---

## Solution Overview

Use the LLM as an independent evaluator. When below-threshold heuristics match an event, present them to the LLM as candidates in a neutral evaluation prompt. After the LLM generates its response, compare it to each candidate's suggested action. If the LLM's response is similar to a candidate's action, that candidate receives a confidence boost — the LLM "endorses" the heuristic.

This creates a path from 0.3 to 0.7 that doesn't require user feedback. The LLM evaluation is a weaker signal than user feedback, but it's automatic and continuous.

### Where It Fits

The bootstrapping evaluation is an extension of the existing System 2 (LLM) path in the executive decision loop. No new components — it adds a post-response comparison step to the existing flow.

```
Event arrives
    â”‚
    â–¼
Heuristic lookup (Memory service)
    â”‚
    â”œâ”€â”€ Confidence >= threshold → System 1 (heuristic fires directly)
    â”‚
    â””â”€â”€ Confidence < threshold → System 2 (LLM path)
            â”‚
            â–¼
        Build evaluation prompt (candidates + event, neutral framing)
            â”‚
            â–¼
        LLM generates response → delivered to user
            â”‚
            â–¼
        [ASYNC] Compare LLM response to each candidate     â† NEW
            â”‚
            â”œâ”€â”€ Similarity >= match threshold → boost candidate confidence
            â””â”€â”€ Similarity < match threshold → no change
```

### Two-Path Signal Model

Bootstrapping and firing are different contexts with different signal rules:

| Path | Condition | Who sees it | Signals that move confidence |
|------|-----------|-------------|------------------------------|
| **Bootstrapping** | Heuristic matched, below threshold | User sees LLM response (not the heuristic) | LLM endorsement, explicit user feedback |
| **Firing** | Heuristic matched, above threshold | User sees heuristic action | Explicit feedback, implicit feedback (timeout, undo, ignore) |

**Key distinction**: Implicit signals (silence = positive, undo = negative) only apply to the firing path, where the user saw and could react to the heuristic's action. On the bootstrapping path, the user never saw the heuristic — silence means nothing about the heuristic's quality.

---

## Evaluation Prompt Specification

### What Goes In

The prompt includes:

1. **Event context** — the triggering event text and source
2. **Candidate pairs** — each candidate's `condition_text` and `suggested_action`, presented as context:response pairs
3. **Generation instruction** — ask the LLM to produce its own response

### Neutral Framing Rules

1. **Randomize candidate order** — prevents positional bias
2. **No confidence scores** — the LLM must not know which candidates the system trusts
3. **No origin labels** — don't indicate "learned", "seeded", or "skill_pack"
4. **No fire counts or metadata** — no system-internal information
5. **Present as "possible responses"** — not as "suggestions from the system" or "patterns we've learned"
6. **Don't ask the LLM to judge candidates** — ask it to generate its own response. Comparison happens post-hoc via embeddings, not by asking the LLM to evaluate.

### Example Prompt

```
Event from [game_sensor]: Player health dropped to 3 hearts during combat with skeleton

Here are some possible responses to this situation:

1. Context: "When a player's health is critically low during active combat"
   Response: "Use a healing potion immediately before the next hit lands"

2. Context: "When facing a ranged enemy in an open area with low health"
   Response: "Take cover behind terrain to break line of sight before healing"

3. Context: "When inventory contains golden apples during a difficult fight"
   Response: "Consider using a golden apple for the regeneration effect"

Generate your own response to this event. You may draw on the above for context or disregard them entirely.
```

### What Is NOT Included

- Confidence values
- Heuristic IDs or internal identifiers
- Origin or creation date
- Fire count or success rate
- Any indication that these are "learned" or "automated"
- System metadata of any kind

### Documentation Requirement

The evaluation prompt format and neutral framing rules must be documented as a **behavioral contract** — any executive implementation (Python or C#) must follow these rules. The exact prompt wording may evolve, but the framing constraints are invariants.

---

## Post-Response Comparison

After the LLM generates its response:

1. Compute embedding similarity between the LLM response text and each candidate's `suggested_action`
2. For each candidate where similarity >= `endorsement_similarity_threshold`: apply confidence boost
3. For candidates below threshold: no change (not a penalty)
4. Log the comparison result for observability

### Mechanism

The existing `QueryMatchingHeuristics` uses pgvector to find heuristics by `condition_embedding` similarity. For bootstrapping, we need to match the LLM's response against heuristic *actions* (not conditions).

**Options**:

| Approach | Pros | Cons |
|----------|------|------|
| A: Add `action_embedding` column + pgvector query | Leverages existing DB infra, scales to all heuristics, single query | Schema migration, need to backfill existing heuristics |
| B: `GenerateEmbedding` RPC + local cosine similarity | No schema changes, works immediately | N+1 embedding calls per evaluation, doesn't scale beyond candidates |
| C: New `QuerySimilarActions(text, min_similarity, limit)` RPC | Clean interface, DB-backed | New RPC + action embeddings needed (combines A's migration with clean API) |

**Recommendation**: Option A for release (DB-backed action embeddings). Option B is acceptable for Phase if candidates are few (3-5).

**Phase optimization**: Rather than N+1 `GenerateEmbedding` RPC calls, add a batch comparison RPC to the memory service:

```
CompareTextToActions(response_text, [heuristic_id1, heuristic_id2, ...]) → [(heuristic_id, similarity), ...]
```

Single RPC, memory service does all embedding + comparison with its already-loaded model. Avoids round-trip overhead and keeps embedding logic centralized.

**Source filtering is mandatory.** Candidates must be from the same source domain as the event. A gaming heuristic must not be boosted by an email LLM response. The existing `QueryMatchingHeuristics` RPC already has `source_filter` (field 4) — the orchestrator's routing query must pass the event's `source` field.

Note: "match against existing heuristic" means ALL heuristics in the same source domain, not just the candidates shown in the prompt. If the LLM independently generates a response that matches an existing heuristic's action, that heuristic gets a boost even if it wasn't a candidate. Option A supports this naturally; Option B would need a broader search.

### Async Execution

The comparison is **not on the response path**. The user already has the LLM's response. The comparison is a background bookkeeping task that updates confidence for future events.

```
Timeline:
  t=0     LLM responds → user gets response immediately
  t=0+Î´   Async: compute similarity, update confidence
  t=later  Next event arrives → heuristic has updated confidence
```

---

## Confidence Update Model

### LLM Endorsement Signal

When the LLM's response is similar to a candidate's action (similarity >= threshold), the candidate receives a weighted confidence boost.

The boost is a **weighted positive observation** in the confidence model. It counts as a fraction of a success, not a full success:

```
effective_signal = endorsement_boost_weight Ã— similarity
```

Where `endorsement_boost_weight` is configurable (default 0.5) and `similarity` is the embedding cosine similarity (0.0—1.0).

### Signal Weight Table

**Status: Needs calibration.** The current Bayesian model (`storage.py`) ignores the `magnitude` parameter — every feedback is +1 to `success_count` (integer). Weighted signals require updating the model to use fractional observations (float alpha/beta). This is a prerequisite for bootstrapping.

The weights below express relative signal strength. Actual magnitudes must be calibrated against the Bayesian update formula once it supports weighted observations.

| Signal | Relative strength | Path | Notes |
|--------|-------------------|------|-------|
| Explicit positive (user ðŸ‘) | Strong | Both | Direct validation — but measures satisfaction, not correctness (see §Three Measurement Dimensions) |
| Explicit negative (user ðŸ‘Ž) | Strong negative | Both | Direct rejection |
| LLM endorsement (similar response) | Moderate | Bootstrapping | LLM agrees independently |
| Dev positive (outcome rated successful) | Strong | Both | Measures correctness — strongest quality signal |
| Dev negative (outcome rated unsuccessful) | Strong negative | Both | Measures correctness |
| Implicit positive (silence after timeout) | Weak | Firing only | User didn't complain — ambiguous |
| Implicit negative (undo detected) | Moderate negative | Firing only | User reversed the action |
| Ignored 3x (fired, user ignored) | Weak negative | Firing only | Pattern of disengagement |

### Bayesian Model: Weighted Signals via Fractional Pseudo-Counts

**Decision (2026-02-08)**: Confidence uses real-valued alpha/beta pseudo-counts. Magnitude scales observation weight — an LLM endorsement at magnitude 0.41 adds 0.41 to alpha, not 1.0. This is standard practice (Thompson sampling, Bayesian A/B testing, multi-armed bandits).

The `UpdateHeuristicConfidenceRequest` proto has the fields needed:

- `magnitude` (field 6): scales the observation weight (0.0—1.0)
- `feedback_source` (field 5): identifies the signal type (e.g., `"llm_endorsement"`, `"explicit_positive"`, `"dev_outcome"`)
- `positive` (field 2): direction of the update

**Update formula**:

- Positive feedback: `alpha += magnitude`
- Negative feedback: `beta += magnitude`
- Confidence = `alpha / (alpha + beta)`
- Prior: alpha = 1.0, beta = 1.0 (uniform — no opinion)

**Magnitude affects confidence only.** Success rate uses a separate integer mechanism — `success_count` incremented only on outcome-confirmed success (see §Success Rate).

**Implementation required**: `storage.py` currently ignores `magnitude`. The formula `(1 + success_count) / (2 + fire_count)` uses integer counts. Must be updated to use float alpha/beta columns. This is a prerequisite for bootstrapping — without it, all signals are treated as full-weight observations.

The executive sends:

```
UpdateHeuristicConfidence(
    heuristic_id = candidate.id,
    positive = true,
    magnitude = endorsement_boost_weight Ã— similarity,
    feedback_source = "llm_endorsement"
)
```

### Cache Invalidation

The Rust salience gateway maintains a heuristic cache for fast-path evaluation. When bootstrapping updates a heuristic's confidence, the cache must be invalidated so the next event sees the updated confidence.

The `SalienceGateway.NotifyHeuristicChange` RPC already exists for this purpose. After every confidence update, the executive (or memory service) must call:

```
NotifyHeuristicChange(heuristic_id, change_type="updated")
```

**Failure mode**: If cache invalidation fails, the heuristic fires with stale confidence. This is eventually consistent — the cache entry will expire or be replaced. Not a correctness issue, but delays the bootstrapping effect.

### Double-Signal Scenario

A single event can produce both an LLM endorsement (async, fast) and later user feedback (explicit, slower). Both signals apply. This is correct — two independent sources agreeing is stronger evidence than either alone.

---

## Concurrency Model

The executive must support multiple concurrent LLM evaluations. This is needed because:

- Multiple events may arrive in quick succession
- Each event may need LLM evaluation with its own candidates
- Serializing evaluations would create unacceptable latency at scale

### Specification (Language-Neutral)

- The executive maintains a pool of up to **N** concurrent LLM evaluation slots
- N is a configuration parameter (`max_concurrent_llm_evaluations`, default 3)
- When all slots are occupied, new evaluations wait for a slot to free
- Each evaluation is independent: its own prompt, its own candidates, its own comparison
- The post-response comparison (embedding similarity) runs in its own slot, not counted against LLM slots

### Resource Considerations

- Each LLM call consumes Ollama inference time (the real bottleneck)
- N should be tuned to the LLM backend's capacity (local GPU memory, API rate limits)
- Too high: LLM calls compete for GPU, all slow down
- Too low: events queue up, responsiveness suffers
- Default of 3 is a reasonable starting point for a single local GPU

### Implementation Notes

**Python (Phase)**: `asyncio.Semaphore(N)` — straightforward, already async.

**C# (future)**: `SemaphoreSlim(N)` with `async/await` — direct equivalent. Or, for true multithreading with shared memory coordination, a thread pool with bounded concurrency.

---

## Candidate Delivery

### Current State

`ProcessEventRequest` passes at most one `HeuristicSuggestion`. For bootstrapping, the LLM should see all below-threshold matches, not just the best one.

### Change Required

Extend the proto to pass multiple candidates:

```
ProcessEventRequest {
    Event event = 1;
    bool immediate = 2;
    HeuristicSuggestion suggestion = 3;             // Best match (existing)
    repeated HeuristicSuggestion candidates = 4;     // All below-threshold matches (new)
    RequestMetadata metadata = 15;
}
```

The orchestrator already queries for matching heuristics during routing. Passing all below-threshold matches avoids a redundant query from the executive. The candidates are kept in memory for post-comparison — no second DB query needed. The only DB call after comparison is `UpdateHeuristicConfidence` for candidates that match.

**Source filtering**: The orchestrator must pass `source_filter` when querying for matching heuristics. Only heuristics from the same source domain as the event are candidates. This prevents cross-domain false matches.

**Max candidates**: Configurable (`max_evaluation_candidates`, default 5). More candidates = richer prompt but higher token cost and potential attention dilution.

---

## Configuration Surface

All settings with defaults. Grouped by concern.

### Bootstrapping Evaluation

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrent_llm_evaluations` | int | 3 | Max LLM calls in flight simultaneously |
| `max_evaluation_candidates` | int | 5 | Max candidates included in evaluation prompt |
| `endorsement_similarity_threshold` | float | 0.75 | Minimum similarity for LLM response to count as endorsement |
| `endorsement_boost_weight` | float | 0.5 | Weight of LLM endorsement signal (0.0—1.0) |

### Confidence Thresholds (Existing)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `confidence_threshold` | float | 0.7 | Min confidence for heuristic to fire (System 1 path) |
| `heuristic_reinforce_threshold` | float | 0.75 | Min similarity to reinforce instead of create new |

### Where Configuration Lives

For Phase: environment variables (consistent with existing `EXECUTIVE_*` pattern).

For release: config file or pack manifest. The bootstrapping parameters are executive-level settings, not pack-level — they apply to all domains equally.

---

## Performance Instrumentation

These metrics support both Phase validation and the Python-vs-C# decision.

### Required Metrics

| Metric | What It Measures | Decision It Informs |
|--------|-----------------|---------------------|
| `executive.event_processing_latency_ms` | Total time from ProcessEvent to response | Is the executive a bottleneck? |
| `executive.llm_call_latency_ms` | Time spent waiting for LLM | Is concurrency helping? |
| `executive.embedding_comparison_latency_ms` | Time for post-response similarity check | Is this cheap enough to be async? |
| `executive.semaphore_wait_ms` | Time waiting for an LLM slot | Is N too low? |
| `executive.endorsement_rate` | Fraction of candidates endorsed per evaluation | Are thresholds well-calibrated? |
| `executive.confidence_trajectory` | Confidence over time per heuristic | Is bootstrapping working? |
| `executive.heuristic_path_ratio` | Fraction of events using System 1 vs System 2 | Are heuristics graduating to firing threshold? |

### C# Migration Decision Criteria

Specific signals that would indicate Python is insufficient:

1. `event_processing_latency_ms` P95 exceeds 100ms target (ADR-0014 §12) excluding LLM wait time
2. Semaphore contention consistently above 50% (GIL-related scheduling issues)
3. Memory growth under sustained load (Python object overhead)
4. CPU utilization dominated by Python overhead rather than useful work

If none of these trigger during Phase, Python remains viable. C# migration becomes a capability play (shared memory, true multithreading) rather than a performance necessity.

---

## Executive Contract (Language-Neutral)

Any executive implementation (Python or C#) must satisfy these requirements. This is the interface that enables drop-in replacement.

### Proto Interface

Implements `ExecutiveService` as defined in `executive.proto`:

- `ProcessEvent` — accepts events with candidates, returns responses
- `ProvideFeedback` — accepts user feedback, updates confidence
- `GetHealth` / `GetHealthDetails` — standard health RPCs

### Behavioral Requirements

1. Heuristics above `confidence_threshold` fire directly (System 1)
2. Below-threshold events go to LLM with candidates in neutral evaluation prompt
3. Post-response comparison runs asynchronously
4. Endorsements update confidence with configurable weight
5. Explicit user feedback updates confidence at full weight
6. No implicit signals on the bootstrapping path
7. Max N concurrent LLM evaluations
8. All metrics listed above are emitted

### Environment Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `EXECUTIVE_HEURISTIC_THRESHOLD` | 0.7 | Confidence threshold for System 1 path |
| `EXECUTIVE_LLM_PROVIDER` | ollama | LLM backend type |
| `EXECUTIVE_MAX_CONCURRENT_LLM` | 3 | Max concurrent LLM evaluations |
| `EXECUTIVE_ENDORSEMENT_THRESHOLD` | 0.75 | Similarity threshold for endorsement |
| `EXECUTIVE_ENDORSEMENT_WEIGHT` | 0.5 | Confidence boost weight for LLM endorsement |
| `EXECUTIVE_MAX_CANDIDATES` | 5 | Max candidates in evaluation prompt |
| `EXECUTIVE_GOALS` | (empty) | Active user goals (semicolon-separated) |
| `EXECUTIVE_DECISION_STRATEGY` | heuristic_first | Decision strategy type |

---

## Integration Points

### Proto Changes

1. **`executive.proto`**: Add `repeated HeuristicSuggestion candidates` to `ProcessEventRequest`
2. **`memory.proto`**: No changes needed for confidence updates (`magnitude` and `feedback_source` already exist). Action embedding support (Option A above) would need schema migration but no proto changes.

### Data Operations Required

Bootstrapping needs these operations. How they're accessed (gRPC to memory service, direct DB, or some other mechanism) is an open architectural question — not decided here.

| Operation | Input | Output | Existing RPC |
|-----------|-------|--------|--------------|
| Generate embedding | text | embedding bytes | `GenerateEmbedding` (memory.proto) |
| Update confidence (weighted) | heuristic_id, positive, magnitude, feedback_source | old/new confidence | `UpdateHeuristicConfidence` (memory.proto) — magnitude field already exists |
| Query matching heuristics | event text, min_confidence, limit | list of (heuristic, similarity) | `QueryMatchingHeuristics` (memory.proto) — matches by condition |
| Invalidate cache entry | heuristic_id, change_type | success | `NotifyHeuristicChange` (memory.proto, SalienceGateway service) |

The embedding model lives in the memory service. All similarity computation requires the memory service regardless of how other DB access is structured.

### Orchestrator

- Router passes all below-threshold matching heuristics as `candidates` in `ProcessEventRequest`
- Currently only passes the best match as `suggestion` — extend to include additional matches

### Learning Module Location

Where the learning module lives (orchestrator, executive, or split) is an open decision that will be evaluated across phases. The bootstrapping mechanism is designed to work regardless:

- The interface contract (signal type, weight, target heuristic) is the same either way
- Only the transport changes (internal method calls vs gRPC vs direct DB)

---

## Three Measurement Dimensions

Confidence bootstrapping addresses one dimension. The system actually tracks three distinct metrics that must not be conflated:

| Dimension | What it measures | Signal sources | Current status |
|-----------|-----------------|---------------|----------------|
| **Context match** (similarity) | Does this heuristic apply to this situation? | Embedding cosine similarity | Implemented — pgvector query |
| **Confidence** (trust) | Should we fire this heuristic? | LLM endorsement, user feedback | Partially implemented — Bayesian model exists, float alpha/beta decided, `storage.py` update pending |
| **Success rate** (correctness) | Does this heuristic's action produce good outcomes? | Dev ratings, outcome observation, follow-up events | Fields exist (`fire_count`, `success_count`, `predicted_success`), not wired up |

**Key distinction**: Confidence measures agreement/trust (LLM and users endorse it). Success rate measures correctness (the action produces successful outcomes). A heuristic can have high confidence (everyone agrees) but low success rate (it doesn't actually work). The system values correctness over user satisfaction.

### Success Rate

Success rate = `success_count / fire_count`. Both fields exist in the `heuristics` table and proto. Currently `success_count` is incremented on any positive feedback — it should only be incremented when the action's outcome is evaluated as successful.

**What "success" means**: Determined by the domain skill's outcome evaluator (ADR-0010 §3.11, ADR-0003 §6.4). The evaluator defines outcome signals (e.g., "player_survived" = positive, "player_died" = negative) and a correlation window for matching decisions to outcomes. The domain skill is the authority on correctness.

**Success depends on the user's goal.** Killing teammates is a success if that's the player's goal. The executive's `EXECUTIVE_GOALS` config provides goal context to the LLM prompt and outcome evaluation. Goal identification is a separate design question (see `docs/design/questions/goal-identification.md`).

### Existing Fields to Wire Up (Phase 2)

| Field | Location | Current state | Action |
|-------|----------|--------------|--------|
| `fire_count` | `heuristics` table | Incremented on heuristic fire | Already wired — no change |
| `success_count` | `heuristics` table | Incremented on positive feedback | Needs separation: increment only on outcome-confirmed success |
| `predicted_success` | `episodic_events` table, `ProcessEventResponse` | Stored but never consumed | Wire into learning: compare predicted vs actual outcome |
| `decision_path` | `episodic_events` table, `ProcessEventResponse` | Stored | Use for System 1 vs System 2 path ratio metric |

### Dev Ratings (Dashboard Tooling)

Users cannot decompose their feedback — a thumbs-up/down is a combined reaction to context match + response quality. Developers can rate these separately:

1. **Context rating**: "Does this heuristic's condition correctly describe this situation?" — measures context match quality
2. **Outcome rating**: "Would this action produce a successful outcome?" — measures response correctness

The dashboard (#62) must support dev rating of both dimensions. Dev outcome ratings feed directly into `success_count` and are the primary quality signal for pre-built heuristic development. User feedback remains valuable as a satisfaction signal but should not be confused with correctness.

**Phase scope**: Dashboard dev rating UI. User-facing feedback stays as-is (binary like/dislike). Automated outcome observation (follow-up event correlation) is deferred — see `docs/design/questions/outcome-correlation.md`.

---

## Open Questions (To Resolve During Phase)

1. **Rejection penalty**: Should LLM generating a response dissimilar to ALL candidates penalize those candidates? Current design says no (no change). If Phase shows heuristics lingering at low confidence without penalty, reconsider.

2. **Evaluation frequency**: Should every below-threshold match trigger an LLM evaluation? Or should there be rate limiting per-heuristic (e.g., evaluate at most once per hour)? Start without rate limiting, add if LLM costs are excessive.

3. **Convergence detection**: When a heuristic reaches the firing threshold via bootstrapping alone (no user feedback), should it be flagged for human review before graduating to System 1? Conservative approach: yes. Practical approach: no, the threshold already gates quality.

---

## Appendix: Worked Example

**Setup**: Heuristic H1 exists with condition "When player health drops below 3 hearts during combat", action "Use a healing potion immediately", confidence 0.35.

**Event**: "Player health dropped to 2 hearts while fighting a skeleton"

**Step 1**: Orchestrator queries memory, finds H1 matches with similarity 0.85 but confidence 0.35 < threshold 0.7. H1 passed as candidate in `ProcessEventRequest`.

**Step 2**: Executive builds evaluation prompt with H1's context:response pair (and any other matching candidates), randomized, neutral framing. Sends to LLM.

**Step 3**: LLM generates: "Your health is critical at 2 hearts! Drink a healing potion now before the skeleton can hit you again."

**Step 4**: Response delivered to user immediately.

**Step 5 (async)**: Compute embedding similarity between LLM response and H1's action "Use a healing potion immediately". Similarity = 0.82 (above 0.75 threshold).

**Step 6**: H1 endorsed. Magnitude = `endorsement_boost_weight Ã— similarity` = `0.5 Ã— 0.82 = 0.41`. Bayesian update: `alpha += 0.41` → alpha = 1.41, beta = 1.0. New confidence = `1.41 / (1.41 + 1.0) = 0.585`. H1 is climbing but not yet above the 0.7 threshold.

**Step 7**: Same scenario occurs again. LLM again generates a similar response (similarity 0.79). Magnitude = `0.5 Ã— 0.79 = 0.395`. Update: alpha = 1.805, beta = 1.0. Confidence = `1.805 / 2.805 = 0.643`. Getting closer.

**Step 8**: User gives ðŸ‘ on the LLM response. Full-weight update: `alpha += 1.0` → alpha = 2.805, beta = 1.0. Confidence = `2.805 / 3.805 = 0.737`. H1 now exceeds the 0.7 threshold.

**Step 9**: Next time a similar event arrives, H1 fires directly via System 1. No LLM call needed. H1 has graduated from bootstrapping through a combination of LLM endorsements and one user confirmation.
