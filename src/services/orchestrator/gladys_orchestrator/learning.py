"""Learning Module — facade for all learning-related operations.

Consolidates scattered learning calls (confidence updates, fire recording,
outcome watching, implicit feedback signals) behind a clean interface.

The router interacts only with LearningModule for learning operations.
Memory and OutcomeWatcher are internal dependencies.

Implicit feedback signals:
- Timeout = positive: no complaint within timeout → heuristic was correct
- Undo within 60s = negative: user undid the action
- Ignored 3x = negative: heuristic fired 3 times without engagement
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import Any, Protocol, TYPE_CHECKING

from gladys_common import get_logger

from .outcome_watcher import OutcomeWatcher

if TYPE_CHECKING:
    from .config import OrchestratorConfig

logger = get_logger(__name__)


class SignalType(Enum):
    """Types of feedback signals."""

    POSITIVE = auto()
    NEGATIVE = auto()
    NEUTRAL = auto()


@dataclass(frozen=True)
class FeedbackSignal:
    """A learning signal produced by a strategy."""

    signal_type: SignalType
    heuristic_id: str
    event_id: str = ""
    source: str = ""
    magnitude: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LearningStrategy(Protocol):
    """Protocol for learning strategies that interpret signals."""

    def interpret_explicit_feedback(
        self, event_id: str, heuristic_id: str, positive: bool, source: str
    ) -> FeedbackSignal:
        """Interpret explicit user feedback."""
        ...

    def interpret_timeout(
        self, heuristic_id: str, event_id: str, elapsed_seconds: float
    ) -> FeedbackSignal:
        """Interpret an outcome expectation timeout."""
        ...

    def interpret_event_for_undo(
        self, event_text: str, recent_fires: list[dict[str, str]]
    ) -> list[FeedbackSignal]:
        """Interpret an incoming event as a potential undo of recent actions."""
        ...

    def interpret_ignore(
        self, heuristic_id: str, consecutive_count: int
    ) -> FeedbackSignal:
        """Interpret consecutive ignores of a heuristic."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Return the strategy's current configuration."""
        ...


@dataclass
class BayesianStrategyConfig:
    """Configuration for Bayesian learning strategy."""

    undo_window_sec: float = 30.0
    ignored_threshold: int = 3
    undo_keywords: tuple[str, ...] = (
        "undo",
        "revert",
        "cancel",
        "rollback",
        "nevermind",
        "never mind",
    )
    implicit_magnitude: float = 1.0
    explicit_magnitude: float = 0.8


class BayesianStrategy:
    """Default Bayesian learning strategy using Beta-Binomial updates."""

    def __init__(self, config: BayesianStrategyConfig):
        self._config = config

    def interpret_explicit_feedback(
        self, event_id: str, heuristic_id: str, positive: bool, source: str
    ) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE if positive else SignalType.NEGATIVE,
            heuristic_id=heuristic_id,
            event_id=event_id,
            source=source,
            magnitude=self._config.explicit_magnitude,
        )

    def interpret_timeout(
        self, heuristic_id: str, event_id: str, elapsed_seconds: float
    ) -> FeedbackSignal:
        return FeedbackSignal(
            signal_type=SignalType.POSITIVE,
            heuristic_id=heuristic_id,
            event_id=event_id,
            source="implicit_timeout",
            magnitude=self._config.implicit_magnitude,
        )

    def interpret_event_for_undo(
        self, event_text: str, recent_fires: list[dict[str, str]]
    ) -> list[FeedbackSignal]:
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

    def interpret_ignore(
        self, heuristic_id: str, consecutive_count: int
    ) -> FeedbackSignal:
        if consecutive_count >= self._config.ignored_threshold:
            return FeedbackSignal(
                signal_type=SignalType.NEGATIVE,
                heuristic_id=heuristic_id,
                source="implicit_ignored",
                magnitude=self._config.implicit_magnitude,
            )
        return FeedbackSignal(
            signal_type=SignalType.NEUTRAL,
            heuristic_id=heuristic_id,
        )

    @property
    def config(self) -> dict[str, Any]:
        return {
            "undo_window_sec": self._config.undo_window_sec,
            "ignored_threshold": self._config.ignored_threshold,
            "undo_keywords": self._config.undo_keywords,
            "implicit_magnitude": self._config.implicit_magnitude,
            "explicit_magnitude": self._config.explicit_magnitude,
        }


def create_learning_strategy(config: "OrchestratorConfig") -> LearningStrategy:
    """Factory for learning strategies."""
    if config.learning_strategy == "bayesian":
        undo_keywords = tuple(
            kw.strip() for kw in config.learning_undo_keywords.split(",")
        )
        strategy_config = BayesianStrategyConfig(
            undo_window_sec=config.learning_undo_window_sec,
            ignored_threshold=config.learning_ignored_threshold,
            undo_keywords=undo_keywords,
            implicit_magnitude=config.learning_implicit_magnitude,
            explicit_magnitude=config.learning_explicit_magnitude,
        )
        return BayesianStrategy(strategy_config)
    raise ValueError(f"Unknown learning strategy: {config.learning_strategy}")


@dataclass
class FireRecord:
    """In-memory record of a heuristic fire for implicit signal tracking."""

    heuristic_id: str
    event_id: str
    fire_time: datetime
    condition_text: str
    predicted_success: float
    source: str = ""


class LearningModule:
    """Facade for all learning operations in the Orchestrator.

    Owns the interaction with memory_client and outcome_watcher for
    feedback, fire recording, and implicit signal detection.
    """

    def __init__(
        self,
        memory_client: Any,  # TODO: add Protocol type when interface stabilizes
        outcome_watcher: OutcomeWatcher | None,
        strategy: LearningStrategy,
    ) -> None:
        self._memory_client = memory_client
        self._outcome_watcher = outcome_watcher
        self._strategy = strategy

        # Recent fires for undo and ignore detection
        self._recent_fires: list[FireRecord] = []
        self._fires_lock = asyncio.Lock()

        # Event IDs that received explicit feedback (not ignored)
        self._acknowledged_fires: set[str] = set()

        # Ignore counter: heuristic_id -> consecutive ignore count
        self._ignore_counts: dict[str, int] = defaultdict(int)

    async def _apply_signal(self, signal: FeedbackSignal) -> None:
        """Apply a feedback signal to memory."""
        if signal.signal_type == SignalType.NEUTRAL:
            return

        if not self._memory_client:
            logger.warning("signal_skipped", reason="no memory client")
            return

        positive = signal.signal_type == SignalType.POSITIVE
        result = await self._memory_client.update_heuristic_confidence(
            heuristic_id=signal.heuristic_id,
            positive=positive,
            magnitude=signal.magnitude,
            feedback_source=signal.source,
        )

        if not result or not result.get("success"):
            logger.warning(
                "confidence_update_failed",
                heuristic_id=signal.heuristic_id,
                error=result.get("error") if result else "no result",
            )

    async def on_feedback(
        self,
        event_id: str,
        heuristic_id: str,
        positive: bool,
        source: str,
    ) -> None:
        """Handle explicit feedback. Calls Memory service for confidence update."""
        logger.info(
            "feedback_received",
            heuristic_id=heuristic_id,
            event_id=event_id,
            positive=positive,
            source=source,
        )

        signal = self._strategy.interpret_explicit_feedback(
            event_id=event_id,
            heuristic_id=heuristic_id,
            positive=positive,
            source=source,
        )
        await self._apply_signal(signal)

        # Mark this fire as acknowledged (not ignored)
        self._acknowledged_fires.add(event_id)
        # Reset ignore counter on any explicit feedback
        self._ignore_counts.pop(heuristic_id, None)

    async def on_fire(
        self,
        heuristic_id: str,
        event_id: str,
        condition_text: str,
        predicted_success: float,
        source: str = "",
    ) -> None:
        """Register heuristic fire. Records in flight recorder, registers with outcome watcher."""
        logger.info(
            "heuristic_fire_registered",
            heuristic_id=heuristic_id,
            event_id=event_id,
        )

        # Record in flight recorder (Memory service)
        if self._memory_client:
            try:
                await self._memory_client.record_heuristic_fire(
                    heuristic_id=heuristic_id,
                    event_id=event_id,
                    episodic_event_id=event_id,
                )
            except Exception as e:
                logger.warning(
                    "fire_record_failed",
                    heuristic_id=heuristic_id,
                    error=str(e),
                )

        # Register with outcome watcher for pattern-based implicit feedback
        if self._outcome_watcher:
            await self._outcome_watcher.register_fire(
                heuristic_id=heuristic_id,
                event_id=event_id,
                predicted_success=predicted_success,
                condition_text=condition_text,
            )

        # Track for undo and ignore detection
        record = FireRecord(
            heuristic_id=heuristic_id,
            event_id=event_id,
            fire_time=datetime.now(UTC),
            condition_text=condition_text,
            predicted_success=predicted_success,
            source=source,
        )
        async with self._fires_lock:
            self._recent_fires.append(record)

    async def check_event_for_outcomes(self, event: Any) -> list[str]:
        """Check if incoming event resolves any pending outcomes.

        Also checks for undo signals and ignored heuristic fires.
        Returns resolved heuristic IDs.
        """
        resolved: list[str] = []

        # Check outcome watcher for pattern-based matches
        if self._outcome_watcher:
            matched = await self._outcome_watcher.check_event(event)
            resolved.extend(matched)

        # Check for undo signal
        raw_text = getattr(event, "raw_text", "") or ""
        if raw_text:
            undo_ids = await self._check_undo_signal(raw_text)
            resolved.extend(undo_ids)

        # Check for ignored fires: a new event from the same source means
        # the user moved on without giving feedback on a previous fire.
        event_source = getattr(event, "source", "") or ""
        if event_source:
            await self._check_ignored_fires(event_source)

        return resolved

    async def on_heuristic_ignored(self, heuristic_id: str) -> None:
        """Track that a heuristic suggestion was ignored (not acted upon).

        After IGNORED_THRESHOLD consecutive ignores, sends negative implicit feedback.

        Called by _check_ignored_fires() when a new event arrives from the same
        source as a previous fire that received no explicit feedback.
        """
        self._ignore_counts[heuristic_id] += 1
        count = self._ignore_counts[heuristic_id]

        logger.debug(
            "heuristic_ignored",
            heuristic_id=heuristic_id,
            consecutive_count=count,
        )

        signal = self._strategy.interpret_ignore(heuristic_id, count)
        if signal.signal_type != SignalType.NEUTRAL:
            logger.info(
                "implicit_signal_detected",
                signal_type="ignored",
                heuristic_id=heuristic_id,
                count=count,
            )
            await self._apply_signal(signal)
            # Reset counter after sending feedback
            self._ignore_counts[heuristic_id] = 0

    async def cleanup_expired(self) -> int:
        """Clean up timed-out pending outcomes.

        Timeout expiration = implicit positive feedback (no complaint means it worked).
        Returns count of expired expectations processed.
        """
        if not self._outcome_watcher:
            return 0

        # Get expired items before cleanup
        expired_items = await self._outcome_watcher.get_expired_items()

        # Now do the standard cleanup (removes expired from pending list)
        expired_count = await self._outcome_watcher.cleanup_expired()

        # Send positive implicit feedback for each expired expectation
        # (timeout = positive: no complaint means heuristic was correct)
        timeout_sec = self._strategy.config.get("outcome_timeout_sec", 120)
        for heuristic_id, event_id in expired_items:
            logger.info(
                "implicit_signal_detected",
                signal_type="timeout_positive",
                heuristic_id=heuristic_id,
                event_id=event_id,
            )
            signal = self._strategy.interpret_timeout(
                heuristic_id, event_id, float(timeout_sec)
            )
            await self._apply_signal(signal)

        # Also clean up stale fire records (older than undo window)
        now = datetime.now(UTC)
        undo_window = self._strategy.config["undo_window_sec"]
        cutoff = now - timedelta(seconds=undo_window)
        async with self._fires_lock:
            expired_event_ids = {
                r.event_id for r in self._recent_fires if r.fire_time < cutoff
            }
            self._recent_fires = [
                r for r in self._recent_fires if r.fire_time >= cutoff
            ]
        # Clean up acknowledged set for expired fires
        self._acknowledged_fires -= expired_event_ids

        logger.debug(
            "cleanup_stats",
            expired_outcomes=expired_count,
            timeout_positive_sent=len(expired_items),
            remaining_fires=len(self._recent_fires),
            pending_outcomes=self._outcome_watcher.pending_count if self._outcome_watcher else 0,
        )

        return expired_count

    async def _check_undo_signal(self, raw_text: str) -> list[str]:
        """Check if event text indicates an undo of a recent heuristic action.

        Looks for undo-like keywords in events arriving within UNDO_WINDOW_SEC
        of a heuristic fire. Sends negative implicit feedback.

        Returns list of heuristic IDs that received negative feedback.
        """
        now = datetime.now(UTC)
        undo_window = self._strategy.config["undo_window_sec"]
        cutoff = now - timedelta(seconds=undo_window)

        async with self._fires_lock:
            # Filter fires within window
            recent_dicts = [
                {"heuristic_id": r.heuristic_id, "event_id": r.event_id}
                for r in self._recent_fires
                if r.fire_time >= cutoff
            ]

        if not recent_dicts:
            return []

        signals = self._strategy.interpret_event_for_undo(raw_text, recent_dicts)

        affected: list[str] = []
        for signal in signals:
            logger.info(
                "implicit_signal_detected",
                signal_type="undo",
                heuristic_id=signal.heuristic_id,
                event_id=signal.event_id,
                undo_text=raw_text[:100],
            )
            await self._apply_signal(signal)
            affected.append(signal.heuristic_id)

        return affected

    async def _check_ignored_fires(self, event_source: str) -> None:
        """Check if any recent fires from this source were ignored.

        A fire is "ignored" if: it came from the same source as this new event,
        is within the undo window, and never received explicit feedback. When a
        new event arrives from the same source, the user has moved on.
        """
        now = datetime.now(UTC)
        undo_window = self._strategy.config["undo_window_sec"]
        cutoff = now - timedelta(seconds=undo_window)
        ignored_heuristic_ids: list[str] = []

        async with self._fires_lock:
            remaining = []
            for record in self._recent_fires:
                if (
                    record.source == event_source
                    and record.fire_time >= cutoff
                    and record.event_id not in self._acknowledged_fires
                ):
                    ignored_heuristic_ids.append(record.heuristic_id)
                    # Don't keep this fire — it's been evaluated as ignored
                else:
                    remaining.append(record)
            self._recent_fires = remaining

        for heuristic_id in ignored_heuristic_ids:
            await self.on_heuristic_ignored(heuristic_id)
