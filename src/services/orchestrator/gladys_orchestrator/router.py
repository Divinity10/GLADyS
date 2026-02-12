"""Event routing logic for the Orchestrator.

Routes all events to Executive (§30 boundary change):
- Executive decides heuristic-vs-LLM based on suggestion context
- Orchestrator attaches salience + heuristic context but does not decide
- Exception: emergency fast-path (confidence >= 0.95 AND threat >= 0.9)

Events are annotated with evaluated salience before routing so that
Executive receives events with salience already attached.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from gladys_common import get_logger

from .config import OrchestratorConfig
from .generated import types_pb2
from .learning import LearningModule

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
    Routes events to Executive with heuristic context (§30 boundary change).

    Flow:
    1. Receive event from sensor/preprocessor
    2. Query Salience+Memory for salience score and heuristic match (via gRPC)
    3. Build heuristic suggestion context (if match found)
    4. Queue for Executive processing (Executive decides heuristic-vs-LLM)
    5. Exception: emergency fast-path for critical threats with high confidence
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        salience_client=None,
        executive_client=None,
        memory_client: Optional[Any] = None,
        learning_module: Optional[LearningModule] = None,
    ):
        self.config = config
        self._subscribers: dict[str, Subscriber] = {}
        self._response_subscribers: dict[str, ResponseSubscriber] = {}
        self._salience_client = salience_client
        self._executive_client = executive_client
        self._memory_client = memory_client
        self._learning_module = learning_module

    async def route_event(self, event: Any) -> dict:
        """
        Route a single event.

        Returns an EventAck dict with routing info and Executive response (if applicable).
        """
        event_id = getattr(event, "id", "unknown")

        try:
            # Step 0: Check if this event satisfies any pending outcome expectations
            # (Implicit feedback via LearningModule)
            if self._learning_module:
                resolved = await self._learning_module.check_event_for_outcomes(event)
                if resolved:
                    logger.info("Event satisfied outcome for heuristics", event_id=event_id, resolved=resolved)

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
                "_candidates": [],
            }

            # Step 4: Record heuristic fire via LearningModule
            # (Deferred to Step 5 after we have condition_text from heuristic lookup)

            # Step 5: Build heuristic context for Executive (§30 boundary change)
            # Orchestrator no longer decides heuristic-vs-LLM — Executive does.
            # All events are forwarded to Executive with heuristic context attached.
            heuristic_data = None
            if matched_heuristic_id and self._memory_client:
                heuristic = await self._memory_client.get_heuristic(matched_heuristic_id)
                if heuristic:
                    confidence = heuristic.get("confidence", 0.0)

                    action_text = self._extract_action_text(
                        heuristic.get("effects_json", "{}"),
                        matched_heuristic_id,
                    )

                    condition_text = heuristic.get("condition_text", "")

                    heuristic_data = {
                        "heuristic_id": matched_heuristic_id,
                        "suggested_action": action_text,
                        "confidence": confidence,
                        "condition_text": condition_text,
                    }

                    # Emergency fast-path: confidence >= 0.95 AND critical threat
                    # This is the only case where Orchestrator short-circuits Executive.
                    threat = salience.get("threat", 0.0)
                    if (confidence >= self.config.emergency_confidence_threshold
                            and threat >= self.config.emergency_threat_threshold):
                        logger.info(
                            "EMERGENCY_FASTPATH",
                            event_id=event_id,
                            heuristic_id=matched_heuristic_id,
                            confidence=round(confidence, 3),
                            threat=round(threat, 3),
                            thresholds={
                                "confidence": self.config.emergency_confidence_threshold,
                                "threat": self.config.emergency_threat_threshold,
                            },
                        )
                        result["response_text"] = action_text
                        result["prediction_confidence"] = confidence
                        result["predicted_success"] = confidence
                        result["queued"] = False

                        await self.broadcast_response({
                            "event_id": event_id,
                            "response_id": "",
                            "response_text": action_text,
                            "predicted_success": confidence,
                            "prediction_confidence": confidence,
                            "routing_path": "EMERGENCY",
                            "matched_heuristic_id": matched_heuristic_id,
                            "event_source": getattr(event, "source", ""),
                            "event_timestamp_ms": int(getattr(event, "timestamp", None) and event.timestamp.ToMilliseconds() or 0),
                            "response_timestamp_ms": int(time.time() * 1000),
                        })

                        if self._learning_module:
                            task = asyncio.create_task(
                                self._learning_module.on_fire(
                                    heuristic_id=matched_heuristic_id,
                                    event_id=event_id,
                                    condition_text=condition_text,
                                    predicted_success=confidence,
                                    source=getattr(event, "source", ""),
                                ),
                                name="learning_on_fire",
                            )
                            task.add_done_callback(_handle_task_exception)

                        await self._broadcast_to_subscribers(event)
                        return result

            if (
                self._memory_client
                and getattr(event, "raw_text", "")
                and self.config.max_evaluation_candidates > 0
            ):
                source_filter = getattr(event, "source", "") or ""
                best_match_id = (
                    heuristic_data.get("heuristic_id", "")
                    if heuristic_data
                    else matched_heuristic_id
                )
                matches = await self._memory_client.query_matching_heuristics(
                    event_text=getattr(event, "raw_text", ""),
                    min_confidence=0.0,
                    limit=self.config.max_evaluation_candidates + 1,
                    source_filter=source_filter,
                )

                filtered_with_similarity: list[dict] = []
                for match in matches:
                    heuristic_id = match.get("heuristic_id", "")
                    if heuristic_id and heuristic_id == best_match_id:
                        continue

                    confidence = float(match.get("confidence", 0.0) or 0.0)
                    if confidence >= self.config.heuristic_confidence_threshold:
                        continue

                    filtered_with_similarity.append({
                        "heuristic_id": heuristic_id,
                        "suggested_action": self._extract_action_text(
                            match.get("effects_json", "{}"),
                            heuristic_id,
                        ),
                        "confidence": confidence,
                        "condition_text": match.get("condition_text", ""),
                        "_similarity": float(match.get("similarity", 0.0) or 0.0),
                    })

                filtered_with_similarity.sort(
                    key=lambda candidate: candidate.get("_similarity", 0.0),
                    reverse=True,
                )

                candidates: list[dict] = []
                for candidate in filtered_with_similarity[: self.config.max_evaluation_candidates]:
                    candidates.append({
                        "heuristic_id": candidate.get("heuristic_id", ""),
                        "suggested_action": candidate.get("suggested_action", ""),
                        "confidence": candidate.get("confidence", 0.0),
                        "condition_text": candidate.get("condition_text", ""),
                    })
                result["_candidates"] = candidates

            # Step 6: Always queue for Executive (§30)
            # Executive decides heuristic-vs-LLM based on suggestion context.
            logger.info(
                "ROUTE_TO_EXECUTIVE",
                event_id=event_id,
                salience=round(max_salience, 2),
                has_suggestion=heuristic_data is not None,
                candidate_count=len(result.get("_candidates", [])),
            )
            result["queued"] = True
            result["_salience"] = max_salience

            if heuristic_data:
                result["_suggestion"] = heuristic_data
                logger.info(
                    "SUGGESTION_CONTEXT",
                    event_id=event_id,
                    heuristic_id=heuristic_data["heuristic_id"],
                    confidence=round(heuristic_data["confidence"], 3),
                )

            # Register heuristic fire via LearningModule
            if matched_heuristic_id and self._learning_module:
                condition_text_for_fire = ""
                if heuristic_data:
                    condition_text_for_fire = heuristic_data.get("condition_text", "")
                task = asyncio.create_task(
                    self._learning_module.on_fire(
                        heuristic_id=matched_heuristic_id,
                        event_id=event_id,
                        condition_text=condition_text_for_fire,
                        predicted_success=result.get("predicted_success", 0.0),
                        source=getattr(event, "source", ""),
                    ),
                    name="learning_on_fire",
                )
                task.add_done_callback(_handle_task_exception)

            await self._broadcast_to_subscribers(event)
            return result

        except Exception as e:
            logger.error("Error routing event", event_id=event_id, error=str(e))
            return {"event_id": event_id, "accepted": False, "error_message": str(e)}

    def _extract_action_text(self, effects_json: Any, heuristic_id: str) -> str:
        """Extract suggested action text from a heuristic effects payload."""
        action_text = ""
        try:
            action = json.loads(effects_json) if isinstance(effects_json, str) else effects_json
            if isinstance(action, dict):
                action_text = action.get("message") or action.get("text") or action.get("response") or ""
        except json.JSONDecodeError:
            logger.warning("Failed to parse effects_json", heuristic_id=heuristic_id)
        return action_text

    def _has_explicit_salience(self, event: Any) -> bool:
        """Check if event has explicitly-set salience values (for testing/override)."""
        if not hasattr(event, "salience") or not event.salience:
            return False
        s = event.salience
        threat = getattr(s, "threat", 0.0)
        salience_score = getattr(s, "salience", 0.0)
        habituation = getattr(s, "habituation", 0.0)
        vector = getattr(s, "vector", None)
        return (threat > 0.0 or salience_score > 0.0 or habituation > 0.0 or bool(vector))

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
            logger.debug("Using explicit salience from event", event_id=getattr(event, "id", "unknown"))
            vector = dict(getattr(event.salience, "vector", {}))
            if not vector:
                for dim in ("novelty", "goal_relevance", "opportunity", "actionability", "social"):
                    if hasattr(event.salience, dim):
                        vector[dim] = float(getattr(event.salience, dim))
            return {
                "threat": event.salience.threat,
                "salience": getattr(event.salience, "salience", 0.0),
                "habituation": event.salience.habituation,
                "vector": vector,
                "model_id": getattr(event.salience, "model_id", ""),
            }

        # If salience client is available, use it
        if self._salience_client:
            return await self._salience_client.evaluate_salience(event)

        # Fallback: use event's existing salience if present (shouldn't reach here normally)
        if hasattr(event, "salience") and event.salience:
            vector = dict(getattr(event.salience, "vector", {}))
            if not vector:
                for dim in ("novelty", "goal_relevance", "opportunity", "actionability", "social"):
                    if hasattr(event.salience, dim):
                        vector[dim] = float(getattr(event.salience, dim))
            return {
                "threat": event.salience.threat,
                "salience": getattr(event.salience, "salience", 0.0),
                "habituation": event.salience.habituation,
                "vector": vector,
                "model_id": getattr(event.salience, "model_id", ""),
            }

        logger.debug("No salience service available, defaulting to neutral salience values")
        return self._default_salience()

    def _default_salience(self) -> dict:
        """Default neutral salience values when service unavailable."""
        return {
            "threat": 0.5,
            "salience": 0.5,
            "habituation": 0.5,
            "vector": {
                "novelty": 0.5,
                "goal_relevance": 0.5,
                "opportunity": 0.5,
                "actionability": 0.5,
                "social": 0.5,
            },
        }

    def _attach_salience(self, event: Any, salience: dict) -> None:
        """
        Attach evaluated salience to an event.

        Events sent to Executive should have salience already populated so
        Executive doesn't need to re-evaluate.

        Also attaches matched_heuristic_id for feedback correlation.
        """
        if not hasattr(event, "salience"):
            logger.warning("Event has no salience field", event_id=getattr(event, "id", "unknown"))
            return

        # Check if the event's salience field supports proto CopyFrom
        if hasattr(event.salience, "CopyFrom"):
            def _as_float(value: Any) -> float:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0

            salience_result = types_pb2.SalienceResult(
                threat=_as_float(salience.get("threat", 0.0)),
                salience=_as_float(salience.get("salience", 0.0)),
                habituation=_as_float(salience.get("habituation", 0.0)),
                model_id=salience.get("model_id", "") or "",
            )

            vector = salience.get("vector")
            if isinstance(vector, dict):
                for dim, value in vector.items():
                    if dim in {"novelty", "goal_relevance", "opportunity", "actionability", "social"}:
                        salience_result.vector[dim] = _as_float(value)
            else:
                for dim in ("novelty", "goal_relevance", "opportunity", "actionability", "social"):
                    if dim in salience:
                        salience_result.vector[dim] = _as_float(salience.get(dim))

            event.salience.CopyFrom(salience_result)

            # Attach matched heuristic ID for TD learning (if present)
            matched_heuristic = salience.get("_matched_heuristic", "")
            if matched_heuristic and hasattr(event, "matched_heuristic_id"):
                event.matched_heuristic_id = matched_heuristic
        else:
            # Non-proto event (e.g., test mocks) - salience already attached or not applicable
            logger.debug("Event has non-proto salience, skipping attach", event_id=getattr(event, "id", "unknown"))

    def _get_max_salience(self, salience: dict) -> float:
        """Get scalar salience for routing priority."""
        try:
            salience_score = float(salience.get("salience", 0.0))
        except (TypeError, ValueError):
            salience_score = 0.0

        try:
            threat = float(salience.get("threat", 0.0))
        except (TypeError, ValueError):
            threat = 0.0

        if salience_score == 0.0 and threat > 0.0:
            return threat
        return salience_score

    async def _send_immediate(
        self,
        event: Any,
        suggestion: dict | None = None,
        candidates: list[dict] | None = None,
    ) -> dict | None:
        """
        Send event immediately to Executive for LLM processing.

        Args:
            event: The event to process
            suggestion: Optional suggestion context from low-conf heuristic (Scenario 2)

        Returns the Executive response dict, or None if no Executive connected.
        """
        event_id = getattr(event, 'id', 'unknown')

        if self._executive_client:
            response = await self._executive_client.send_event_immediate(
                event,
                suggestion=suggestion,
                candidates=candidates,
            )
            if response.get("accepted"):
                logger.info("IMMEDIATE: Event delivered to Executive", event_id=event_id)
            else:
                logger.warning("IMMEDIATE: Event delivery failed", event_id=event_id, error=response.get("error_message"))
            return response
        else:
            logger.info("IMMEDIATE: No Executive connected", event_id=event_id)
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
                logger.warning("Subscriber queue full, dropping event", subscriber_id=subscriber.subscriber_id)

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
        logger.info("Response subscriber added", subscriber_id=subscriber_id)
        return queue

    def remove_response_subscriber(self, subscriber_id: str) -> None:
        """Remove a response subscriber."""
        self._response_subscribers.pop(subscriber_id, None)
        logger.info("Response subscriber removed", subscriber_id=subscriber_id)

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
            "Broadcasting response",
            event_id=event_id,
            routing_path=routing_path,
            subscriber_count=subscriber_count,
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
                logger.debug("Delivered response to subscriber", event_id=event_id, subscriber_id=subscriber.subscriber_id)
            except asyncio.QueueFull:
                logger.warning("Response subscriber queue full, dropping response", subscriber_id=subscriber.subscriber_id)
