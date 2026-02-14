"""Async gRPC client for GLADyS orchestrator.

Wraps orchestrator RPCs with timeout configuration and error handling.
All methods are async.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import TimeoutConfig
from .state import ComponentState

logger = logging.getLogger(__name__)


class GladysClient:
    """Async gRPC client for GLADyS orchestrator.

    Wraps orchestrator RPCs with timeout configuration and error handling.
    All methods are async.
    """

    def __init__(
        self,
        orchestrator_address: str,
        timeout_config: Optional[TimeoutConfig] = None,
    ) -> None:
        """Initialize client.

        Args:
            orchestrator_address: gRPC address (e.g., "localhost:50051").
            timeout_config: Timeout settings (default: TimeoutConfig()).
        """
        self.address = orchestrator_address
        self.timeout_config = timeout_config or TimeoutConfig()
        self._channel: Any = None
        self._stub: Any = None

    async def connect(self) -> None:
        """Establish gRPC channel (idempotent)."""
        if self._channel is not None:
            return

        try:
            import grpc.aio  # noqa: F811

            self._channel = grpc.aio.insecure_channel(self.address)
            try:
                from .generated import orchestrator_pb2_grpc  # type: ignore[import-not-found]

                self._stub = orchestrator_pb2_grpc.OrchestratorServiceStub(
                    self._channel
                )
            except ImportError:
                # Generated stubs are optional in some test/dev paths.
                pass
            logger.info("Connected to orchestrator at %s", self.address)
        except ImportError:
            logger.warning(
                "grpc.aio not available; client operates in stub mode "
                "(testing without gRPC)"
            )

    async def close(self) -> None:
        """Close gRPC channel."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Disconnected from orchestrator")

    def _timeout_seconds(self, timeout_ms: int) -> Optional[float]:
        """Convert ms timeout to seconds, returning None for 0 (no timeout)."""
        if timeout_ms <= 0:
            return None
        return timeout_ms / 1000.0

    async def register_component(
        self,
        component_id: str,
        component_type: str,
        capabilities: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Register component with orchestrator.

        Args:
            component_id: Unique component identifier.
            component_type: Component type (e.g., "sensor.runescape").
            capabilities: Component capabilities dict.

        Returns:
            RegisterResponse with success status.

        Raises:
            RuntimeError: If gRPC channel is not connected.
        """
        if self._stub is None:
            logger.warning("No gRPC stub available; register_component is a no-op")
            return _StubResponse(success=True)

        timeout = self._timeout_seconds(self.timeout_config.register_ms)
        response = await self._stub.RegisterComponent(
            _build_register_request(component_id, component_type, capabilities),
            timeout=timeout,
        )
        return response

    async def unregister_component(self, component_id: str) -> Any:
        """Unregister component (graceful shutdown)."""
        if self._stub is None:
            logger.warning("No gRPC stub available; unregister_component is a no-op")
            return _StubResponse(success=True)

        timeout = self._timeout_seconds(self.timeout_config.register_ms)
        response = await self._stub.UnregisterComponent(
            _build_unregister_request(component_id),
            timeout=timeout,
        )
        return response

    async def heartbeat(
        self,
        component_id: str,
        state: ComponentState,
        error_message: Optional[str] = None,
    ) -> Any:
        """Send heartbeat and retrieve pending commands.

        Args:
            component_id: Component ID.
            state: Current component state.
            error_message: Optional error message (populated on ERROR state).

        Returns:
            HeartbeatResponse with pending_commands list.
        """
        if self._stub is None:
            logger.debug("No gRPC stub available; heartbeat is a no-op")
            return _StubHeartbeatResponse()

        timeout = self._timeout_seconds(self.timeout_config.heartbeat_ms)
        response = await self._stub.Heartbeat(
            _build_heartbeat_request(component_id, state, error_message),
            timeout=timeout,
        )
        return response

    async def publish_event(self, event: Any) -> Any:
        """Publish single event to orchestrator.

        Args:
            event: Event message.

        Returns:
            PublishEventResponse with acknowledgment.
        """
        if self._stub is None:
            logger.debug("No gRPC stub available; publish_event is a no-op")
            return _StubResponse(success=True)

        timeout = self._timeout_seconds(self.timeout_config.publish_event_ms)
        response = await self._stub.PublishEvent(
            _build_publish_event_request(event),
            timeout=timeout,
        )
        return response

    async def publish_events(self, events: list[Any]) -> Any:
        """Publish batch of events (high-volume sensors).

        Args:
            events: List of Event messages.

        Returns:
            PublishEventsResponse with accepted_count and errors.
        """
        if self._stub is None:
            logger.debug("No gRPC stub available; publish_events is a no-op")
            return _StubPublishEventsResponse(accepted_count=len(events))

        timeout = self._timeout_seconds(self.timeout_config.publish_event_ms)
        response = await self._stub.PublishEvents(
            _build_publish_events_request(events),
            timeout=timeout,
        )
        return response


# ---------------------------------------------------------------------------
# Stub responses for when gRPC is not available (testing)
# ---------------------------------------------------------------------------


class _StubResponse:
    """Stub response for testing without gRPC."""

    def __init__(self, success: bool = True, error_message: str = "") -> None:
        self.success = success
        self.error_message = error_message


class _StubHeartbeatResponse:
    """Stub heartbeat response for testing without gRPC."""

    def __init__(self) -> None:
        self.acknowledged = True
        self.pending_commands: list[Any] = []


class _StubPublishEventsResponse:
    """Stub batch publish response for testing without gRPC."""

    def __init__(self, accepted_count: int = 0) -> None:
        self.accepted_count = accepted_count
        self.errors: list[Any] = []


# ---------------------------------------------------------------------------
# Proto message builders (will use generated stubs when available)
# ---------------------------------------------------------------------------


def _build_register_request(
    component_id: str,
    component_type: str,
    capabilities: Optional[dict[str, Any]],
) -> Any:
    """Build RegisterRequest proto message."""
    try:
        from gladys.v1 import orchestrator_pb2  # type: ignore[import-untyped]

        return orchestrator_pb2.RegisterRequest(
            component_id=component_id,
            component_type=component_type,
        )
    except ImportError:
        return {"component_id": component_id, "component_type": component_type}


def _build_unregister_request(component_id: str) -> Any:
    """Build UnregisterRequest proto message."""
    try:
        from gladys.v1 import orchestrator_pb2  # type: ignore[import-untyped]

        return orchestrator_pb2.UnregisterRequest(component_id=component_id)
    except ImportError:
        return {"component_id": component_id}


def _build_heartbeat_request(
    component_id: str,
    state: ComponentState,
    error_message: Optional[str],
) -> Any:
    """Build HeartbeatRequest proto message."""
    try:
        from gladys.v1 import orchestrator_pb2  # type: ignore[import-untyped]

        return orchestrator_pb2.HeartbeatRequest(
            component_id=component_id,
            state=int(state),
            error_message=error_message or "",
        )
    except ImportError:
        return {
            "component_id": component_id,
            "state": int(state),
            "error_message": error_message or "",
        }


def _build_publish_event_request(event: Any) -> Any:
    """Build PublishEventRequest proto message."""
    try:
        from gladys.v1 import orchestrator_pb2  # type: ignore[import-untyped]

        return orchestrator_pb2.PublishEventRequest(event=event)
    except ImportError:
        return {"event": event}


def _build_publish_events_request(events: list[Any]) -> Any:
    """Build PublishEventsRequest proto message."""
    try:
        from gladys.v1 import orchestrator_pb2  # type: ignore[import-untyped]

        return orchestrator_pb2.PublishEventsRequest(events=events)
    except ImportError:
        return {"events": events}
