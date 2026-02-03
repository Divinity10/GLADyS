# Decision Strategy Interface Spec

**Status**: Proposed
**Date**: 2026-02-02
**Implements**: Extensibility Review item #1 (partial)
**Depends on**: [LLM_PROVIDER.md](LLM_PROVIDER.md)

## Purpose

Define an abstract interface for event decision logic so that PoC 2 can A/B test different strategies (heuristic-first, always-LLM, hybrid) without modifying the Executive's gRPC handler.

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
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Any


class DecisionPath(Enum):
    """Which path the decision took."""
    HEURISTIC = "heuristic"
    LLM = "llm"
    FALLBACK = "fallback"
    REJECTED = "rejected"


@dataclass
class DecisionContext:
    """Input to a decision strategy."""
    event_id: str
    event_text: str
    event_source: str
    salience: dict[str, float]
    suggestion: dict[str, Any] | None  # {heuristic_id, confidence, condition_text, suggested_action}
    immediate: bool


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
    metadata: dict[str, Any]


class DecisionStrategy(Protocol):
    """Interface for event decision logic."""

    async def decide(
        self,
        context: DecisionContext,
        llm: LLMProvider | None,
    ) -> DecisionResult:
        """Decide how to respond to an event."""
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
    system_prompt: str = EXECUTIVE_SYSTEM_PROMPT
    prediction_prompt_template: str = PREDICTION_PROMPT


class HeuristicFirstStrategy:
    """Use heuristic if confident, else LLM."""

    def __init__(self, config: HeuristicFirstConfig | None = None):
        self._config = config or HeuristicFirstConfig()
        self._trace_store: dict[str, ReasoningTrace] = {}

    async def decide(self, context: DecisionContext, llm: LLMProvider | None) -> DecisionResult:
        # Path 1: High-confidence heuristic
        if (context.suggestion
                and context.suggestion.get("confidence", 0) >= self._config.confidence_threshold):
            return self._heuristic_path(context)

        # Path 2: LLM reasoning
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

    def _heuristic_path(self, context: DecisionContext) -> DecisionResult:
        suggestion = context.suggestion
        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=suggestion["suggested_action"],
            matched_heuristic_id=suggestion["heuristic_id"],
            predicted_success=suggestion["confidence"],
        )
        return DecisionResult(
            path=DecisionPath.HEURISTIC,
            response_text=suggestion["suggested_action"],
            response_id=response_id,
            matched_heuristic_id=suggestion["heuristic_id"],
            predicted_success=suggestion["confidence"],
            prediction_confidence=suggestion["confidence"],
            prompt_text="",
            metadata={"threshold": self._config.confidence_threshold},
        )

    async def _llm_path(self, context: DecisionContext, llm: LLMProvider) -> DecisionResult:
        prompt = self._build_prompt(context)
        llm_response = await llm.generate(LLMRequest(
            prompt=prompt,
            system_prompt=self._config.system_prompt,
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
        predicted_success, prediction_confidence = await self._get_prediction(llm, context, response_text)

        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=response_text,
            matched_heuristic_id=context.suggestion.get("heuristic_id") if context.suggestion else None,
            predicted_success=predicted_success,
        )

        return DecisionResult(
            path=DecisionPath.LLM,
            response_text=response_text,
            response_id=response_id,
            matched_heuristic_id=context.suggestion.get("heuristic_id") if context.suggestion else None,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
            prompt_text=prompt,
            metadata={"model": llm.model_name},
        )

    def _build_prompt(self, context: DecisionContext) -> str:
        prompt = f"URGENT event: [{context.event_source}]: {context.event_text}\n\n"
        if context.suggestion:
            prompt += f"""A learned pattern matched this situation:
- Pattern: "{context.suggestion.get('condition_text', '')}"
- Suggested action: "{context.suggestion.get('suggested_action', '')}"
- Confidence: {context.suggestion.get('confidence', 0):.0%}

Consider this suggestion in your response.

"""
        prompt += "How should I respond?"
        return prompt

    async def _get_prediction(self, llm: LLMProvider, context: DecisionContext, response_text: str) -> tuple[float, float]:
        # ... prediction logic (unchanged from current impl)
        pass

    def _store_trace(self, **kwargs) -> str:
        response_id = str(uuid.uuid4())
        self._trace_store[response_id] = ReasoningTrace(response_id=response_id, timestamp=time.time(), **kwargs)
        return response_id

    def get_trace(self, response_id: str) -> ReasoningTrace | None:
        return self._trace_store.get(response_id)

    @property
    def config(self) -> dict[str, Any]:
        return {"strategy": "heuristic_first", "confidence_threshold": self._config.confidence_threshold}
```

## ExecutiveServicer Changes

`ProcessEvent` becomes a thin wrapper:

```python
async def ProcessEvent(self, request, context) -> ProcessEventResponse:
    self._setup_trace(context)

    decision_context = DecisionContext(
        event_id=request.event.id,
        event_text=request.event.raw_text,
        event_source=request.event.source,
        salience=self._extract_salience(request.event.salience),
        suggestion=self._extract_suggestion(request.suggestion) if request.HasField("suggestion") else None,
        immediate=request.immediate,
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
```

Factory:
```python
def create_decision_strategy(strategy_type: str, **kwargs) -> DecisionStrategy:
    if strategy_type == "heuristic_first":
        return HeuristicFirstStrategy(HeuristicFirstConfig(
            confidence_threshold=float(kwargs.get("threshold", 0.7)),
        ))
    raise ValueError(f"Unknown decision strategy: {strategy_type}")
```

## File Changes

| File | Change |
|------|--------|
| `server.py` (executive) | Add `DecisionStrategy` Protocol, `DecisionContext`, `DecisionResult`, `DecisionPath` |
| `server.py` (executive) | Add `HeuristicFirstStrategy` class |
| `server.py` (executive) | Move `ReasoningTrace` and trace storage into strategy |
| `server.py` (executive) | Refactor `ExecutiveServicer.ProcessEvent` to delegate |
| `server.py` (executive) | Add `create_decision_strategy` factory |
| `server.py` (executive) | Update `serve()` to use factories |

## Testing

- Unit test `HeuristicFirstStrategy.decide()` with various `DecisionContext` inputs
- Mock `LLMProvider` for deterministic tests
- Test heuristic path when confidence >= threshold
- Test LLM path when confidence < threshold
- Test rejected path when no LLM and not immediate

## Out of Scope

- Feedback handling (`ProvideFeedback`) — separate spec if needed
- Quality gate and dedup logic — stays in feedback handler for now
- Alternative strategies — add in PoC 2
