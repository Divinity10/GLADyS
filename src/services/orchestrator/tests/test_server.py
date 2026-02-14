"""Tests for the Orchestrator gRPC server."""

import pytest

from gladys_orchestrator.server import OrchestratorServicer
from gladys_orchestrator.config import OrchestratorConfig
from gladys_orchestrator.generated import orchestrator_pb2, common_pb2


class TestOrchestratorServicer:
    """Test cases for OrchestratorServicer."""

    def test_servicer_initialization(self):
        """Servicer initializes with config."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        assert servicer.config == config
        assert servicer.registry is not None
        assert servicer.router is not None
        assert servicer.event_queue is not None

    @pytest.mark.asyncio
    async def test_register_component(self):
        """RegisterComponent RPC works."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        request = orchestrator_pb2.RegisterRequest(
            component_id="sensor-1",
            component_type="sensor",
            address="localhost:50001",
        )

        response = await servicer.RegisterComponent(request, context=None)

        assert response.success is True
        assert response.assigned_id == "sensor-1"

    @pytest.mark.asyncio
    async def test_unregister_component(self):
        """UnregisterComponent RPC works."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        # First register
        register_req = orchestrator_pb2.RegisterRequest(
            component_id="sensor-1",
            component_type="sensor",
            address="localhost:50001",
        )
        await servicer.RegisterComponent(register_req, context=None)

        # Then unregister
        unregister_req = orchestrator_pb2.UnregisterRequest(
            component_id="sensor-1",
        )
        response = await servicer.UnregisterComponent(unregister_req, context=None)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_heartbeat(self):
        """Heartbeat RPC works."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        # First register
        register_req = orchestrator_pb2.RegisterRequest(
            component_id="sensor-1",
            component_type="sensor",
            address="localhost:50001",
        )
        await servicer.RegisterComponent(register_req, context=None)

        # Send heartbeat
        heartbeat_req = orchestrator_pb2.HeartbeatRequest(
            component_id="sensor-1",
            state=common_pb2.COMPONENT_STATE_ACTIVE,
        )
        response = await servicer.Heartbeat(heartbeat_req, context=None)

        assert response.acknowledged is True

    @pytest.mark.asyncio
    async def test_resolve_component_by_id(self):
        """ResolveComponent by ID works."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        # First register
        register_req = orchestrator_pb2.RegisterRequest(
            component_id="sensor-1",
            component_type="sensor",
            address="localhost:50001",
        )
        await servicer.RegisterComponent(register_req, context=None)

        # Resolve
        resolve_req = orchestrator_pb2.ResolveRequest(
            component_id="sensor-1",
        )
        response = await servicer.ResolveComponent(resolve_req, context=None)

        assert response.found is True
        assert response.address == "localhost:50001"

    @pytest.mark.asyncio
    async def test_resolve_component_not_found(self):
        """ResolveComponent returns found=False for unknown ID."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        resolve_req = orchestrator_pb2.ResolveRequest(
            component_id="nonexistent",
        )
        response = await servicer.ResolveComponent(resolve_req, context=None)

        assert response.found is False

    @pytest.mark.asyncio
    async def test_get_system_status(self):
        """GetSystemStatus RPC works."""
        config = OrchestratorConfig()
        servicer = OrchestratorServicer(config)

        # Register some components
        for i in range(3):
            req = orchestrator_pb2.RegisterRequest(
                component_id=f"sensor-{i}",
                component_type="sensor",
                address=f"localhost:5000{i}",
            )
            await servicer.RegisterComponent(req, context=None)

        # Get status
        status_req = orchestrator_pb2.SystemStatusRequest()
        response = await servicer.GetSystemStatus(status_req, context=None)

        assert len(response.components) == 3
