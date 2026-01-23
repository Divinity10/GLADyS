"""gRPC server for the Orchestrator service."""

import asyncio
import logging
from concurrent import futures
from typing import AsyncIterator

import grpc
from grpc_reflection.v1alpha import reflection

from .config import OrchestratorConfig
from .registry import ComponentRegistry
from .router import EventRouter
from .accumulator import MomentAccumulator
from .clients.salience_client import SalienceMemoryClient

# Generated proto imports
from .generated import common_pb2
from .generated import orchestrator_pb2
from .generated import orchestrator_pb2_grpc

logger = logging.getLogger(__name__)


class OrchestratorServicer(orchestrator_pb2_grpc.OrchestratorServiceServicer):
    """
    gRPC servicer implementing the OrchestratorService.

    Responsibilities:
    - Receive events from sensors/preprocessors
    - Query Salience+Memory for salience scores
    - Route HIGH salience immediately to Executive
    - Accumulate LOW salience into moments
    - Send moments on configurable tick (default 100ms)
    """

    def __init__(self, config: OrchestratorConfig, salience_client: SalienceMemoryClient | None = None):
        self.config = config
        self.registry = ComponentRegistry()
        self._salience_client = salience_client
        self.router = EventRouter(config, salience_client)
        self.accumulator = MomentAccumulator(config)
        self._running = False

    async def start(self) -> None:
        """Start background tasks (moment ticker, health checks)."""
        self._running = True
        # Start moment accumulator tick loop
        asyncio.create_task(self._moment_tick_loop())
        logger.info("Orchestrator servicer started")

    async def stop(self) -> None:
        """Stop background tasks gracefully."""
        self._running = False
        logger.info("Orchestrator servicer stopped")

    async def _moment_tick_loop(self) -> None:
        """Background loop that sends accumulated moments to Executive."""
        tick_interval = self.config.moment_window_ms / 1000.0
        while self._running:
            await asyncio.sleep(tick_interval)
            moment = self.accumulator.flush()
            if moment and moment.events:
                await self.router.send_moment_to_executive(moment)

    # -------------------------------------------------------------------------
    # Event Routing RPCs
    # -------------------------------------------------------------------------

    async def PublishEvents(
        self,
        request_iterator: AsyncIterator[common_pb2.Event],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[orchestrator_pb2.EventAck]:
        """
        Streaming RPC: Sensors publish events, Orchestrator routes them.

        For each event:
        1. Query Salience+Memory for salience score
        2. If HIGH salience → immediate to Executive
        3. If LOW salience → accumulate into current moment
        """
        async for event in request_iterator:
            try:
                # Route the event (queries salience, decides path)
                result = await self.router.route_event(event, self.accumulator)
                yield orchestrator_pb2.EventAck(
                    event_id=result["event_id"],
                    accepted=result["accepted"],
                    error_message=result.get("error_message", ""),
                )
            except Exception as e:
                logger.error(f"Error routing event {event.id}: {e}")
                yield orchestrator_pb2.EventAck(
                    event_id=event.id,
                    accepted=False,
                    error_message=str(e),
                )

    async def SubscribeEvents(
        self,
        request: orchestrator_pb2.SubscribeRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[common_pb2.Event]:
        """
        Streaming RPC: Components subscribe to receive events.

        Used by Executive and other components to receive routed events.
        """
        subscriber_id = request.subscriber_id
        source_filters = list(request.source_filters) if request.source_filters else None
        event_types = list(request.event_types) if request.event_types else None

        logger.info(f"New subscriber: {subscriber_id}")

        # Register subscriber
        queue = self.router.add_subscriber(subscriber_id, source_filters, event_types)

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self.router.remove_subscriber(subscriber_id)
            logger.info(f"Subscriber disconnected: {subscriber_id}")

    # -------------------------------------------------------------------------
    # Component Lifecycle RPCs
    # -------------------------------------------------------------------------

    async def RegisterComponent(
        self,
        request: orchestrator_pb2.RegisterRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.RegisterResponse:
        """Register a component with the orchestrator."""
        result = self.registry.register(
            component_id=request.component_id,
            component_type=request.component_type,
            address=request.address,
            capabilities=request.capabilities,
        )
        return orchestrator_pb2.RegisterResponse(
            success=result.get("success", False),
            error_message=result.get("error_message", ""),
            assigned_id=result.get("assigned_id", request.component_id),
        )

    async def UnregisterComponent(
        self,
        request: orchestrator_pb2.UnregisterRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.UnregisterResponse:
        """Unregister a component (graceful shutdown)."""
        success = self.registry.unregister(request.component_id)
        return orchestrator_pb2.UnregisterResponse(success=success)

    async def SendCommand(
        self,
        request: orchestrator_pb2.CommandRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.CommandResponse:
        """Send a lifecycle command to a component."""
        # TODO: Implement command forwarding to target component
        logger.info(f"Command {request.command} to {request.target_component_id}")
        return orchestrator_pb2.CommandResponse(success=True)

    # -------------------------------------------------------------------------
    # Health & Status RPCs
    # -------------------------------------------------------------------------

    async def Heartbeat(
        self,
        request: orchestrator_pb2.HeartbeatRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.HeartbeatResponse:
        """Process heartbeat from a component."""
        self.registry.update_heartbeat(
            component_id=request.component_id,
            state=request.state,
            metrics=dict(request.metrics) if request.metrics else {},
        )
        # Check for pending commands for this component
        pending_dicts = self.registry.get_pending_commands(request.component_id)
        pending_commands = [
            orchestrator_pb2.PendingCommand(
                command_id=p.get("command_id", ""),
                command=p.get("command", orchestrator_pb2.COMMAND_UNSPECIFIED),
            )
            for p in pending_dicts
        ]
        return orchestrator_pb2.HeartbeatResponse(
            acknowledged=True,
            pending_commands=pending_commands,
        )

    async def GetSystemStatus(
        self,
        request: orchestrator_pb2.SystemStatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.SystemStatusResponse:
        """Get status of all registered components."""
        components_dicts = self.registry.get_all_status()
        components = [
            common_pb2.ComponentStatus(
                component_id=c.get("component_id", ""),
                state=c.get("state", common_pb2.COMPONENT_STATE_UNKNOWN),
                message=c.get("message", ""),
            )
            for c in components_dicts
        ]
        return orchestrator_pb2.SystemStatusResponse(components=components)

    # -------------------------------------------------------------------------
    # Service Discovery RPCs
    # -------------------------------------------------------------------------

    async def ResolveComponent(
        self,
        request: orchestrator_pb2.ResolveRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.ResolveResponse:
        """Resolve component address by ID or type."""
        if request.component_id:
            info = self.registry.get_by_id(request.component_id)
        else:
            info = self.registry.get_by_type(request.component_type)

        if info:
            return orchestrator_pb2.ResolveResponse(
                found=True,
                address=info.address,
                capabilities=info.capabilities,
            )
        return orchestrator_pb2.ResolveResponse(found=False)


async def serve(config: OrchestratorConfig | None = None) -> None:
    """Start the Orchestrator gRPC server."""
    if config is None:
        config = OrchestratorConfig()

    # Create and connect salience client
    salience_client = SalienceMemoryClient(config.salience_memory_address)
    try:
        await salience_client.connect()
        logger.info(f"Connected to Salience+Memory at {config.salience_memory_address}")
    except Exception as e:
        logger.warning(f"Could not connect to Salience+Memory: {e}. Using graceful degradation.")
        salience_client = None

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=config.max_workers))

    servicer = OrchestratorServicer(config, salience_client)
    await servicer.start()

    # Add servicer to server
    orchestrator_pb2_grpc.add_OrchestratorServiceServicer_to_server(servicer, server)

    # Enable reflection for debugging
    SERVICE_NAMES = (
        orchestrator_pb2.DESCRIPTOR.services_by_name["OrchestratorService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    address = f"{config.host}:{config.port}"
    server.add_insecure_port(address)

    logger.info(f"Starting Orchestrator server on {address}")
    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        await servicer.stop()
        if salience_client:
            await salience_client.close()
        await server.stop(grace=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
