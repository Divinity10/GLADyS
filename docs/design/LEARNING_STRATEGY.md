# Learning Strategy Interface Spec

**Status**: Proposed
**Date**: 2026-02-02
**Implements**: Extensibility Review item #2

## Purpose

Define an abstract interface for learning signal interpretation so that PoC 2 can test alternative learning models (e.g., reinforcement learning) without modifying the Orchestrator's router or LearningModule facade.

## Current State

`LearningModule` in `src/services/orchestrator/gladys_orchestrator/learning.py` hardcodes signal interpretation logic:

- Undo detection: substring match against `["undo", "revert", "cancel", ...]` (line 314)
- Ignore detection: `IGNORED_THRESHOLD = 3` consecutive ignores = negative (line 31)
- Timeout: `UNDO_WINDOW_SEC = 60`, no complaint = positive (line 28)

These constants are module-level literals. Swapping logic requires editing the file.

## Design Decision

**Boundary**: Strategy owns signal interpretation only. Confidence math stays in Memory.

**Rationale**: Memory already owns the confidence data (fire_count, success_count). Signal interpretation is where PoC 2 experiments differ. If custom confidence math is needed, add a new RPC.

## Protocol

```python
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Any


class SignalType(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class FeedbackSignal:
    signal_type: SignalType
    heuristic_id: str
    event_id: str
    source: str  # "explicit", "implicit_timeout", "implicit_undo", "implicit_ignored"
    metadata: dict[str, Any]


class LearningStrategy(Protocol):
    """Interface for learning signal interpretation."""

    def interpret_explicit_feedback(
        self, event_id: str, heuristic_id: str, positive: bool, source: str
    ) -> FeedbackSignal:
        """Interpret explicit user feedback (thumbs up/down)."""
        ...

    def interpret_timeout(
        self, heuristic_id: str, event_id: str, elapsed_seconds: float
    ) -> FeedbackSignal:
        """Interpret a timeout (no complaint within window)."""
        ...

    def interpret_event_for_undo(
        self, event_text: str, recent_fires: list[dict]
    ) -> list[FeedbackSignal]:
        """Check if event text indicates an undo of recent fires."""
        ...

    def interpret_ignore(
        self, heuristic_id: str, consecutive_count: int
    ) -> FeedbackSignal:
        """Interpret consecutive ignores of a heuristic."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Return configuration for logging."""
        ...
```

## Default Implementation: BayesianStrategy

```python
@dataclass
class BayesianStrategyConfig:
    undo_window_sec: float = 60.0
    ignored_threshold: int = 3
    undo_keywords: tuple[str, ...] = ("undo", "revert", "cancel", "rollback", "nevermind", "never mind")


class BayesianStrategy:
    """Current PoC 1 learning strategy — implicit signals."""

    def __init__(self, config: BayesianStrategyConfig | None = None):
        self._config = config or BayesianStrategyConfig()

    def interpret_explicit_feedback(self, event_id, heuristic_id, positive, source) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE if positive else SignalType.NEGATIVE,
            heuristic_id=heuristic_id,
            event_id=event_id,
            source="explicit",
            metadata={"original_source": source},
        )

    def interpret_timeout(self, heuristic_id, event_id, elapsed_seconds) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE,  # No news is good news
            heuristic_id=heuristic_id,
            event_id=event_id,
            source="implicit_timeout",
            metadata={"elapsed_seconds": elapsed_seconds},
        )

    def interpret_event_for_undo(self, event_text, recent_fires) -> list[FeedbackSignal]:
        text_lower = event_text.lower()
        if not any(kw in text_lower for kw in self._config.undo_keywords):
            return []
        return [
            FeedbackSignal(
                signal_type=SignalType.NEGATIVE,
                heuristic_id=fire["heuristic_id"],
                event_id=fire["event_id"],
                source="implicit_undo",
                metadata={"undo_text": event_text[:100]},
            )
            for fire in recent_fires
        ]

    def interpret_ignore(self, heuristic_id, consecutive_count) -> FeedbackSignal:
        if consecutive_count >= self._config.ignored_threshold:
            return FeedbackSignal(
                signal_type=SignalType.NEGATIVE,
                heuristic_id=heuristic_id,
                event_id="",
                source="implicit_ignored",
                metadata={"consecutive_count": consecutive_count},
            )
        return FeedbackSignal(
            signal_type=SignalType.NEUTRAL,
            heuristic_id=heuristic_id,
            event_id="",
            source="implicit_ignored",
            metadata={"consecutive_count": consecutive_count},
        )

    @property
    def config(self) -> dict[str, Any]:
        return {
            "strategy": "bayesian",
            "undo_window_sec": self._config.undo_window_sec,
            "ignored_threshold": self._config.ignored_threshold,
        }
```

## LearningModule Changes

1. Accept `strategy: LearningStrategy` in constructor (default: `BayesianStrategy()`)
2. Add `_apply_signal(signal)` helper that calls Memory based on signal type
3. Delegate `_check_undo_signal` → `self._strategy.interpret_event_for_undo`
4. Delegate `on_heuristic_ignored` → `self._strategy.interpret_ignore`
5. Delegate timeout handling in `cleanup_expired` → `self._strategy.interpret_timeout`

```python
class LearningModule:
    def __init__(
        self,
        memory_client: Any,
        outcome_watcher: OutcomeWatcher | None,
        strategy: LearningStrategy | None = None,
    ):
        self._memory_client = memory_client
        self._outcome_watcher = outcome_watcher
        self._strategy = strategy or BayesianStrategy()

    async def _apply_signal(self, signal: FeedbackSignal) -> None:
        if signal.signal_type == SignalType.NEUTRAL:
            return
        if not self._memory_client:
            logger.warning("signal_skipped", reason="no memory client")
            return
        await self._memory_client.update_heuristic_confidence(
            heuristic_id=signal.heuristic_id,
            positive=(signal.signal_type == SignalType.POSITIVE),
            feedback_source=signal.source,
        )
```

## Configuration

Add to `OrchestratorConfig`:

```python
learning_strategy: str = "bayesian"
learning_undo_window_sec: float = 60.0
learning_ignored_threshold: int = 3
```

Factory:

```python
def create_learning_strategy(config: OrchestratorConfig) -> LearningStrategy:
    if config.learning_strategy == "bayesian":
        return BayesianStrategy(BayesianStrategyConfig(
            undo_window_sec=config.learning_undo_window_sec,
            ignored_threshold=config.learning_ignored_threshold,
        ))
    raise ValueError(f"Unknown learning strategy: {config.learning_strategy}")
```

## Cleanup: Remove Unused Parameters

Memory's `update_heuristic_confidence` RPC accepts `learning_rate` and `predicted_success` that are ignored. Remove them:

| File | Change |
|------|--------|
| `memory.proto` | Remove `learning_rate`, `predicted_success` from `UpdateHeuristicConfidenceRequest` |
| `storage.py` | Remove unused params from `update_heuristic_confidence()` |
| `grpc_server.py` | Update RPC handler |

## File Changes

| File | Change |
|------|--------|
| `learning.py` | Add Protocol, dataclasses, `BayesianStrategy`, refactor `LearningModule` |
| `server.py` (orchestrator) | Pass strategy to `LearningModule` |
| `config.py` (orchestrator) | Add strategy config fields |
| `memory.proto` | Remove unused fields |
| `storage.py` | Remove unused params |

## Testing

- Unit test `BayesianStrategy` — each `interpret_*` method
- Test undo detection with various keywords
- Test ignore threshold boundary (2 ignores = NEUTRAL, 3 = NEGATIVE)
- Regression test: default behavior unchanged

## Out of Scope

- RL strategy implementation — PoC 2
- Per-heuristic strategy selection — all heuristics use same strategy
- Custom confidence math — Memory's Bayesian update unchanged
