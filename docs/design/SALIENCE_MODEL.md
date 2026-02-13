# Salience Model Interface Spec

**Status**: Approved
**Date**: 2026-02-11 (finalized), 2026-02-05 (initial)
**Authors**: Scott Mulcahy, Claude (Architect)
**Supersedes**: Partially supersedes SALIENCE_SCORER.md (which covers heuristic matching only)
**Informed by**: Phase 1 finding F-20
**Relates to**: ADR-0013 (Salience Subsystem), DECISION_STRATEGY.md, ROUTER_CONFIG.md

---

## 1. Problem Statement

The current salience implementation conflates three distinct concerns into a single 9-dimensional vector:

1. **Threat detection** (interrupt signal with asymmetric error costs)
2. **Attention priority** (queue ordering for Executive processing)
3. **Response shaping** (what kind of response is appropriate)

Additionally:

- Dimensions are not orthogonal (same heuristic match boosts multiple axes)
- Reduction to scalar uses naive `max()` — ignores cross-dimension semantics
- `habituation` operates inversely to all other dimensions (high = suppress)
- No interface for swapping salience models (all logic inline in `server.rs`)
- Weights are hardcoded, not user-configurable

### What This Spec Covers vs. SALIENCE_SCORER.md

| Concern | This Spec | SALIENCE_SCORER.md |
|---------|-----------|-------------------|
| Salience vector computation | Yes | No |
| Threat/habituation separation | Yes | No |
| Scalar reduction from vector | Yes | No |
| Heuristic matching algorithm | No | Yes |
| Rust trait for scoring | No | Yes |

These specs are complementary. SALIENCE_SCORER.md defines how to find matching heuristics.
This spec defines what to do with the match results (and other signals) to produce a salience assessment.

---

## 2. Design Decisions

### 2.1 Threat Is Separate from the Salience Vector

**Rationale**: Threat has fundamentally different semantics from other dimensions.

| Property | Threat | Other dimensions |
|----------|--------|-----------------|
| Error cost of false negative | Catastrophic | Missed opportunity |
| Error tolerance | Accept false positives | Minimize false positives |
| Priority model | Absolute (never outranked) | Relative (weighted competition) |
| Aggregation | max() across sources | Weighted sum for scalar |
| Learning loss | Separate, higher penalty | Shared loss function |

**Consequence**: Threat bypasses the salience queue entirely. The router checks threat FIRST,
then salience. A high-threat event interrupts regardless of current attention budget.

**Consequence for math**: Removing threat from the vector means PCA, cosine similarity,
averaging, and gradient updates on the vector operate on semantically consistent dimensions.

### 2.2 Habituation Is a Suppression Modifier, Not a Dimension

**Rationale**: Habituation operates inversely to all other dimensions.

- All dimensions: high value = more attention
- Habituation: high value = less attention

Additionally, `habituation != (1 - novelty)`:

- **Novelty**: "How different is this from what I know?" (semantic distance)
- **Habituation**: "How often has this exact pattern fired recently?" (temporal frequency)

An event can be novel (new type) but habituated (similar pattern keeps triggering).
An event can be non-novel (known type) but not habituated (haven't seen it recently).

**Consequence**: Habituation is applied as a multiplier on the salience scalar:

```
effective_salience = salience * (1.0 - habituation)
```

**Consequence**: Habituation does NOT suppress threat. A repeating smoke alarm should not
be ignored. Threat bypasses habituation, same as it bypasses the queue.

### 2.3 Salience Scalar Uses Configurable Weights

**Rationale**: Different users and domains value dimensions differently.

- A risk-averse user should have higher threat sensitivity (handled by threat threshold)
  and possibly higher opportunity weight
- A novelty-seeking user values surprise over predictability
- A gaming domain weights goal_relevance highest
- A home automation domain weights actionability highest

**Weight hierarchy**:

1. **System defaults** — per domain model (baseline)
2. **User overrides** — within bounded ranges (can't disable safety)
3. **Learned adjustments** — system observes which events get engagement, nudges weights

**Scalar computation**:

```
salience = sum(weight[d] * vector[d] for d in dimensions) / sum(weights.values())
```

Normalized so salience remains in 0.0-1.0 regardless of weight magnitudes.

### 2.4 Vector Dimensions Drive Response Shaping and Priority

After removing threat and habituation, the vector contains dimensions that answer:
*"What kind of attention does this deserve, and how should I respond?"*

| Dimension | Range | Purpose |
|-----------|-------|---------|
| novelty | 0-1 | Semantic distance from known events (expected vs unexpected) |
| goal_relevance | 0-1 | Alignment with active user goals (including personality-derived goals like entertainment) |
| opportunity | 0-1 | Positive potential, beneficial if acted upon |
| actionability | 0-1 | Feasibility of responding to this event |
| social | 0-1 | Interpersonal/entity significance |

**Design rationale for removed dimensions:**

- **emotional** (removed): Emotional valence is captured by existing dimensions:
  - Negative urgent consequences → `threat` (separate scalar)
  - Positive beneficial outcomes → `opportunity`
  - Example: "Angry customer email" = high threat (job/relationship risk), "Bank overdraft $5000" = high threat (financial risk), "Boss offers conference trip" = high opportunity
  - In GLADyS's context (email, calendar, thermostat, games, doorbell), emotional valence doesn't drive action selection beyond what threat/opportunity already capture

- **humor** (removed): Entertainment value is captured by `goal_relevance` when entertainment is an active goal:
  - User personality profiles can include implicit "entertainment" goals
  - Humor detection becomes an input to goal evaluation, not an output dimension
  - Funny events score high on goal_relevance (when entertainment is valued) and opportunity (entertainment has value)

- **impact** (deferred, YAGNI): Magnitude of effect on user's state. Deferred because:
  - Threat and opportunity scores should already reflect magnitude (small threat = 0.2, large threat = 0.9)
  - Vector is extensible (`map<string, float>`) — can add if data shows we need it
  - No concrete evidence yet that current dimensions fail to capture impact

**Orthogonality**: These 5 dimensions are orthogonal (can vary independently):

- Opportunity vs actionability: "2 tons of gold, heavily guarded" (high opportunity: 1.0, low actionability: 0.1)
- Goal_relevance vs opportunity: "Exit door while escaping" (high goal_relevance: 0.9, low opportunity: 0.2)
- Social vs actionability: "Friend asks for $10k loan you can't afford" (high social: 0.9, low actionability: 0.1)

The interface supports models outputting any subset of these dimensions, or additional custom dimensions as needs emerge.

---

## 3. Data Object

```python
@dataclass
class SalienceResult:
    """Complete salience assessment for an event."""

    # --- Scalars (each serves a distinct routing/filtering role) ---
    threat: float           # 0.0-1.0  Interrupt signal (bypasses queue + habituation)
    salience: float         # 0.0-1.0  Weighted scalar (queue priority)
    habituation: float      # 0.0-1.0  Suppression modifier (0=fresh, 1=fully habituated)

    # --- Vector (response-shaping dimensions, safe for vector math) ---
    vector: dict[str, float]  # Named dimensions, model-defined

    # --- Metadata ---
    model_id: str           # Which model produced this (for A/B testing)

    @property
    def effective_salience(self) -> float:
        """Salience after habituation suppression."""
        return self.salience * (1.0 - self.habituation)
```

### Proto Representation

```protobuf
message SalienceResult {
    float threat = 1;
    float salience = 2;
    float habituation = 3;
    map<string, float> vector = 4;
    string model_id = 5;
}
```

### Dashboard Display

The dashboard currently shows a flat "Salience Breakdown" grid. With this change:

- **Salience score** shown in the row summary (replaces current single value)
- **Threat** shown with color coding (red if above threshold)
- **Habituation** shown as a modifier (e.g., "Ã—0.7" or "30% habituated")
- **Vector breakdown** shown in the drilldown (same grid layout as current)

---

## 4. Model Interface

```python
class SalienceModel(Protocol):
    """Protocol for salience evaluation models.

    Implementations may range from simple rule-based scoring to custom ML models.
    All must produce a SalienceResult with at minimum: threat, salience, habituation.
    Vector dimensions are model-defined (models declare what they output).
    """

    async def evaluate(
        self,
        event_text: str,
        source: str,
        context: dict[str, Any],  # Active goals, recent events, user profile, event intent (F-20)
    ) -> SalienceResult:
        """Evaluate salience for an event."""
        ...

    @property
    def dimensions(self) -> list[str]:
        """What vector dimensions this model outputs."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Current model configuration (weights, thresholds, etc.)."""
        ...
```

### Weight Configuration

```python
@dataclass
class SalienceWeights:
    """Configurable weights for computing salience scalar from vector."""

    weights: dict[str, float]     # dimension → weight (e.g., {"novelty": 1.0, "actionability": 0.5})
    threat_threshold: float       # Above this → emergency path (default 0.8)
    salience_threshold: float     # Above this → queue for Executive (default 0.5)

    # Bounds for user overrides (safety constraints)
    min_threat_threshold: float = 0.3   # Can't make threat insensitive
    max_threat_threshold: float = 0.95  # Can't make it fire on everything
```

---

## 5. Router Integration

```python
async def route_event(self, event, salience: SalienceResult):
    # 1. Threat check (absolute priority, bypasses queue + habituation)
    if salience.threat >= self.config.threat_threshold:
        return await self.emergency_path(event, salience)

    # 2. Habituation suppression
    effective = salience.effective_salience

    # 3. Attention budget check
    if effective >= self.config.salience_threshold:
        return await self.queue_for_executive(event, salience, priority=effective)

    # 4. Below attention budget
    return await self.store_only(event, salience)
```

**Note**: Intent-based routing (F-20: skip pipeline for informational events) is a router concern, not a salience model concern. See `ROUTER_CONFIG.md` for intent routing. The salience model's role is to reflect intent in scoring — specifically, the `actionability` dimension should score low for informational events, since they don't warrant a response. Event intent is available to models via the `context` dict passed to `evaluate()`.

### Current Code Impact

| File | Current | Change |
|------|---------|--------|
| `server.rs` `evaluate_salience()` | Returns 9-dim SalienceVector | Returns SalienceResult (3 scalars + vector) |
| `router.py` `_get_max_salience()` | `max(8 dimensions)` | Uses `salience.effective_salience` |
| `router.py` emergency fast-path | `confidence >= 0.95 AND threat >= 0.9` | `salience.threat >= threat_threshold` |
| `router.py` `_default_salience()` | 9-dim dict with novelty=0.8 | SalienceResult with defaults |
| Proto `SalienceVector` | 9 named float fields | SalienceResult message (see above) |
| Dashboard `event_row.html` | Flat breakdown grid | Separate threat/habituation + vector grid |

---

## 6. Migration Path (Phase 1 → Phase 2)

### Phase 1: Data Object (minimal code change)

- Define SalienceResult in proto
- Adapter in Rust: current evaluate_salience() → SalienceResult
  - threat = current vector.threat
  - habituation = current vector.habituation
  - salience = max(remaining dimensions)  â† preserves current behavior
  - vector = remaining dimensions
- Router uses SalienceResult instead of raw dict

### Phase 2: Model Interface

- Extract SalienceModel protocol
- Current logic becomes `HeuristicBoostModel` (default implementation)
- Add configuration for weights

### Phase 3: Alternative Models

- Custom ML model (trained on user feedback data)
- A/B testing framework (run two models, compare outcomes)

---

## 7. Design Decisions Summary

### Resolved Questions

1. **emotional dimension** — RESOLVED: Removed. Captured by threat (negative consequences) + opportunity (positive benefits).

2. **humor dimension** — RESOLVED: Removed. Captured by goal_relevance when entertainment is an active/personality goal.

3. **actionability placement** — RESOLVED: In vector, not as modifier. Weighted sum naturally handles high-social + low-actionability cases (friend's request you can't fulfill still routes to Executive for decline).

4. **Scalar computation ownership** — RESOLVED: System computes scalar from weights. Enables user-configurable weights without model retraining.

5. **Vector dimension count** — RESOLVED: 5 standard dimensions (novelty, goal_relevance, opportunity, actionability, social). Extensible via map for future additions.

### Open Questions

1. **How do context profiles (ADR-0013 §5.3) interact with weights?** Are profiles just
   preset weight configurations, or do they also affect which dimensions are active?

2. **Should impact be added as a dimension?** (Magnitude of effect on user's state, orthogonal to valence.) Deferred per YAGNI — threat/opportunity should encode magnitude in their scores. Add if data shows current model under-represents magnitude.

3. **Should additional domain-specific dimensions emerge?** Vector is extensible. Models can add dimensions as needed (e.g., urgency, complexity, certainty).

---

## 8. References

- ADR-0013: Salience Subsystem (architectural specification)
- ADR-0010: Learning (heuristics and System 1/2)
- SALIENCE_SCORER.md: Rust trait for heuristic matching algorithm
- DECISION_STRATEGY.md: How Executive chooses heuristic vs LLM path
- ROUTER_CONFIG.md: Threshold and routing configuration
