"""gRPC client for Executive service.

This client sends events to the Executive for processing.
"""

from typing import Any

import grpc

from gladys_common import get_logger

from ..generated import executive_pb2
from ..generated import executive_pb2_grpc

logger = get_logger(__name__)


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
        logger.info("Connected to Executive", address=self.address)

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def send_event_immediate(
        self,
        event: Any,
        suggestion: dict | None = None,
        candidates: list[dict] | None = None,
    ) -> dict:
        """
        Send a high-salience event immediately (bypass moment accumulation).

        Args:
            event: The event to process
            suggestion: Optional suggestion context from low-conf heuristic (Scenario 2)
                       with keys: heuristic_id, suggested_action, confidence, condition_text
            candidates: Optional additional below-threshold heuristic candidates

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
                    "Including suggestion in request",
                    heuristic_id=suggestion.get("heuristic_id"),
                    confidence=round(suggestion.get("confidence", 0), 2),
                )

            candidate_protos = []
            for candidate in candidates or []:
                candidate_protos.append(
                    executive_pb2.HeuristicSuggestion(
                        heuristic_id=candidate.get("heuristic_id", ""),
                        suggested_action=candidate.get("suggested_action", ""),
                        confidence=candidate.get("confidence", 0.0),
                        condition_text=candidate.get("condition_text", ""),
                    )
                )

            request = executive_pb2.ProcessEventRequest(
                event=event,
                immediate=True,
                suggestion=suggestion_proto,
                candidates=candidate_protos,
            )
            response = await self._stub.ProcessEvent(request)
            return {
                "accepted": response.accepted,
                "error_message": response.error_message,
                "response_id": response.response_id,
                "response_text": response.response_text,
                "predicted_success": response.predicted_success,
                "prediction_confidence": response.prediction_confidence,
                "prompt_text": response.prompt_text,
                "decision_path": response.decision_path,
                "matched_heuristic_id": response.matched_heuristic_id,
            }

        except grpc.RpcError as e:
            logger.error("Failed to send event to Executive", error=str(e))
            return {"accepted": False, "error_message": str(e)}
