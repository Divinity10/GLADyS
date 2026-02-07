# Learning Strategy Interface Spec

**Status**: Proposed
**Date**: 2026-02-02 (updated 2026-02-06 with PoC 1 findings F-03, F-11, F-23, F-24)
**Implements**: Extensibility Review item #3

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
    source: str  # "user_explicit", "user_implicit", "dev", "implicit_timeout", "implicit_undo", "implicit_ignored"
    magnitude: float  # Weight of this signal (default 1.0). Enables F-03 gradient decay and F-23 score magnitudes.
    metadata: dict[str, Any]


class LearningStrategy(Protocol):
    """Interface for learning signal interpretation."""

    def interpret_explicit_feedback(
        self, event_id: str, heuristic_id: str, positive: bool, source: str
    ) -> FeedbackSignal:
        """Interpret explicit feedback. For PoC 1: binary (positive: bool).
        PoC 2 extends to granular scores via F-23 (3-point user, 5-point dev)."""
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
    undo_window_sec: float = 30.0  # F-11: time-based implicit window, configurable per-domain
    ignored_threshold: int = 3
    undo_keywords: tuple[str, ...] = ("undo", "revert", "cancel", "rollback", "nevermind", "never mind")
    implicit_magnitude: float = 1.0  # F-03: implicit > explicit (implicit is default weight)
    explicit_magnitude: float = 0.8  # F-03: explicit feedback weighted lower than implicit


class BayesianStrategy:
    """Current PoC 1 learning strategy — implicit signals."""

    def __init__(self, config: BayesianStrategyConfig | None = None):
        self._config = config or BayesianStrategyConfig()

    def interpret_explicit_feedback(self, event_id, heuristic_id, positive, source) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE if positive else SignalType.NEGATIVE,
            heuristic_id=heuristic_id,
            event_id=event_id,
            source="user_explicit",
            magnitude=self._config.explicit_magnitude,  # F-03: explicit weighted lower
            metadata={"original_source": source},
        )

    def interpret_timeout(self, heuristic_id, event_id, elapsed_seconds) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE,  # No news is good news
            heuristic_id=heuristic_id,
            event_id=event_id,
            source="implicit_timeout",
            magnitude=self._config.implicit_magnitude,  # F-03: implicit is default weight
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
                magnitude=self._config.implicit_magnitude,
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
                magnitude=self._config.implicit_magnitude,
                metadata={"consecutive_count": consecutive_count},
            )
        return FeedbackSignal(
            signal_type=SignalType.NEUTRAL,
            heuristic_id=heuristic_id,
            event_id="",
            source="implicit_ignored",
            magnitude=0.0,  # Neutral signals are skipped anyway
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
            magnitude=signal.magnitude,  # F-03: weight of this signal
        )
```

## Configuration

Add to `OrchestratorConfig` (pydantic-settings reads from env vars / `.env` file):

```python
learning_strategy: str = "bayesian"
learning_undo_window_sec: float = 30.0  # F-11: implicit timeout window
learning_ignored_threshold: int = 3
learning_undo_keywords: str = "undo,revert,cancel,rollback,nevermind,never mind"
learning_implicit_magnitude: float = 1.0  # F-03: implicit signal weight
learning_explicit_magnitude: float = 0.8  # F-03: explicit signal weight (lower than implicit)
```

Corresponding environment variables (override defaults via `.env` or shell):
```
LEARNING_STRATEGY=bayesian
LEARNING_UNDO_WINDOW_SEC=30.0
LEARNING_IGNORED_THRESHOLD=3
LEARNING_UNDO_KEYWORDS=undo,revert,cancel,rollback,nevermind,never mind
LEARNING_IMPLICIT_MAGNITUDE=1.0
LEARNING_EXPLICIT_MAGNITUDE=0.8
```

Factory:

```python
def create_learning_strategy(config: OrchestratorConfig) -> LearningStrategy:
    if config.learning_strategy == "bayesian":
        # Parse comma-separated keywords
        keywords = tuple(k.strip() for k in config.learning_undo_keywords.split(","))
        return BayesianStrategy(BayesianStrategyConfig(
            undo_window_sec=config.learning_undo_window_sec,
            ignored_threshold=config.learning_ignored_threshold,
            undo_keywords=keywords,
            implicit_magnitude=config.learning_implicit_magnitude,
            explicit_magnitude=config.learning_explicit_magnitude,
        ))
    raise ValueError(f"Unknown learning strategy: {config.learning_strategy}")
```

## Proto Changes

Memory's `update_heuristic_confidence` RPC needs changes:

1. **Remove** unused `learning_rate` field
2. **Keep** `predicted_success` — not yet incorporated but planned
3. **Add** `magnitude` field (float, default 1.0) and `feedback_source` field (string)

| File | Change |
|------|--------|
| `memory.proto` | Remove `learning_rate`. Add `magnitude` (float) and `feedback_source` (string) to `UpdateHeuristicConfidenceRequest` |
| `storage.py` | Remove `learning_rate` param, add `magnitude` and `feedback_source` to `update_heuristic_confidence()` |
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

## PoC 1 Findings Incorporated

| Finding | What changed | Where |
|---------|-------------|-------|
| F-03 | `magnitude` field on `FeedbackSignal`. `implicit_magnitude` and `explicit_magnitude` config. Implicit > explicit weighting. | FeedbackSignal, BayesianStrategyConfig |
| F-11 | Implicit timeout default changed 60s → 30s. Per-domain configurable. Explicit: unlimited, last click wins (no change to strategy — handled by caller). Both implicit and explicit are independent channels. | BayesianStrategyConfig.undo_window_sec |
| F-23 | `source` field expanded to `user_explicit`, `user_implicit`, `dev`. Protocol signature unchanged for PoC 1 (binary). PoC 2 extends to granular scores. | FeedbackSignal.source |
| F-24 | Not enforced in strategy — constraints (locked/floor/ceiling/feedback_weight) are enforced in `_apply_signal` or Memory. Strategy returns signals; LearningModule checks constraints before applying. | Documented, not implemented |

### F-03 design: implicit > explicit

Per F-03 Q3: "implicit feedback weighted higher than explicit (correctness > user happiness)." Implicit = "it worked in practice"; explicit = "user opinion" (noisy, biased negative). Both can coexist for the same event. The `magnitude` field carries this weight to Memory's update function.

F-03 also resolved: decay function (`1 / (1 + k * n)`) for diminishing returns on repeated feedback. This is a **PoC 2 extension** — BayesianStrategy currently uses flat magnitudes.

### F-24 design: constraint enforcement

Pack constraints (`locked`, `floor`, `ceiling`, `feedback_weight`) are NOT checked in the strategy. The strategy is algorithm-agnostic — it interprets signals, not enforce policies. Enforcement goes in `_apply_signal` (LearningModule) or Memory's `update_heuristic_confidence`. For this extraction: pass `magnitude` through; constraint enforcement is a separate task.

## PoC 2 Extensions (not built now, Protocol supports them)

- **F-03 decay**: `BayesianStrategy.interpret_explicit_feedback` applies `magnitude *= 1 / (1 + k * n)` where n is observation count
- **F-23 granular scores**: Protocol method signature changes to `interpret_explicit_feedback(event_id, heuristic_id, score: int, source: str)`. BayesianStrategy maps 3-point/5-point scores to magnitudes via config
- **F-24 constraints**: `_apply_signal` checks constraints before calling Memory. `feedback_weight` multiplies `signal.magnitude`

## Out of Scope

- RL strategy implementation — PoC 2
- Per-heuristic strategy selection — all heuristics use same strategy
- Custom confidence math — Memory's Bayesian update unchanged
- F-03 decay function — PoC 2 (Protocol supports it via magnitude)
- F-23 granular score mapping — PoC 2 (Protocol supports it via source field)
- F-24 constraint enforcement — separate task (not a strategy concern)
