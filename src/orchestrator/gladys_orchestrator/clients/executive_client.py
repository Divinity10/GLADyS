"""gRPC client for Executive service.

This client sends events and moments to the Executive for processing.
"""

import logging
from typing import Any

import grpc

logger = logging.getLogger(__name__)


class ExecutiveClient:
    """
    Client for the Executive service.

    The Executive is the decision-making component that:
    - Processes incoming events/moments
    - Applies System 1 (heuristics) or System 2 (LLM reasoning)
    - Generates responses/actions
    """

    def __init__(self, address: str):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub = None

    async def connect(self) -> None:
        """Establish connection to Executive service."""
        self._channel = grpc.aio.insecure_channel(self.address)
        # TODO: Initialize stub from generated proto
        # self._stub = executive_pb2_grpc.ExecutiveServiceStub(self._channel)
        logger.info(f"Connected to Executive at {self.address}")

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None

    async def send_event_immediate(self, event: Any) -> bool:
        """
        Send a high-salience event immediately (bypass moment accumulation).

        Returns True if accepted by Executive.
        """
        if not self._stub:
            logger.warning("Executive not connected, event not delivered")
            return False

        try:
            # TODO: Implement actual RPC call
            # response = await self._stub.ProcessEvent(event)
            # return response.accepted
            logger.info(f"Would send immediate event to Executive: {getattr(event, 'id', 'unknown')}")
            return True

        except grpc.RpcError as e:
            logger.error(f"Failed to send event to Executive: {e}")
            return False

    async def send_moment(self, moment: Any) -> bool:
        """
        Send an accumulated moment to Executive.

        Returns True if accepted by Executive.
        """
        if not self._stub:
            logger.warning("Executive not connected, moment not delivered")
            return False

        try:
            # TODO: Implement actual RPC call
            # response = await self._stub.ProcessMoment(moment)
            # return response.accepted
            event_count = len(moment.events) if hasattr(moment, "events") else 0
            logger.info(f"Would send moment ({event_count} events) to Executive")
            return True

        except grpc.RpcError as e:
            logger.error(f"Failed to send moment to Executive: {e}")
            return False
