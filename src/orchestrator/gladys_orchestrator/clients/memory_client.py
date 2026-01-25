"""gRPC client for MemoryStorage service.

This client stores episodic events in the Memory subsystem.
"""

import logging
import time
from typing import Any

import grpc

from ..generated import memory_pb2
from ..generated import memory_pb2_grpc

logger = logging.getLogger(__name__)


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
        logger.info(f"Connected to MemoryStorage at {self.address}")

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
    ) -> bool:
        """
        Store a single episodic event.

        Args:
            event: The event proto (common_pb2.Event)
            response_id: Executive's response ID (if routed to LLM)
            response_text: The actual LLM response (for fine-tuning)
            predicted_success: LLM's prediction (if routed to LLM)
            prediction_confidence: LLM's confidence (if routed to LLM)

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
            )

            # Copy salience if present
            if hasattr(event, "salience") and event.salience:
                episodic_event.salience.CopyFrom(event.salience)

            request = memory_pb2.StoreEventRequest(event=episodic_event)
            response = await self._stub.StoreEvent(request)

            if not response.success:
                logger.error(f"Failed to store event: {response.error}")
                return False

            return True

        except grpc.RpcError as e:
            logger.error(f"Failed to store event: {e}")
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
