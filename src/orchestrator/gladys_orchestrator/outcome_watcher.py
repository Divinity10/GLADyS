"""Outcome Watcher - Implicit feedback via observed consequences.

Watches for "outcomes" of heuristic-triggered actions. When a heuristic fires
and the expected outcome event arrives, automatically triggers positive feedback.

This is the "Outcome Evaluator" from Phase 2 of the Learning Closure Plan.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OutcomePattern:
    """Configuration for an expected outcome pattern.

    When a heuristic fires whose condition_text contains `trigger_pattern`,
    watch for an event whose raw_text contains `outcome_pattern` within
    `timeout_sec` seconds.
    """

    trigger_pattern: str  # Substring match on heuristic condition_text
    outcome_pattern: str  # Substring match on outcome event raw_text
    timeout_sec: int = 120  # How long to wait for outcome
    is_success: bool = True  # True = outcome means success, False = failure


@dataclass
class PendingOutcome:
    """A pending outcome expectation from a heuristic fire."""

    heuristic_id: str
    event_id: str  # The event that triggered the heuristic
    trigger_pattern: str  # What pattern matched
    expected_pattern: str  # What outcome we're waiting for
    fire_time: datetime
    timeout_at: datetime
    predicted_success: float = 0.0  # From LLM, for TD learning
    is_success_outcome: bool = True  # Does matching mean success?


class OutcomeWatcher:
    """
    Watches for implicit feedback via observed consequences.

    Usage:
        watcher = OutcomeWatcher(patterns, memory_client)

        # When a heuristic fires:
        await watcher.register_fire(heuristic_id, event_id, predicted_success)

        # When any event arrives:
        await watcher.check_event(event)

        # Periodically clean up expired expectations:
        watcher.cleanup_expired()
    """

    def __init__(
        self,
        patterns: list[OutcomePattern],
        memory_client: Any = None,
    ):
        """
        Initialize the outcome watcher.

        Args:
            patterns: List of outcome patterns to watch for
            memory_client: gRPC client for calling UpdateHeuristicConfidence
                          and GetHeuristic (for fetching condition_text)
        """
        self.patterns = patterns
        self._memory_client = memory_client
        self._pending: list[PendingOutcome] = []
        self._lock = asyncio.Lock()
        # Cache heuristic condition_text to avoid repeated lookups
        self._condition_text_cache: dict[str, str] = {}

    async def _get_condition_text(self, heuristic_id: str) -> str:
        """Get condition_text for a heuristic, with caching."""
        if heuristic_id in self._condition_text_cache:
            return self._condition_text_cache[heuristic_id]

        if not self._memory_client:
            return ""

        try:
            heuristic = await self._memory_client.get_heuristic(heuristic_id)
            if heuristic:
                condition_text = heuristic.get("condition_text", "")
                self._condition_text_cache[heuristic_id] = condition_text
                return condition_text
        except Exception as e:
            logger.warning(f"OutcomeWatcher: Failed to fetch heuristic {heuristic_id}: {e}")

        return ""

    async def register_fire(
        self,
        heuristic_id: str,
        event_id: str,
        predicted_success: float = 0.0,
        condition_text: str = "",
    ) -> bool:
        """
        Register that a heuristic fired, potentially creating an outcome expectation.

        Args:
            heuristic_id: The ID of the heuristic that fired
            event_id: The event that triggered the heuristic
            predicted_success: LLM's prediction (for TD learning)
            condition_text: Optional - if not provided, will be fetched from memory

        Returns True if an expectation was created, False otherwise.
        """
        if not heuristic_id:
            return False

        # Get condition_text if not provided
        if not condition_text:
            condition_text = await self._get_condition_text(heuristic_id)
            if not condition_text:
                logger.debug(f"OutcomeWatcher: No condition_text for heuristic {heuristic_id}")
                return False

        # Find matching pattern
        for pattern in self.patterns:
            if pattern.trigger_pattern.lower() in condition_text.lower():
                now = datetime.utcnow()
                pending = PendingOutcome(
                    heuristic_id=heuristic_id,
                    event_id=event_id,
                    trigger_pattern=pattern.trigger_pattern,
                    expected_pattern=pattern.outcome_pattern,
                    fire_time=now,
                    timeout_at=now + timedelta(seconds=pattern.timeout_sec),
                    predicted_success=predicted_success,
                    is_success_outcome=pattern.is_success,
                )
                self._pending.append(pending)
                logger.info(
                    f"OutcomeWatcher: Registered expectation for heuristic {heuristic_id}: "
                    f"waiting for '{pattern.outcome_pattern}' within {pattern.timeout_sec}s"
                )
                return True

        return False

    async def check_event(self, event: Any) -> list[str]:
        """
        Check if an incoming event satisfies any pending outcome expectations.

        Returns list of heuristic IDs that received implicit feedback.
        """
        raw_text = getattr(event, "raw_text", "") or ""
        if not raw_text:
            return []

        raw_text_lower = raw_text.lower()
        resolved_heuristics = []

        async with self._lock:
            # Find matching pending outcomes
            matched = []
            remaining = []

            for pending in self._pending:
                if pending.expected_pattern.lower() in raw_text_lower:
                    matched.append(pending)
                else:
                    remaining.append(pending)

            self._pending = remaining

        # Send feedback for matched outcomes
        for pending in matched:
            success = await self._send_feedback(pending)
            if success:
                resolved_heuristics.append(pending.heuristic_id)

        return resolved_heuristics

    async def _send_feedback(self, pending: PendingOutcome) -> bool:
        """Send implicit feedback for a resolved outcome."""
        positive = pending.is_success_outcome

        elapsed = (datetime.utcnow() - pending.fire_time).total_seconds()
        logger.info(
            f"OutcomeWatcher: Outcome detected for heuristic {pending.heuristic_id} "
            f"after {elapsed:.1f}s. Sending {'positive' if positive else 'negative'} "
            f"implicit feedback."
        )

        if not self._memory_client:
            logger.warning("OutcomeWatcher: No memory client configured, skipping feedback")
            return False

        try:
            result = await self._memory_client.update_heuristic_confidence(
                heuristic_id=pending.heuristic_id,
                positive=positive,
                predicted_success=pending.predicted_success,
                feedback_source="implicit",  # Mark as implicit feedback
            )
            if result.get("success"):
                logger.info(
                    f"OutcomeWatcher: Confidence updated for {pending.heuristic_id}: "
                    f"{result.get('old_confidence', 0):.2f} → {result.get('new_confidence', 0):.2f} "
                    f"(delta={result.get('delta', 0):.3f}, td_error={result.get('td_error', 0):.3f})"
                )
                return True
            else:
                logger.error(
                    f"OutcomeWatcher: Failed to update confidence: {result.get('error')}"
                )
                return False
        except Exception as e:
            logger.error(f"OutcomeWatcher: Error sending feedback: {e}")
            return False

    def cleanup_expired(self) -> int:
        """
        Remove expired pending outcomes.

        Returns count of expired expectations removed.
        """
        now = datetime.utcnow()
        expired = [p for p in self._pending if p.timeout_at < now]
        self._pending = [p for p in self._pending if p.timeout_at >= now]

        for p in expired:
            logger.debug(
                f"OutcomeWatcher: Expectation expired for heuristic {p.heuristic_id} "
                f"(waited for '{p.expected_pattern}')"
            )

        return len(expired)

    @property
    def pending_count(self) -> int:
        """Number of pending outcome expectations."""
        return len(self._pending)
