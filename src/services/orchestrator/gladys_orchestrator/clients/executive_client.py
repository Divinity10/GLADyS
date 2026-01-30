"""gRPC client for Executive service.

This client sends events to the Executive for processing.
"""

import logging
from typing import Any

import grpc

from ..generated import executive_pb2
from ..generated import executive_pb2_grpc

logger = logging.getLogger(__name__)


class ExecutiveClient:
    """
    Client for the Executive service.

    The Executive is the decision-making component that:
    - Processes incoming events
    - Applies System 1 (heuristics) or System 2 (LLM reasoning)
    - Generates responses/actions
    """

    def __init__(self, address: str):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: executive_pb2_grpc.ExecutiveServiceStub | None = None

    async def connect(self) -> None:
        """Establish connection to Executive service."""
        self._channel = grpc.aio.insecure_channel(self.address)
        self._stub = executive_pb2_grpc.ExecutiveServiceStub(self._channel)
        logger.info(f"Connected to Executive at {self.address}")

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def send_event_immediate(self, event: Any, suggestion: dict | None = None) -> dict:
        """
        Send a high-salience event immediately (bypass moment accumulation).

        Args:
            event: The event to process
            suggestion: Optional suggestion context from low-conf heuristic (Scenario 2)
                       with keys: heuristic_id, suggested_action, confidence, condition_text

        Returns dict with response data from Executive:
        - accepted: bool
        - error_message: str
        - response_id: str
        - response_text: str
        - predicted_success: float
        - prediction_confidence: float
        """
        if not self._stub:
            logger.warning("Executive not connected, event not delivered")
            return {"accepted": False, "error_message": "Executive not connected"}

        try:
            # Build suggestion proto if provided
            suggestion_proto = None
            if suggestion:
                suggestion_proto = executive_pb2.HeuristicSuggestion(
                    heuristic_id=suggestion.get("heuristic_id", ""),
                    suggested_action=suggestion.get("suggested_action", ""),
                    confidence=suggestion.get("confidence", 0.0),
                    condition_text=suggestion.get("condition_text", ""),
                )
                logger.debug(
                    f"Including suggestion in request: heuristic={suggestion.get('heuristic_id')}, "
                    f"confidence={suggestion.get('confidence', 0):.2f}"
                )

            request = executive_pb2.ProcessEventRequest(
                event=event,
                immediate=True,
                suggestion=suggestion_proto,
            )
            response = await self._stub.ProcessEvent(request)
            return {
                "accepted": response.accepted,
                "error_message": response.error_message,
                "response_id": response.response_id,
                "response_text": response.response_text,
                "predicted_success": response.predicted_success,
                "prediction_confidence": response.prediction_confidence,
            }

        except grpc.RpcError as e:
            logger.error(f"Failed to send event to Executive: {e}")
            return {"accepted": False, "error_message": str(e)}
