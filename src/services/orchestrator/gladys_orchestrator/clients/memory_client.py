"""gRPC client for MemoryStorage service.

This client stores episodic events in the Memory subsystem.
"""

import time
from typing import Any

import grpc

from gladys_common import get_logger

from ..generated import memory_pb2
from ..generated import memory_pb2_grpc

logger = get_logger(__name__)


class MemoryStorageClient:
    """
    Client for the MemoryStorage service.

    Used by Orchestrator to persist events after routing.
    """

    def __init__(self, address: str):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: memory_pb2_grpc.MemoryStorageStub | None = None

    async def connect(self) -> None:
        """Establish connection to MemoryStorage service."""
        self._channel = grpc.aio.insecure_channel(self.address)
        self._stub = memory_pb2_grpc.MemoryStorageStub(self._channel)
        logger.info("Connected to MemoryStorage", address=self.address)

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def store_event(
        self,
        event: Any,
        response_id: str = "",
        response_text: str = "",
        predicted_success: float = 0.0,
        prediction_confidence: float = 0.0,
        prompt_text: str = "",
        decision_path: str = "",
        matched_heuristic_id: str = "",
    ) -> bool:
        """
        Store a single episodic event.

        Args:
            event: The event proto (common_pb2.Event)
            response_id: Executive's response ID (if routed to LLM)
            response_text: The actual LLM response (for fine-tuning)
            predicted_success: LLM's prediction (if routed to LLM)
            prediction_confidence: LLM's confidence (if routed to LLM)
            prompt_text: Full LLM prompt (empty for heuristic fast-path)
            decision_path: "heuristic" or "llm"
            matched_heuristic_id: UUID of involved heuristic (empty if none)

        Returns:
            True if stored successfully.
        """
        if not self._stub:
            logger.warning("MemoryStorage not connected, event not stored")
            return False

        try:
            # Build EpisodicEvent from Event
            episodic_event = memory_pb2.EpisodicEvent(
                id=getattr(event, "id", ""),
                timestamp_ms=int(time.time() * 1000),
                source=getattr(event, "source", ""),
                raw_text=getattr(event, "raw_text", ""),
                response_id=response_id,
                response_text=response_text,
                predicted_success=predicted_success,
                prediction_confidence=prediction_confidence,
                llm_prompt_text=prompt_text,
                decision_path=decision_path,
                matched_heuristic_id=matched_heuristic_id,
            )

            # Copy salience if present
            # Note: Both Event.salience and EpisodicEvent.salience now use
            # types_pb2.SalienceVector (shared type), so CopyFrom works correctly
            if hasattr(event, "salience") and event.salience:
                episodic_event.salience.CopyFrom(event.salience)

            request = memory_pb2.StoreEventRequest(event=episodic_event)
            response = await self._stub.StoreEvent(request)

            if not response.success:
                logger.error("Failed to store event", error=response.error)
                return False

            return True

        except grpc.RpcError as e:
            logger.error("Failed to store event", error=str(e))
            return False

    async def store_events(
        self,
        events: list[Any],
        response_id: str = "",
    ) -> int:
        """
        Store multiple events (batch).

        Used for accumulated moment events on tick.
        These events don't have individual response data since
        the moment was processed as a batch.

        Args:
            events: List of event protos
            response_id: Optional moment-level response ID

        Returns:
            Number of events successfully stored.
        """
        if not self._stub:
            logger.warning("MemoryStorage not connected, events not stored")
            return 0

        stored = 0
        for event in events:
            # Batch events don't have individual LLM responses
            success = await self.store_event(event, response_id=response_id)
            if success:
                stored += 1

        return stored

    async def record_heuristic_fire(
        self,
        heuristic_id: str,
        event_id: str,
        episodic_event_id: str = "",
    ) -> str:
        """
        Record that a heuristic fired ("Flight Recorder").

        Args:
            heuristic_id: UUID of heuristic that fired
            event_id: ID of event that triggered it
            episodic_event_id: Optional: UUID of persisted episodic event

        Returns:
            Fire record ID (UUID) if successful, empty string otherwise.
        """
        if not self._stub:
            logger.warning("MemoryStorage not connected, fire not recorded")
            return ""

        try:
            request = memory_pb2.RecordHeuristicFireRequest(
                heuristic_id=heuristic_id,
                event_id=event_id,
                episodic_event_id=episodic_event_id
            )
            response = await self._stub.RecordHeuristicFire(request)
            return response.fire_id
        except grpc.RpcError as e:
            logger.error("Failed to record heuristic fire", error=str(e))
            return ""

    async def update_heuristic_confidence(
        self,
        heuristic_id: str,
        positive: bool,
        learning_rate: float = 0.0,
        predicted_success: float = 0.0,
        feedback_source: str = "explicit",
    ) -> dict:
        """
        Update heuristic confidence based on feedback.

        Used for both explicit (user thumbs up/down) and implicit
        (outcome observed) feedback.

        Args:
            heuristic_id: UUID of the heuristic to update
            positive: True for positive feedback, False for negative
            learning_rate: Optional override (0 = use default 0.1)
            predicted_success: LLM's prediction for TD learning
            feedback_source: "explicit" or "implicit"

        Returns:
            Dict with success, old_confidence, new_confidence, delta, td_error
        """
        if not self._stub:
            logger.warning("MemoryStorage not connected, feedback not sent")
            return {"success": False, "error": "Not connected"}

        try:
            request = memory_pb2.UpdateHeuristicConfidenceRequest(
                heuristic_id=heuristic_id,
                positive=positive,
                learning_rate=learning_rate,
                predicted_success=predicted_success,
                feedback_source=feedback_source,
            )
            response = await self._stub.UpdateHeuristicConfidence(request)

            if response.success:
                logger.info(
                    "Confidence updated",
                    heuristic_id=heuristic_id[:8],
                    old_confidence=round(response.old_confidence, 2),
                    new_confidence=round(response.new_confidence, 2),
                    feedback_source=feedback_source,
                )

            return {
                "success": response.success,
                "error": response.error,
                "old_confidence": response.old_confidence,
                "new_confidence": response.new_confidence,
                "delta": response.delta,
                "td_error": response.td_error,
            }

        except grpc.RpcError as e:
            logger.error("Failed to update heuristic confidence", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_heuristic(self, heuristic_id: str) -> dict | None:
        """
        Get a heuristic by ID.

        Used by OutcomeWatcher to get condition_text for pattern matching.

        Returns:
            Dict with heuristic fields, or None if not found.
        """
        if not self._stub:
            logger.warning("MemoryStorage not connected")
            return None

        try:
            request = memory_pb2.GetHeuristicRequest(id=heuristic_id)
            response = await self._stub.GetHeuristic(request)

            if response.heuristic and response.heuristic.id:
                return {
                    "id": response.heuristic.id,
                    "name": response.heuristic.name,
                    "condition_text": response.heuristic.condition_text,
                    "effects_json": response.heuristic.effects_json,
                    "confidence": response.heuristic.confidence,
                    "origin": response.heuristic.origin,
                }
            return None

        except grpc.RpcError as e:
            logger.error("Failed to get heuristic", error=str(e))
            return None
