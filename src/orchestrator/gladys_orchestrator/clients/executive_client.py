"""gRPC client for Executive service.

This client sends events and moments to the Executive for processing.
"""

import logging
from typing import Any

import grpc

from ..generated import executive_pb2
from ..generated import executive_pb2_grpc
from ..generated import common_pb2

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

    async def send_event_immediate(self, event: Any) -> bool:
        """
        Send a high-salience event immediately (bypass moment accumulation).

        Returns True if accepted by Executive.
        """
        if not self._stub:
            logger.warning("Executive not connected, event not delivered")
            return False

        try:
            request = executive_pb2.ProcessEventRequest(
                event=event,
                immediate=True,
            )
            response = await self._stub.ProcessEvent(request)
            return response.accepted

        except grpc.RpcError as e:
            logger.error(f"Failed to send event to Executive: {e}")
            return False

    async def send_moment(self, moment: Any) -> bool:
        """
        Send an accumulated moment to Executive.

        The moment should have events with salience already attached.
        Returns True if accepted by Executive.
        """
        if not self._stub:
            logger.warning("Executive not connected, moment not delivered")
            return False

        try:
            # Convert internal Moment to proto Moment
            proto_moment = self._to_proto_moment(moment)
            request = executive_pb2.ProcessMomentRequest(moment=proto_moment)
            response = await self._stub.ProcessMoment(request)
            return response.accepted

        except grpc.RpcError as e:
            logger.error(f"Failed to send moment to Executive: {e}")
            return False

    def _to_proto_moment(self, moment: Any) -> common_pb2.Moment:
        """Convert internal Moment dataclass to proto Moment."""
        from google.protobuf.timestamp_pb2 import Timestamp

        proto_moment = common_pb2.Moment()

        # Add events (they should already be proto Event objects with salience)
        for event in moment.events:
            proto_moment.events.append(event)

        # Set timestamps
        if moment.start_time_ms:
            start = Timestamp()
            start.FromMilliseconds(moment.start_time_ms)
            proto_moment.start_time.CopyFrom(start)

        if moment.end_time_ms:
            end = Timestamp()
            end.FromMilliseconds(moment.end_time_ms)
            proto_moment.end_time.CopyFrom(end)

        return proto_moment
