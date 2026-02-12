"""gRPC client for Salience+Memory service.

This client queries the "amygdala" (Salience+Memory shared process)
for salience evaluation of incoming events.
"""

from typing import Any

import grpc

from gladys_common import get_logger

from ..generated import memory_pb2
from ..generated import memory_pb2_grpc

logger = get_logger(__name__)


class SalienceMemoryClient:
    """
    Client for the Salience+Memory service.

    The Salience+Memory service is the "amygdala" - it provides fast
    threat/opportunity detection by combining:
    - Salience Gateway (Python): evaluation pipeline
    - Memory Fast Path (Rust): heuristic lookup, novelty detection

    Per ADR-0001 §5.1, these share a process to avoid IPC overhead.
    Orchestrator calls them via gRPC (external API).
    """

    def __init__(self, address: str):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: memory_pb2_grpc.SalienceGatewayStub | None = None

    async def connect(self) -> None:
        """Establish connection to Salience+Memory service."""
        self._channel = grpc.aio.insecure_channel(self.address)
        self._stub = memory_pb2_grpc.SalienceGatewayStub(self._channel)
        logger.info("Connected to Salience+Memory", address=self.address)

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def evaluate_salience(self, event: Any) -> dict:
        """
        Evaluate salience for an event.

        Returns a dict with SalienceResult structure:
        - Scalars: threat, salience, habituation
        - Vector: dict with dimension names (novelty, goal_relevance, opportunity,
          actionability, social) as keys
        - model_id: identifier for the salience model used

        If service unavailable, returns default low salience
        (graceful degradation per ADR-0001 §11).
        """
        if not self._stub:
            logger.warning("Salience+Memory service not connected, using default salience")
            return self._default_salience()

        try:
            # Build request from event
            request = memory_pb2.EvaluateSalienceRequest(
                event_id=getattr(event, "id", ""),
                source=getattr(event, "source", ""),
                raw_text=getattr(event, "raw_text", ""),
            )

            # Add structured data if present
            if hasattr(event, "structured") and event.structured:
                from google.protobuf.json_format import MessageToJson
                request.structured_json = MessageToJson(event.structured)

            # Add entity IDs if present
            if hasattr(event, "entity_ids"):
                request.entity_ids.extend(event.entity_ids)

            # Make RPC call
            response = await self._stub.EvaluateSalience(request)

            if response.error:
                logger.error("Salience evaluation error", error=response.error)
                return self._default_salience()

            return self._response_to_dict(response)

        except grpc.RpcError as e:
            logger.error("Salience evaluation failed", error=str(e))
            # Graceful degradation: return default low salience
            return self._default_salience()

    def _response_to_dict(self, response: memory_pb2.EvaluateSalienceResponse) -> dict:
        """Convert SalienceResult proto response to dict."""
        salience = response.salience
        return {
            "threat": salience.threat,
            "salience": salience.salience,
            "habituation": salience.habituation,
            "vector": dict(salience.vector),  # Convert proto map to Python dict
            "model_id": salience.model_id,
            "_from_cache": response.from_cache,
            "_matched_heuristic": response.matched_heuristic_id,
        }

    def _default_salience(self) -> dict:
        """Default SalienceResult when service unavailable."""
        return {
            "threat": 0.0,
            "salience": 0.0,
            "habituation": 0.0,
            "vector": {
                "novelty": 0.1,  # Slight novelty for new events
                "goal_relevance": 0.0,
                "opportunity": 0.0,
                "actionability": 0.0,
                "social": 0.0,
            },
            "model_id": "default",
        }
