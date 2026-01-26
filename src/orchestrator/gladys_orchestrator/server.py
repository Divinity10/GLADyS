"""gRPC server for the Orchestrator service."""

import asyncio
import json
import logging
from concurrent import futures
from datetime import datetime, timezone
from typing import AsyncIterator

import grpc
from grpc_reflection.v1alpha import reflection

from .config import OrchestratorConfig
from .registry import ComponentRegistry
from .router import EventRouter
from .accumulator import MomentAccumulator
from .outcome_watcher import OutcomeWatcher, OutcomePattern
from .clients.executive_client import ExecutiveClient
from .clients.salience_client import SalienceMemoryClient
from .clients.memory_client import MemoryStorageClient

# Generated proto imports
from .generated import common_pb2
from .generated import orchestrator_pb2
from .generated import orchestrator_pb2_grpc
from .generated import types_pb2

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

    def __init__(
        self,
        config: OrchestratorConfig,
        salience_client: SalienceMemoryClient | None = None,
        executive_client: ExecutiveClient | None = None,
        memory_client: MemoryStorageClient | None = None,
    ):
        self.config = config
        self.registry = ComponentRegistry()
        self._salience_client = salience_client
        self._executive_client = executive_client
        self._memory_client = memory_client

        # Create OutcomeWatcher for implicit feedback (Phase 2)
        self._outcome_watcher = self._create_outcome_watcher(config, memory_client)

        self.router = EventRouter(
            config,
            salience_client,
            executive_client,
            memory_client=self._memory_client,
            outcome_watcher=self._outcome_watcher,
        )
        self.accumulator = MomentAccumulator(config)
        self._running = False
        self._started_at = datetime.now(timezone.utc)

    def _create_outcome_watcher(
        self,
        config: OrchestratorConfig,
        memory_client: MemoryStorageClient | None,
    ) -> OutcomeWatcher | None:
        """Create OutcomeWatcher from config if enabled."""
        if not config.outcome_watcher_enabled:
            logger.info("OutcomeWatcher disabled in config")
            return None

        # Parse outcome patterns from JSON config
        patterns = []
        try:
            patterns_data = json.loads(config.outcome_patterns_json)
            for p in patterns_data:
                patterns.append(OutcomePattern(
                    trigger_pattern=p.get("trigger_pattern", ""),
                    outcome_pattern=p.get("outcome_pattern", ""),
                    timeout_sec=p.get("timeout_sec", 120),
                    is_success=p.get("is_success", True),
                ))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse outcome_patterns_json: {e}")

        if patterns:
            logger.info(f"OutcomeWatcher enabled with {len(patterns)} patterns")
        else:
            logger.info("OutcomeWatcher enabled but no patterns configured")

        return OutcomeWatcher(patterns=patterns, memory_client=memory_client)

    async def start(self) -> None:
        """Start background tasks (moment ticker, health checks, outcome cleanup)."""
        self._running = True
        # Start moment accumulator tick loop
        asyncio.create_task(self._moment_tick_loop())
        # Start outcome watcher cleanup loop (if enabled)
        if self._outcome_watcher:
            asyncio.create_task(self._outcome_cleanup_loop())
        logger.info("Orchestrator servicer started")

    async def _outcome_cleanup_loop(self) -> None:
        """Background loop that cleans up expired outcome expectations."""
        cleanup_interval = self.config.outcome_cleanup_interval_sec
        while self._running:
            await asyncio.sleep(cleanup_interval)
            if self._outcome_watcher:
                expired = self._outcome_watcher.cleanup_expired()
                if expired > 0:
                    logger.debug(f"OutcomeWatcher: Cleaned up {expired} expired expectations")

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

                # Batch-store LOW salience events after sending moment
                if self._memory_client:
                    try:
                        stored = await self._memory_client.store_events(moment.events)
                        if stored > 0:
                            logger.debug(f"Batch-stored {stored} events from moment")
                    except Exception as store_err:
                        logger.warning(f"Failed to batch-store moment events: {store_err}")

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

                # Store HIGH salience events immediately after Executive responds
                # Also store Fast Path (heuristic match) events so they appear in history
                should_store = result.get("routed_to_llm") or result.get("matched_heuristic_id")
                if should_store and self._memory_client:
                    try:
                        await self._memory_client.store_event(
                            event=event,
                            response_id=result.get("response_id", ""),
                            response_text=result.get("response_text", ""),
                            predicted_success=result.get("predicted_success", 0.0),
                            prediction_confidence=result.get("prediction_confidence", 0.0),
                        )
                    except Exception as store_err:
                        logger.warning(f"Failed to store event {event.id}: {store_err}")

                yield orchestrator_pb2.EventAck(
                    event_id=result["event_id"],
                    accepted=result["accepted"],
                    error_message=result.get("error_message", ""),
                    # Executive response data (if routed to LLM)
                    response_id=result.get("response_id", ""),
                    response_text=result.get("response_text", ""),
                    predicted_success=result.get("predicted_success", 0.0),
                    prediction_confidence=result.get("prediction_confidence", 0.0),
                    # Routing info
                    routed_to_llm=result.get("routed_to_llm", False),
                    matched_heuristic_id=result.get("matched_heuristic_id", ""),
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

    async def SubscribeResponses(
        self,
        request: orchestrator_pb2.SubscribeResponsesRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[orchestrator_pb2.EventResponse]:
        """
        Streaming RPC: Subscribe to receive responses (for evaluation UI).

        Receives responses for:
        - ACCUMULATED events (after moment is sent to Executive on tick)
        - Optionally IMMEDIATE events (if include_immediate=True)

        This allows the evaluation UI to see responses for events that went
        through the accumulator path, not just IMMEDIATE path events.
        """
        subscriber_id = request.subscriber_id
        source_filters = list(request.source_filters) if request.source_filters else None
        include_immediate = request.include_immediate

        logger.info(f"New response subscriber: {subscriber_id} (include_immediate={include_immediate})")

        # Register response subscriber
        queue = self.router.add_response_subscriber(
            subscriber_id, source_filters, include_immediate
        )

        try:
            while True:
                response_dict = await queue.get()
                # Convert dict to proto EventResponse
                yield orchestrator_pb2.EventResponse(
                    event_id=response_dict.get("event_id", ""),
                    response_id=response_dict.get("response_id", ""),
                    response_text=response_dict.get("response_text", ""),
                    predicted_success=response_dict.get("predicted_success", 0.0),
                    prediction_confidence=response_dict.get("prediction_confidence", 0.0),
                    routing_path=self._routing_path_to_enum(response_dict.get("routing_path", "")),
                    matched_heuristic_id=response_dict.get("matched_heuristic_id", ""),
                    event_timestamp_ms=response_dict.get("event_timestamp_ms", 0),
                    response_timestamp_ms=response_dict.get("response_timestamp_ms", 0),
                )
        finally:
            self.router.remove_response_subscriber(subscriber_id)
            logger.info(f"Response subscriber disconnected: {subscriber_id}")

    def _routing_path_to_enum(self, path: str) -> int:
        """Convert routing path string to proto enum value."""
        if path == "IMMEDIATE":
            return orchestrator_pb2.ROUTING_PATH_IMMEDIATE
        elif path == "ACCUMULATED":
            return orchestrator_pb2.ROUTING_PATH_ACCUMULATED
        return orchestrator_pb2.ROUTING_PATH_UNSPECIFIED

    async def FlushMoment(
        self,
        request: orchestrator_pb2.FlushMomentRequest,
        context: grpc.aio.ServicerContext,
    ) -> orchestrator_pb2.FlushMomentResponse:
        """
        Manually flush the moment accumulator (for testing).

        Immediately sends any accumulated events to Executive, rather than
        waiting for the next tick. Useful for evaluation and testing.
        """
        reason = request.reason or "manual flush"
        logger.info(f"Manual moment flush requested: {reason}")

        try:
            moment = self.accumulator.flush()
            events_flushed = len(moment.events) if moment else 0

            if events_flushed > 0:
                await self.router.send_moment_to_executive(moment)

                # Batch-store events after sending moment
                if self._memory_client:
                    try:
                        stored = await self._memory_client.store_events(moment.events)
                        logger.debug(f"Batch-stored {stored} events from manual flush")
                    except Exception as store_err:
                        logger.warning(f"Failed to batch-store flush events: {store_err}")

                return orchestrator_pb2.FlushMomentResponse(
                    events_flushed=events_flushed,
                    moment_sent=True,
                )
            else:
                return orchestrator_pb2.FlushMomentResponse(
                    events_flushed=0,
                    moment_sent=False,
                )

        except Exception as e:
            logger.error(f"Error during manual flush: {e}")
            return orchestrator_pb2.FlushMomentResponse(
                events_flushed=0,
                moment_sent=False,
                error_message=str(e),
            )

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

    # -------------------------------------------------------------------------
    # Health Check RPCs
    # -------------------------------------------------------------------------

    async def GetHealth(
        self,
        request: types_pb2.GetHealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> types_pb2.GetHealthResponse:
        """Basic health check."""
        return types_pb2.GetHealthResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            message=""
        )

    async def GetHealthDetails(
        self,
        request: types_pb2.GetHealthDetailsRequest,
        context: grpc.aio.ServicerContext,
    ) -> types_pb2.GetHealthDetailsResponse:
        """Detailed health check with uptime and metrics."""
        uptime = int((datetime.now(timezone.utc) - self._started_at).total_seconds())

        # Gather connection status
        details = {
            "salience_connected": str(self._salience_client is not None).lower(),
            "executive_connected": str(self._executive_client is not None).lower(),
            "memory_connected": str(self._memory_client is not None).lower(),
            "registered_components": str(len(self.registry.get_all_status())),
            "accumulated_events": str(self.accumulator.event_count()),
        }

        return types_pb2.GetHealthDetailsResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            uptime_seconds=uptime,
            details=details
        )


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

    # Create and connect executive client
    executive_client = ExecutiveClient(config.executive_address)
    try:
        await executive_client.connect()
        logger.info(f"Connected to Executive at {config.executive_address}")
    except Exception as e:
        logger.warning(f"Could not connect to Executive: {e}. Moments will be logged only.")
        executive_client = None

    # Create and connect memory storage client
    memory_client = MemoryStorageClient(config.memory_storage_address)
    try:
        await memory_client.connect()
        logger.info(f"Connected to Memory at {config.memory_storage_address}")
    except Exception as e:
        logger.warning(f"Could not connect to Memory: {e}. Events will not be stored.")
        memory_client = None

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=config.max_workers))

    servicer = OrchestratorServicer(config, salience_client, executive_client, memory_client)
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
        if executive_client:
            await executive_client.close()
        if memory_client:
            await memory_client.close()
        await server.stop(grace=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
