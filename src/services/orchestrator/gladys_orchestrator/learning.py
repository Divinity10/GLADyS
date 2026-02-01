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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from gladys_common import get_logger

from .outcome_watcher import OutcomeWatcher

logger = get_logger(__name__)

# How long after a fire an "undo" event counts as negative feedback
UNDO_WINDOW_SEC = 60

# How many consecutive ignores before sending negative feedback
IGNORED_THRESHOLD = 3


@dataclass
class FireRecord:
    """In-memory record of a heuristic fire for implicit signal tracking."""

    heuristic_id: str
    event_id: str
    fire_time: datetime
    condition_text: str
    predicted_success: float


class LearningModule:
    """Facade for all learning operations in the Orchestrator.

    Owns the interaction with memory_client and outcome_watcher for
    feedback, fire recording, and implicit signal detection.
    """

    def __init__(
        self,
        memory_client: Any,
        outcome_watcher: OutcomeWatcher | None,
    ) -> None:
        self._memory_client = memory_client
        self._outcome_watcher = outcome_watcher

        # Recent fires for undo detection (keyed by heuristic_id)
        self._recent_fires: list[FireRecord] = []
        self._fires_lock = asyncio.Lock()

        # Ignore counter: heuristic_id -> consecutive ignore count
        self._ignore_counts: dict[str, int] = defaultdict(int)

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

        if not self._memory_client:
            logger.warning("feedback_skipped", reason="no memory client")
            return

        result = await self._memory_client.update_heuristic_confidence(
            heuristic_id=heuristic_id,
            positive=positive,
            feedback_source=source,
        )

        if not result or not result.get("success"):
            logger.warning(
                "confidence_update_failed",
                heuristic_id=heuristic_id,
                error=result.get("error") if result else "no result",
            )

        # Reset ignore counter on any explicit feedback
        self._ignore_counts.pop(heuristic_id, None)

    async def on_fire(
        self,
        heuristic_id: str,
        event_id: str,
        condition_text: str,
        predicted_success: float,
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

        # Track for undo detection
        record = FireRecord(
            heuristic_id=heuristic_id,
            event_id=event_id,
            fire_time=datetime.now(UTC),
            condition_text=condition_text,
            predicted_success=predicted_success,
        )
        async with self._fires_lock:
            self._recent_fires.append(record)

    async def on_outcome(
        self,
        heuristic_id: str,
        event_id: str,
        outcome: str,
    ) -> None:
        """Handle implicit feedback signal. Calls confidence update."""
        positive = outcome == "success"
        logger.info(
            "implicit_signal_detected",
            signal_type="outcome",
            heuristic_id=heuristic_id,
            event_id=event_id,
            outcome=outcome,
            positive=positive,
        )

        if not self._memory_client:
            logger.warning("outcome_skipped", reason="no memory client")
            return

        result = await self._memory_client.update_heuristic_confidence(
            heuristic_id=heuristic_id,
            positive=positive,
            feedback_source="implicit",
        )

        if not result or not result.get("success"):
            logger.warning(
                "confidence_update_failed",
                heuristic_id=heuristic_id,
                error=result.get("error") if result else "no result",
            )

    async def check_event_for_outcomes(self, event: Any) -> list[str]:
        """Check if incoming event resolves any pending outcomes.

        Also checks for undo signals. Returns resolved heuristic IDs.
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

        return resolved

    async def on_heuristic_ignored(self, heuristic_id: str) -> None:
        """Track that a heuristic suggestion was ignored (not acted upon).

        After IGNORED_THRESHOLD consecutive ignores, sends negative implicit feedback.
        """
        self._ignore_counts[heuristic_id] += 1
        count = self._ignore_counts[heuristic_id]

        logger.debug(
            "heuristic_ignored",
            heuristic_id=heuristic_id,
            consecutive_count=count,
        )

        if count >= IGNORED_THRESHOLD:
            logger.info(
                "implicit_signal_detected",
                signal_type="ignored_3x",
                heuristic_id=heuristic_id,
                count=count,
            )
            await self.on_outcome(
                heuristic_id=heuristic_id,
                event_id="",
                outcome="fail",
            )
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
        # Note: outcome_watcher uses naive UTC datetimes (pre-existing tech debt),
        # so we compare with naive UTC here at the boundary.
        now_naive = datetime.utcnow()  # noqa: DTZ003 — matching outcome_watcher convention
        expired_items: list[tuple[str, str]] = []

        async with self._outcome_watcher._lock:
            for p in self._outcome_watcher._pending:
                if p.timeout_at < now_naive:
                    expired_items.append((p.heuristic_id, p.event_id))

        # Now do the standard cleanup (removes expired from pending list)
        expired_count = await self._outcome_watcher.cleanup_expired()

        # Send positive implicit feedback for each expired expectation
        # (timeout = positive: no complaint means heuristic was correct)
        for heuristic_id, event_id in expired_items:
            logger.info(
                "implicit_signal_detected",
                signal_type="timeout_positive",
                heuristic_id=heuristic_id,
                event_id=event_id,
            )
            await self.on_outcome(
                heuristic_id=heuristic_id,
                event_id=event_id,
                outcome="success",
            )

        # Also clean up stale fire records (older than undo window)
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=UNDO_WINDOW_SEC)
        async with self._fires_lock:
            self._recent_fires = [
                r for r in self._recent_fires if r.fire_time >= cutoff
            ]

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
        undo_keywords = ["undo", "revert", "cancel", "rollback", "nevermind", "never mind"]
        text_lower = raw_text.lower()

        if not any(kw in text_lower for kw in undo_keywords):
            return []

        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=UNDO_WINDOW_SEC)
        affected: list[str] = []

        async with self._fires_lock:
            for record in self._recent_fires:
                if record.fire_time >= cutoff:
                    logger.info(
                        "implicit_signal_detected",
                        signal_type="undo",
                        heuristic_id=record.heuristic_id,
                        event_id=record.event_id,
                        undo_text=raw_text[:100],
                    )
                    affected.append(record.heuristic_id)

        # Send negative feedback for each affected heuristic
        for heuristic_id in affected:
            await self.on_outcome(
                heuristic_id=heuristic_id,
                event_id="",
                outcome="fail",
            )

        return affected
