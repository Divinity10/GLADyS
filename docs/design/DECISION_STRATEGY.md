# Decision Strategy Interface Spec

**Status**: Ready for implementation
**Date**: 2026-02-02 (updated 2026-02-06)
**Implements**: Extensibility Review item #2
**Depends on**: [LLM_PROVIDER.md](LLM_PROVIDER.md)
**Informed by**: Phase 1 findings F-04, F-06, F-07, F-24, F-25

## Purpose

Define an abstract interface for event decision logic so that Phase 2 can A/B test different strategies (heuristic-first, always-LLM, hybrid) without modifying the Executive's gRPC handler.

## Current State

`ExecutiveServicer.ProcessEvent` in `src/services/executive/gladys_executive/server.py` is a ~100-line method with inline decision logic:

1. Check if suggestion confidence >= threshold → heuristic path
2. Else if LLM available and immediate → LLM path
3. Else → no response

Hardcoded elements:

- Confidence threshold: `EXECUTIVE_HEURISTIC_THRESHOLD` env var (default 0.7)
- Prompts: `EXECUTIVE_SYSTEM_PROMPT`, `PREDICTION_PROMPT` — string constants
- Trace storage: `self.reasoning_traces` dict

## Protocol

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Any


class DecisionPath(Enum):
    """Which path the decision took."""
    HEURISTIC = "heuristic"
    LLM = "llm"
    FALLBACK = "fallback"
    REJECTED = "rejected"


@dataclass
class HeuristicCandidate:
    """A heuristic candidate for LLM prompt inclusion (F-04).

    Deliberately minimal — only condition and action text.
    No confidence scores, fire counts, or similarity scores (avoids anchoring bias).
    """
    heuristic_id: str
    condition_text: str
    suggested_action: str
    confidence: float  # Used for heuristic-path threshold check, NOT shown to LLM


@dataclass
class DecisionContext:
    """Input to a decision strategy."""
    event_id: str
    event_text: str
    event_source: str
    salience: dict[str, float]
    candidates: list[HeuristicCandidate]  # Replaces single 'suggestion'. Best match first, then additional candidates.
    immediate: bool
    goals: list[str] = field(default_factory=list)  # Active user goals (F-07). Injected into system prompt.
    personality_biases: dict[str, float] = field(default_factory=dict)  # F-24: threshold adjustments per-domain/user


@dataclass
class DecisionResult:
    """Output from a decision strategy."""
    path: DecisionPath
    response_text: str
    response_id: str
    matched_heuristic_id: str | None
    predicted_success: float
    prediction_confidence: float
    prompt_text: str
    metadata: dict[str, Any]  # Includes convergence info (F-04 Q3) when detected


class DecisionStrategy(Protocol):
    """Interface for event decision logic."""

    async def decide(
        self,
        context: DecisionContext,
        llm: LLMProvider | None,
    ) -> DecisionResult:
        """Decide how to respond to an event.

        Works for both real-time decisions (candidates populated) and
        sleep-cycle re-evaluation (candidates empty, F-25).
        """
        ...

    def get_trace(self, response_id: str) -> ReasoningTrace | None:
        """Get reasoning trace for feedback handling."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Return configuration for logging."""
        ...
```

## Default Implementation: HeuristicFirstStrategy

```python
@dataclass
class HeuristicFirstConfig:
    confidence_threshold: float = 0.7
    max_candidates: int = 3          # Max candidates in LLM prompt (F-04 Q5)
    llm_confidence_ceiling: float = 0.8  # Cap LLM self-reported confidence (F-06)
    system_prompt: str = EXECUTIVE_SYSTEM_PROMPT
    prediction_prompt_template: str = PREDICTION_PROMPT


class HeuristicFirstStrategy:
    """Use heuristic if confident, else LLM.

    Decision flow:
    1. If best candidate confidence >= threshold → heuristic fast-path
    2. If LLM available and immediate → LLM path (remaining candidates shown as neutral context)
    3. Otherwise → rejected
    """

    def __init__(self, config: HeuristicFirstConfig | None = None):
        self._config = config or HeuristicFirstConfig()
        self._trace_store: dict[str, ReasoningTrace] = {}

    async def decide(self, context: DecisionContext, llm: LLMProvider | None) -> DecisionResult:
        # Apply personality bias to threshold (F-24)
        threshold = self._config.confidence_threshold + context.personality_biases.get("confidence_threshold", 0.0)
        threshold = max(0.3, min(0.95, threshold))  # Clamp to safe range

        # Path 1: High-confidence heuristic (best candidate above threshold)
        best = context.candidates[0] if context.candidates else None
        if best and best.confidence >= threshold:
            return self._heuristic_path(context, best)

        # Path 2: LLM reasoning (with remaining candidates as neutral context)
        if llm and context.immediate:
            return await self._llm_path(context, llm)

        # Path 3: Rejected
        return DecisionResult(
            path=DecisionPath.REJECTED,
            response_text="",
            response_id="",
            matched_heuristic_id=None,
            predicted_success=0.0,
            prediction_confidence=0.0,
            prompt_text="",
            metadata={"reason": "llm_unavailable" if not llm else "not_immediate"},
        )

    def _heuristic_path(self, context: DecisionContext, candidate: HeuristicCandidate) -> DecisionResult:
        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=candidate.suggested_action,
            matched_heuristic_id=candidate.heuristic_id,
            predicted_success=candidate.confidence,
        )
        return DecisionResult(
            path=DecisionPath.HEURISTIC,
            response_text=candidate.suggested_action,
            response_id=response_id,
            matched_heuristic_id=candidate.heuristic_id,
            predicted_success=candidate.confidence,
            prediction_confidence=candidate.confidence,
            prompt_text="",
            metadata={"threshold": self._config.confidence_threshold},
        )

    async def _llm_path(self, context: DecisionContext, llm: LLMProvider) -> DecisionResult:
        prompt = self._build_prompt(context)

        # Compose system prompt with goals (F-07)
        system_prompt = self._config.system_prompt
        if context.goals:
            goals_text = "\n".join(f"- {g}" for g in context.goals)
            system_prompt += f"\n\nCurrent user goals:\n{goals_text}"

        llm_response = await llm.generate(LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
        ))

        if not llm_response:
            return DecisionResult(
                path=DecisionPath.FALLBACK,
                response_text="",
                response_id="",
                matched_heuristic_id=None,
                predicted_success=0.0,
                prediction_confidence=0.0,
                prompt_text=prompt,
                metadata={"reason": "llm_no_response"},
            )

        response_text = llm_response.text.strip()
        predicted_success, prediction_confidence = await self._get_prediction(
            llm, context, response_text
        )

        # Cap LLM self-reported confidence (F-06)
        predicted_success = min(predicted_success, self._config.llm_confidence_ceiling)
        prediction_confidence = min(prediction_confidence, self._config.llm_confidence_ceiling)

        # Determine matched heuristic (best candidate if present)
        matched_id = context.candidates[0].heuristic_id if context.candidates else None

        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=response_text,
            matched_heuristic_id=matched_id,
            predicted_success=predicted_success,
        )

        metadata: dict[str, Any] = {"model": llm.model_name}
        # Note: Convergence detection (comparing LLM response to candidate actions
        # via embedding similarity) is deferred to Phase 2. When implemented, add:
        # metadata["convergence"] = {"converged_heuristic_id": "...", "similarity": 0.82}

        return DecisionResult(
            path=DecisionPath.LLM,
            response_text=response_text,
            response_id=response_id,
            matched_heuristic_id=matched_id,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
            prompt_text=prompt,
            metadata=metadata,
        )

    def _build_prompt(self, context: DecisionContext) -> str:
        """Build LLM prompt with neutral candidate presentation (F-04).

        Candidates shown as "previous responses to similar situations" —
        condition + action only, no scores, randomized order.
        LLM given explicit permission to ignore them.
        """
        prompt = f"URGENT event: [{context.event_source}]: {context.event_text}\n\n"

        # Include candidates as neutral context (up to max_candidates)
        display_candidates = context.candidates[:self._config.max_candidates]
        if display_candidates:
            # Randomize order to avoid positional bias
            import random
            shuffled = list(display_candidates)
            random.shuffle(shuffled)

            prompt += "Previous responses to similar situations (for context — you may ignore these):\n"
            for i, c in enumerate(shuffled, 1):
                prompt += f"{i}. Situation: \"{c.condition_text}\" → Response: \"{c.suggested_action}\"\n"
            prompt += "\n"

        prompt += "How should I respond?"
        return prompt

    async def _get_prediction(self, llm: LLMProvider, context: DecisionContext, response_text: str) -> tuple[float, float]:
        # ... prediction logic (unchanged from current impl)
        # F-06: Prediction prompt should define "success" in terms of goals when available.
        # The raw values are capped by llm_confidence_ceiling in the caller.
        pass

    def _store_trace(self, **kwargs) -> str:
        response_id = str(uuid.uuid4())
        self._trace_store[response_id] = ReasoningTrace(response_id=response_id, timestamp=time.time(), **kwargs)
        return response_id

    def get_trace(self, response_id: str) -> ReasoningTrace | None:
        return self._trace_store.get(response_id)

    @property
    def config(self) -> dict[str, Any]:
        return {
            "strategy": "heuristic_first",
            "confidence_threshold": self._config.confidence_threshold,
            "max_candidates": self._config.max_candidates,
            "llm_confidence_ceiling": self._config.llm_confidence_ceiling,
        }
```

## ExecutiveServicer Changes

`ProcessEvent` becomes a thin wrapper:

```python
async def ProcessEvent(self, request, context) -> ProcessEventResponse:
    self._setup_trace(context)

    # Build candidates list from request
    # The orchestrator sends the best match as request.suggestion (current proto).
    # Future: proto gains repeated candidates field for multiple matches.
    candidates = []
    if request.HasField("suggestion") and request.suggestion.heuristic_id:
        candidates.append(HeuristicCandidate(
            heuristic_id=request.suggestion.heuristic_id,
            condition_text=request.suggestion.condition_text,
            suggested_action=request.suggestion.suggested_action,
            confidence=request.suggestion.confidence,
        ))

    decision_context = DecisionContext(
        event_id=request.event.id,
        event_text=request.event.raw_text,
        event_source=request.event.source,
        salience=self._extract_salience(request.event.salience),
        candidates=candidates,
        immediate=request.immediate,
        goals=self._get_active_goals(),  # From config/env for Phase 2
    )

    result = await self._strategy.decide(decision_context, self._llm)

    return executive_pb2.ProcessEventResponse(
        accepted=result.path != DecisionPath.REJECTED,
        response_id=result.response_id,
        response_text=result.response_text,
        predicted_success=result.predicted_success,
        prediction_confidence=result.prediction_confidence,
        prompt_text=result.prompt_text,
        decision_path=result.path.value,
        matched_heuristic_id=result.matched_heuristic_id or "",
    )
```

## Configuration

Environment variables:

```
EXECUTIVE_DECISION_STRATEGY=heuristic_first  # "heuristic_first" | "always_llm" (future)
EXECUTIVE_HEURISTIC_THRESHOLD=0.7
EXECUTIVE_GOALS=                             # Semicolon-separated goal strings (F-07, optional)
```

Factory:

```python
def create_decision_strategy(strategy_type: str, **kwargs) -> DecisionStrategy | None:
    if strategy_type == "heuristic_first":
        return HeuristicFirstStrategy(HeuristicFirstConfig(
            confidence_threshold=float(kwargs.get("threshold", 0.7)),
        ))
    return None  # Unknown strategy type
```

## File Changes

| File | Change |
|------|--------|
| `server.py` (executive) | Add `DecisionStrategy` Protocol, `DecisionContext`, `DecisionResult`, `DecisionPath`, `HeuristicCandidate` |
| `server.py` (executive) | Add `HeuristicFirstStrategy` class with `HeuristicFirstConfig` |
| `server.py` (executive) | Move `ReasoningTrace` and trace storage into strategy |
| `server.py` (executive) | Refactor `ExecutiveServicer.ProcessEvent` to delegate |
| `server.py` (executive) | Add `create_decision_strategy` factory |
| `server.py` (executive) | Update `serve()` to use factories |

## Testing

- Unit test `HeuristicFirstStrategy.decide()` with various `DecisionContext` inputs
- Mock `LLMProvider` for deterministic tests
- Test heuristic path when best candidate confidence >= threshold
- Test LLM path when confidence < threshold (verify candidates in prompt)
- Test rejected path when no LLM and not immediate
- Test fallback path when LLM returns None
- Test confidence ceiling is applied (F-06)
- Test empty candidates list (supports F-25 sleep-cycle re-evaluation)

## Design Decisions (from Phase 1 findings)

### F-04: Candidate presentation in LLM prompt

- Candidates shown with **condition + action only** — no scores (avoids anchoring bias)
- Order **randomized** (avoids positional bias)
- Framed as "previous responses to similar situations" with explicit permission to ignore
- **Approach A**: LLM generates independently; convergence detected in post-processing (not selection menu)
- Max candidates: **configurable** (default 3, hard max 5)
- Convergence recorded in `metadata`, **not** used to boost confidence directly

### F-06: LLM confidence calibration

- `predicted_success` = probability response leads to goal state
- `prediction_confidence` = epistemic uncertainty (how much info available)
- Raw LLM values **capped at 0.8** (`llm_confidence_ceiling`)
- LLM-path heuristics still start at 0.3 regardless of LLM self-assessment

### F-07: Goal context

- `DecisionContext.goals` carries active goals
- Goals injected into **system prompt** (after personality, before event data)
- Phase 2: static per-domain goals from config. Dynamic selection deferred to F-08

### F-24: Personality bias as threshold modifier

- Personality = bias (weighted preferences, threshold adjustments), NOT strategy override
- `DecisionContext.personality_biases` carries named biases as float adjustments (e.g., `{"confidence_threshold": -0.05}` lowers the threshold by 0.05)
- Strategies apply biases to their internal thresholds — e.g., `HeuristicFirstStrategy` adjusts `confidence_threshold` by `personality_biases.get("confidence_threshold", 0.0)`
- Empty dict = no bias (default). Populated from user profile or domain config
- Biases are bounded — strategies should clamp adjusted thresholds to safe ranges

### F-25: Sleep-cycle compatibility

- Protocol supports empty candidates list — `decide()` works for both real-time and sleep-cycle re-evaluation
- Sleep-cycle provides clean convergence signal (no candidate contamination)

## Future: Feedback Handling

The strategy owns reasoning traces, so it will handle feedback when that's formalized. Current implementation uses binary feedback (positive/negative). Future approaches to explore:

1. **Scaled feedback** (1-5 rating) — more signal than binary, but UX cost
2. **Multi-dimensional feedback** — separate ratings for match quality vs response quality
3. **Weighted feedback** — confidence update magnitude varies by:
   - Feedback source (explicit user vs implicit timeout)
   - User calibration (some users are harsher/gentler raters)
   - Time since response (immediate feedback weighted higher?)
   - Response path (heuristic vs LLM — different confidence semantics?)

These aren't defined yet. The current binary approach stays for this implementation. When feedback handling is formalized, the strategy Protocol will gain:

```python
async def handle_feedback(
    self,
    response_id: str,
    feedback: FeedbackData,  # TBD: binary, scaled, or multi-dimensional
    llm: LLMProvider | None,
) -> FeedbackResult:
    """Handle feedback on a previous response."""
    ...
```

See also: `docs/design/questions/feedback-signal-decomposition.md`, `docs/design/questions/user-feedback-calibration.md`

## Selection Strategy (Design Direction)

*Added 2026-02-08. Full design in [urgency-selection.md](questions/urgency-selection.md).*

The current selection strategy is **similarity-dominant**: the heuristic with the highest condition-match similarity wins, with confidence used only as a pass/fail filter (>= threshold). This is correct for ranking but the binary threshold is too rigid.

### Planned: Urgency-Modulated Threshold

```
effective_threshold = base_threshold - (urgency Ã— threshold_reduction)
```

High urgency lowers the bar for heuristic firing. Low urgency keeps the baseline, preferring LLM. Three behavioral tiers:

| Tier | Urgency | Data source | Behavior |
|------|---------|-------------|----------|
| Immediate | High | Cache first, DB fallback | Fire any reasonable match — speed over quality |
| Soon | Moderate | DB always | Weighted selection from full candidate pool |
| Not urgent | Low | DB + LLM preferred | Only fire singular high-match + high-confidence; otherwise LLM |

**Selection ranking** within a tier: similarity-dominant, confidence as tiebreaker when similarities are close. A 0.3-confidence heuristic with 0.9 context match beats a 0.7-confidence with 0.6 match.

### Heuristic Cache Decision (Phase 2)

**No cache for Phase 2.** The Rust salience gateway's LRU cache exists but should be bypassed — DB is sole source of truth. Cache saves 1-10ms on local PostgreSQL queries; the real bottleneck is LLM latency. Cache coherence (syncing confidence updates) adds complexity without proportional benefit.

If a cache is added later: read-through only (never write-back), domain-partitioned.

### Three Measurement Dimensions

The decision strategy interacts with three distinct metrics (see [CONFIDENCE_BOOTSTRAPPING.md](CONFIDENCE_BOOTSTRAPPING.md) §Three Measurement Dimensions):

- **Context match** (similarity) — primary selection criterion
- **Confidence** (trust) — threshold gate, not ranking factor
- **Success rate** (correctness) — not yet used in selection; future work may incorporate it

## Out of Scope

- Feedback handling details — deferred until feedback model is designed
- Quality gate and dedup logic — stays in current `ProvideFeedback` for now
- Alternative strategies — add in Phase 2
- Convergence detection implementation — captured in metadata structure, actual embedding comparison deferred
- Dynamic goal selection per event (F-08) — Phase 2 uses static goals
- Urgency implementation details — see [urgency-selection.md](questions/urgency-selection.md)
