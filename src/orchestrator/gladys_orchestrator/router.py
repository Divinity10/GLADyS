"""Event routing logic for the Orchestrator.

Routes events based on salience:
- HIGH salience → immediate to Executive (bypass moment accumulation)
- LOW salience → accumulate into current moment

Events are annotated with evaluated salience before routing so that
Executive receives events with salience already attached.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .accumulator import Moment
from .config import OrchestratorConfig
from .generated import common_pb2

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """A subscriber waiting for events."""

    subscriber_id: str
    queue: asyncio.Queue
    source_filters: list[str] | None = None
    event_types: list[str] | None = None


class EventRouter:
    """
    Routes events based on salience evaluation.

    Flow:
    1. Receive event from sensor/preprocessor
    2. Query Salience+Memory for salience score (via gRPC)
    3. If max(salience dimensions) > threshold → send immediately to Executive
    4. Otherwise → accumulate into current moment
    """

    def __init__(self, config: OrchestratorConfig, salience_client=None, executive_client=None):
        self.config = config
        self._subscribers: dict[str, Subscriber] = {}
        self._salience_client = salience_client
        self._executive_client = executive_client

    async def route_event(self, event: Any, accumulator: Any) -> dict:
        """
        Route a single event.

        Returns an EventAck dict.
        """
        event_id = getattr(event, "id", "unknown")

        try:
            # Step 1: Get salience score
            salience = await self._get_salience(event)

            # Step 2: Attach salience to event (so Executive receives it)
            self._attach_salience(event, salience)

            # Step 3: Determine routing based on salience
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

    def _attach_salience(self, event: Any, salience: dict) -> None:
        """
        Attach evaluated salience to an event.

        Events sent to Executive (via moment or immediate) should have
        salience already populated so Executive doesn't need to re-evaluate.

        Also attaches matched_heuristic_id for TD learning feedback correlation.
        """
        if not hasattr(event, "salience"):
            logger.warning(f"Event {getattr(event, 'id', 'unknown')} has no salience field")
            return

        # Check if the event's salience field supports proto CopyFrom
        if hasattr(event.salience, "CopyFrom"):
            # Create SalienceVector proto and populate it
            salience_vector = common_pb2.SalienceVector(
                threat=salience.get("threat", 0.0),
                opportunity=salience.get("opportunity", 0.0),
                humor=salience.get("humor", 0.0),
                novelty=salience.get("novelty", 0.0),
                goal_relevance=salience.get("goal_relevance", 0.0),
                social=salience.get("social", 0.0),
                emotional=salience.get("emotional", 0.0),
                actionability=salience.get("actionability", 0.0),
                habituation=salience.get("habituation", 0.0),
            )

            # Copy the salience vector into the event's salience field
            event.salience.CopyFrom(salience_vector)

            # Attach matched heuristic ID for TD learning (if present)
            matched_heuristic = salience.get("_matched_heuristic", "")
            if matched_heuristic and hasattr(event, "matched_heuristic_id"):
                event.matched_heuristic_id = matched_heuristic
        else:
            # Non-proto event (e.g., test mocks) - salience already attached or not applicable
            logger.debug(f"Event {getattr(event, 'id', 'unknown')} has non-proto salience, skipping attach")

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
        event_id = getattr(event, 'id', 'unknown')

        if self._executive_client:
            success = await self._executive_client.send_event_immediate(event)
            if success:
                logger.info(f"IMMEDIATE: Event {event_id} delivered to Executive")
            else:
                logger.warning(f"IMMEDIATE: Event {event_id} delivery failed")
        else:
            logger.info(f"IMMEDIATE: Event {event_id} (no Executive connected)")

        # Also broadcast to subscribers
        await self._broadcast_to_subscribers(event, immediate=True)

    async def send_moment_to_executive(self, moment: Moment) -> None:
        """Send accumulated moment to Executive on tick."""
        if not moment.events:
            return

        event_count = len(moment.events)

        if self._executive_client:
            success = await self._executive_client.send_moment(moment)
            if success:
                logger.info(f"MOMENT: {event_count} events delivered to Executive")
            else:
                logger.warning(f"MOMENT: {event_count} events delivery failed")
        else:
            logger.info(f"MOMENT: {event_count} events (no Executive connected)")

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
