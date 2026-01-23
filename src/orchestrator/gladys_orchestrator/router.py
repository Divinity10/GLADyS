"""Event routing logic for the Orchestrator.

Routes events based on salience:
- HIGH salience → immediate to Executive (bypass moment accumulation)
- LOW salience → accumulate into current moment
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import OrchestratorConfig

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """A subscriber waiting for events."""

    subscriber_id: str
    queue: asyncio.Queue
    source_filters: list[str] | None = None
    event_types: list[str] | None = None


@dataclass
class Moment:
    """A collection of events accumulated within a time window."""

    events: list[Any] = field(default_factory=list)
    start_time_ms: int = 0
    end_time_ms: int = 0


class EventRouter:
    """
    Routes events based on salience evaluation.

    Flow:
    1. Receive event from sensor/preprocessor
    2. Query Salience+Memory for salience score (via gRPC)
    3. If max(salience dimensions) > threshold → send immediately to Executive
    4. Otherwise → accumulate into current moment
    """

    def __init__(self, config: OrchestratorConfig, salience_client=None):
        self.config = config
        self._subscribers: dict[str, Subscriber] = {}
        self._salience_client = salience_client

    async def route_event(self, event: Any, accumulator: Any) -> dict:
        """
        Route a single event.

        Returns an EventAck dict.
        """
        event_id = getattr(event, "id", "unknown")

        try:
            # Step 1: Get salience score
            salience = await self._get_salience(event)

            # Step 2: Determine routing based on salience
            max_salience = self._get_max_salience(salience)

            if max_salience >= self.config.high_salience_threshold:
                # HIGH salience → immediate to Executive
                logger.debug(f"Event {event_id}: HIGH salience ({max_salience:.2f}) → immediate")
                await self._send_immediate(event)
            else:
                # LOW salience → accumulate
                logger.debug(f"Event {event_id}: LOW salience ({max_salience:.2f}) → accumulate")
                accumulator.add_event(event)

            # Also broadcast to subscribers (for monitoring, etc.)
            await self._broadcast_to_subscribers(event)

            return {"event_id": event_id, "accepted": True, "error_message": ""}

        except Exception as e:
            logger.error(f"Error routing event {event_id}: {e}")
            return {"event_id": event_id, "accepted": False, "error_message": str(e)}

    async def _get_salience(self, event: Any) -> dict:
        """
        Query Salience+Memory for salience evaluation.

        This is where we call the "amygdala" (Salience+Memory shared process).
        Falls back to default salience if service unavailable (graceful degradation).
        """
        # If salience client is available, use it
        if self._salience_client:
            return await self._salience_client.evaluate_salience(event)

        # Fallback: use event's existing salience if present
        if hasattr(event, "salience") and event.salience:
            return {
                "threat": event.salience.threat,
                "opportunity": event.salience.opportunity,
                "humor": event.salience.humor,
                "novelty": event.salience.novelty,
                "goal_relevance": event.salience.goal_relevance,
                "social": event.salience.social,
                "emotional": event.salience.emotional,
                "actionability": event.salience.actionability,
                "habituation": event.salience.habituation,
            }

        # Default: low salience (will be accumulated into moment)
        logger.debug("No salience service available, using default low salience")
        return self._default_salience()

    def _default_salience(self) -> dict:
        """Default salience values when service unavailable."""
        return {
            "threat": 0.0,
            "opportunity": 0.0,
            "humor": 0.0,
            "novelty": 0.1,  # Slight novelty for new events
            "goal_relevance": 0.0,
            "social": 0.0,
            "emotional": 0.0,
            "actionability": 0.0,
            "habituation": 0.0,
        }

    def _get_max_salience(self, salience: dict) -> float:
        """Get the maximum salience dimension value."""
        # Exclude habituation from max calculation (it's a modifier, not a trigger)
        dimensions = [
            salience.get("threat", 0),
            salience.get("opportunity", 0),
            salience.get("humor", 0),
            salience.get("novelty", 0),
            salience.get("goal_relevance", 0),
            salience.get("social", 0),
            abs(salience.get("emotional", 0)),  # emotional is -1 to 1
            salience.get("actionability", 0),
        ]
        return max(dimensions)

    async def _send_immediate(self, event: Any) -> None:
        """Send event immediately to Executive (bypass moment accumulation)."""
        # TODO: Implement gRPC call to Executive
        # For now, just broadcast to subscribers with "immediate" flag
        logger.info(f"IMMEDIATE: Event {getattr(event, 'id', 'unknown')} sent to Executive")
        await self._broadcast_to_subscribers(event, immediate=True)

    async def send_moment_to_executive(self, moment: Moment) -> None:
        """Send accumulated moment to Executive on tick."""
        if not moment.events:
            return

        # TODO: Implement gRPC call to Executive
        logger.info(f"MOMENT: Sending {len(moment.events)} events to Executive")

        # Also notify subscribers
        for event in moment.events:
            await self._broadcast_to_subscribers(event)

    async def _broadcast_to_subscribers(self, event: Any, immediate: bool = False) -> None:
        """Broadcast event to all matching subscribers."""
        event_source = getattr(event, "source", None)

        for subscriber in list(self._subscribers.values()):
            # Check source filter
            if subscriber.source_filters:
                if event_source not in subscriber.source_filters:
                    continue

            # TODO: Check event type filter

            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Subscriber {subscriber.subscriber_id} queue full, dropping event")

    def add_subscriber(
        self,
        subscriber_id: str,
        source_filters: list[str] | None = None,
        event_types: list[str] | None = None,
    ) -> asyncio.Queue:
        """Add a new subscriber and return their event queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[subscriber_id] = Subscriber(
            subscriber_id=subscriber_id,
            queue=queue,
            source_filters=source_filters,
            event_types=event_types,
        )
        return queue

    def remove_subscriber(self, subscriber_id: str) -> None:
        """Remove a subscriber."""
        self._subscribers.pop(subscriber_id, None)
