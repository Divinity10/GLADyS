"""Event routing logic for the Orchestrator.

Routes events based on heuristic confidence and salience:
- High-conf heuristic match → return cached action immediately
- Otherwise → queue for async LLM processing (priority by salience)

Events are annotated with evaluated salience before routing so that
Executive receives events with salience already attached.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from gladys_common import get_logger

from .config import OrchestratorConfig
from .generated import types_pb2
from .outcome_watcher import OutcomeWatcher

logger = get_logger(__name__)


def _handle_task_exception(task: asyncio.Task) -> None:
    """Log exceptions from fire-and-forget tasks."""
    try:
        exc = task.exception()
        if exc is not None:
            logger.error(
                "background_task_failed",
                task_name=task.get_name(),
                error=str(exc),
                error_type=type(exc).__name__,
            )
    except asyncio.CancelledError:
        pass  # Task was cancelled, not an error


@dataclass
class Subscriber:
    """A subscriber waiting for events."""

    subscriber_id: str
    queue: asyncio.Queue
    source_filters: list[str] | None = None
    event_types: list[str] | None = None


@dataclass
class ResponseSubscriber:
    """A subscriber waiting for responses (for evaluation UI)."""

    subscriber_id: str
    queue: asyncio.Queue
    source_filters: list[str] | None = None
    include_immediate: bool = False  # Also receive IMMEDIATE path responses


class EventRouter:
    """
    Routes events based on heuristic confidence and salience.

    Flow:
    1. Receive event from sensor/preprocessor
    2. Query Salience+Memory for salience score and heuristic match (via gRPC)
    3. If high-conf heuristic match (>= threshold) → return action immediately
    4. Otherwise → queue for async LLM processing (priority by salience)
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        salience_client=None,
        executive_client=None,
        memory_client: Optional[Any] = None,
        outcome_watcher: Optional[OutcomeWatcher] = None,
    ):
        self.config = config
        self._subscribers: dict[str, Subscriber] = {}
        self._response_subscribers: dict[str, ResponseSubscriber] = {}
        self._salience_client = salience_client
        self._executive_client = executive_client
        self._memory_client = memory_client
        self._outcome_watcher = outcome_watcher

    async def route_event(self, event: Any) -> dict:
        """
        Route a single event.

        Returns an EventAck dict with routing info and Executive response (if applicable).
        """
        event_id = getattr(event, "id", "unknown")

        try:
            # Step 0: Check if this event satisfies any pending outcome expectations
            # (Implicit feedback - Phase 2)
            if self._outcome_watcher:
                resolved = await self._outcome_watcher.check_event(event)
                if resolved:
                    logger.info(f"Event {event_id} satisfied outcome for heuristics: {resolved}")

            # Step 1: Get salience score
            salience = await self._get_salience(event)
            matched_heuristic_id = salience.get("_matched_heuristic", "")

            # Step 2: Attach salience to event (so Executive receives it)
            self._attach_salience(event, salience)

            # Step 3: Determine routing based on salience
            max_salience = self._get_max_salience(salience)

            # Base result
            result = {
                "event_id": event_id,
                "accepted": True,
                "error_message": "",
                "routed_to_llm": False,
                "matched_heuristic_id": matched_heuristic_id,
                "response_id": "",
                "response_text": "",
                "predicted_success": 0.0,
                "prediction_confidence": 0.0,
                "queued": False,  # True if event was queued for async processing
            }

            # Step 4: Record heuristic fire (Flight Recorder)
            if matched_heuristic_id and self._memory_client:
                logger.info(f"Recording heuristic fire: heuristic={matched_heuristic_id}, event={event_id}")
                # fire-and-forget, don't block the response
                task = asyncio.create_task(
                    self._memory_client.record_heuristic_fire(
                        heuristic_id=matched_heuristic_id,
                        event_id=event_id,
                        episodic_event_id=""  # Episodic event not yet stored at fire time
                    ),
                    name="record_heuristic_fire"
                )
                task.add_done_callback(_handle_task_exception)
            elif matched_heuristic_id:
                logger.warning(f"Cannot record fire: memory_client is None (heuristic={matched_heuristic_id})")

            # Step 5: Check for high-confidence heuristic shortcut (System 1 fast path)
            # If matched heuristic has confidence >= threshold, return action immediately
            # without calling LLM. This is the "learned response" path.
            # If confidence < threshold, pass suggestion context for LLM consideration (Scenario 2).
            heuristic_data = None  # Store for potential low-conf suggestion
            if matched_heuristic_id and self._memory_client:
                heuristic = await self._memory_client.get_heuristic(matched_heuristic_id)
                if heuristic:
                    confidence = heuristic.get("confidence", 0.0)

                    # Extract action message and condition for suggestion context
                    action_text = ""
                    effects_json = heuristic.get("effects_json", "{}")
                    try:
                        action = json.loads(effects_json) if isinstance(effects_json, str) else effects_json
                        action_text = action.get("message") or action.get("text") or action.get("response") or ""
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse effects_json for heuristic {matched_heuristic_id}")

                    condition_text = heuristic.get("condition_text", "")

                    # Store for potential low-conf suggestion (used if we don't return early)
                    heuristic_data = {
                        "heuristic_id": matched_heuristic_id,
                        "suggested_action": action_text,
                        "confidence": confidence,
                        "condition_text": condition_text,
                    }

                    if confidence >= self.config.heuristic_confidence_threshold:
                        # High-confidence heuristic - use cached action
                        logger.info(
                            f"HEURISTIC_SHORTCUT: event={event_id}, "
                            f"heuristic={matched_heuristic_id}, confidence={confidence:.3f}"
                        )

                        result["response_text"] = action_text
                        result["prediction_confidence"] = confidence
                        result["predicted_success"] = confidence  # Use confidence as prediction
                        result["queued"] = False

                        # Broadcast response to subscribers
                        await self.broadcast_response({
                            "event_id": event_id,
                            "response_id": "",
                            "response_text": action_text,
                            "predicted_success": confidence,
                            "prediction_confidence": confidence,
                            "routing_path": "HEURISTIC",
                            "matched_heuristic_id": matched_heuristic_id,
                            "event_source": getattr(event, "source", ""),
                            "event_timestamp_ms": int(getattr(event, "timestamp", None) and event.timestamp.ToMilliseconds() or 0),
                            "response_timestamp_ms": int(time.time() * 1000),
                        })

                        # Register for outcome tracking
                        if self._outcome_watcher:
                            await self._outcome_watcher.register_fire(
                                heuristic_id=matched_heuristic_id,
                                event_id=event_id,
                                predicted_success=confidence,
                            )

                        # Broadcast to event subscribers
                        await self._broadcast_to_subscribers(event)

                        return result

            # Step 6: Queue for async processing (no high-conf heuristic matched)
            # Events are processed by salience priority (higher = sooner)
            logger.debug(f"Event {event_id}: salience={max_salience:.2f} → queue for async processing")
            result["queued"] = True
            result["_salience"] = max_salience  # For server to use when enqueuing

            # Pass suggestion context for low-conf heuristic matches (Scenario 2)
            # LLM will see the pattern suggestion even though confidence is below threshold
            if heuristic_data:
                result["_suggestion"] = heuristic_data
                logger.info(
                    f"LOW_CONF_SUGGESTION: event={event_id}, "
                    f"heuristic={heuristic_data['heuristic_id']}, confidence={heuristic_data['confidence']:.3f}"
                )

            # Step 4: Register heuristic fire for outcome tracking (if applicable)
            if matched_heuristic_id and self._outcome_watcher:
                await self._outcome_watcher.register_fire(
                    heuristic_id=matched_heuristic_id,
                    event_id=event_id,
                    predicted_success=result.get("predicted_success", 0.0),
                )

            # Also broadcast to subscribers (for monitoring, etc.)
            await self._broadcast_to_subscribers(event)

            return result

        except Exception as e:
            logger.error(f"Error routing event {event_id}: {e}")
            return {"event_id": event_id, "accepted": False, "error_message": str(e)}

    def _has_explicit_salience(self, event: Any) -> bool:
        """Check if event has explicitly-set salience values (for testing/override)."""
        if not hasattr(event, "salience") or not event.salience:
            return False
        s = event.salience
        # Check if any salience dimension is non-zero
        return any([
            s.threat, s.opportunity, s.humor, s.novelty, s.goal_relevance,
            s.social, s.emotional, s.actionability, s.habituation
        ])

    async def _get_salience(self, event: Any) -> dict:
        """
        Query Salience+Memory for salience evaluation.

        This is where we call the "amygdala" (Salience+Memory shared process).
        Falls back to default salience if service unavailable (graceful degradation).

        If the event has explicit salience values set, use those instead
        (allows UI/tests to override salience for evaluation).
        """
        # First check: if event has explicit salience, use it (override for testing)
        if self._has_explicit_salience(event):
            logger.debug(f"Event {getattr(event, 'id', 'unknown')}: Using explicit salience from event")
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

        # If salience client is available, use it
        if self._salience_client:
            return await self._salience_client.evaluate_salience(event)

        # Fallback: use event's existing salience if present (shouldn't reach here normally)
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

        # Default: HIGH salience when no service available
        # If we can't evaluate salience, err on side of responsiveness (immediate routing)
        # rather than accumulation (delayed/no response for interactive use cases)
        logger.debug("No salience service available, defaulting to HIGH salience for immediate routing")
        return self._default_salience()

    def _default_salience(self) -> dict:
        """Default salience values when service unavailable.

        Defaults to HIGH salience (above threshold) to ensure immediate routing.
        If we can't evaluate salience, it's better to be responsive than to
        accumulate events that may need immediate attention.
        """
        return {
            "threat": 0.0,
            "opportunity": 0.0,
            "humor": 0.0,
            "novelty": 0.8,  # High enough to trigger immediate routing (threshold is 0.7)
            "goal_relevance": 0.0,
            "social": 0.0,
            "emotional": 0.0,
            "actionability": 0.0,
            "habituation": 0.0,
        }

    def _attach_salience(self, event: Any, salience: dict) -> None:
        """
        Attach evaluated salience to an event.

        Events sent to Executive should have salience already populated so
        Executive doesn't need to re-evaluate.

        Also attaches matched_heuristic_id for feedback correlation.
        """
        if not hasattr(event, "salience"):
            logger.warning(f"Event {getattr(event, 'id', 'unknown')} has no salience field")
            return

        # Check if the event's salience field supports proto CopyFrom
        if hasattr(event.salience, "CopyFrom"):
            # Create SalienceVector proto and populate it
            salience_vector = types_pb2.SalienceVector(
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

    async def _send_immediate(self, event: Any, suggestion: dict | None = None) -> dict | None:
        """
        Send event immediately to Executive for LLM processing.

        Args:
            event: The event to process
            suggestion: Optional suggestion context from low-conf heuristic (Scenario 2)

        Returns the Executive response dict, or None if no Executive connected.
        """
        event_id = getattr(event, 'id', 'unknown')

        if self._executive_client:
            response = await self._executive_client.send_event_immediate(event, suggestion=suggestion)
            if response.get("accepted"):
                logger.info(f"IMMEDIATE: Event {event_id} delivered to Executive")
            else:
                logger.warning(f"IMMEDIATE: Event {event_id} delivery failed: {response.get('error_message')}")
            return response
        else:
            logger.info(f"IMMEDIATE: Event {event_id} (no Executive connected)")
            return None

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

    # -------------------------------------------------------------------------
    # Response Subscriber Management (for evaluation UI)
    # -------------------------------------------------------------------------

    def add_response_subscriber(
        self,
        subscriber_id: str,
        source_filters: list[str] | None = None,
        include_immediate: bool = False,
    ) -> asyncio.Queue:
        """Add a response subscriber and return their queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._response_subscribers[subscriber_id] = ResponseSubscriber(
            subscriber_id=subscriber_id,
            queue=queue,
            source_filters=source_filters,
            include_immediate=include_immediate,
        )
        logger.info(f"Response subscriber added: {subscriber_id}")
        return queue

    def remove_response_subscriber(self, subscriber_id: str) -> None:
        """Remove a response subscriber."""
        self._response_subscribers.pop(subscriber_id, None)
        logger.info(f"Response subscriber removed: {subscriber_id}")

    async def broadcast_response(self, response: dict) -> None:
        """
        Broadcast a response to all matching response subscribers.

        Response dict should contain:
        - event_id: str
        - response_id: str
        - response_text: str
        - predicted_success: float
        - prediction_confidence: float
        - routing_path: str ("IMMEDIATE", "HEURISTIC", or "QUEUED")
        - matched_heuristic_id: str
        - event_source: str (for filtering)
        """
        event_source = response.get("event_source", "")
        routing_path = response.get("routing_path", "")
        event_id = response.get("event_id", "")

        subscriber_count = len(self._response_subscribers)
        logger.info(
            f"broadcast_response: event_id={event_id}, routing_path={routing_path}, "
            f"subscriber_count={subscriber_count}"
        )

        for subscriber in list(self._response_subscribers.values()):
            # Skip IMMEDIATE responses if subscriber doesn't want them
            if routing_path == "IMMEDIATE" and not subscriber.include_immediate:
                continue

            # Check source filter
            if subscriber.source_filters:
                if event_source not in subscriber.source_filters:
                    continue

            try:
                subscriber.queue.put_nowait(response)
                logger.debug(
                    f"Delivered response {event_id} to subscriber {subscriber.subscriber_id}"
                )
            except asyncio.QueueFull:
                logger.warning(f"Response subscriber {subscriber.subscriber_id} queue full, dropping response")
