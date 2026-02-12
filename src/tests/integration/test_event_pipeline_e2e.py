"""E2E test for complete event processing pipeline (Issue #176).

Tests verify event flow: sensor → orchestrator → salience → executive → memory.
Requires all services running.

IMPORTANT: This test is currently SKIPPED by default as it requires:
- memory-python service running (port 50051)
- memory-rust service running (port 50052)
- orchestrator service running (port 50053)
- executive service running (port 50055)
- salience service running (port 50054)

To run: pytest -v -k test_event_pipeline_e2e --run-e2e
"""

import asyncio
import pytest
import grpc
from datetime import datetime, timezone


# Skip by default unless --run-e2e flag is used
pytestmark = pytest.mark.skipif(
    not pytest.config.getoption("--run-e2e", default=False),
    reason="E2E test requires all services running. Use --run-e2e to enable.",
)


def pytest_addoption(parser):
    """Add --run-e2e command line option."""
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run E2E tests that require all services",
    )


@pytest.fixture
async def grpc_clients():
    """Create gRPC clients for all services."""
    # Import proto modules
    from gladys_orchestrator.generated import (
        common_pb2,
        orchestrator_pb2,
        orchestrator_pb2_grpc,
        memory_pb2,
        memory_pb2_grpc,
        executive_pb2_grpc,
        salience_pb2_grpc,
    )

    # Create channels
    orchestrator_channel = grpc.aio.insecure_channel("localhost:50053")
    memory_channel = grpc.aio.insecure_channel("localhost:50052")
    executive_channel = grpc.aio.insecure_channel("localhost:50055")
    salience_channel = grpc.aio.insecure_channel("localhost:50054")

    # Create stubs
    clients = {
        "orchestrator": orchestrator_pb2_grpc.OrchestratorStub(orchestrator_channel),
        "memory": memory_pb2_grpc.MemoryServiceStub(memory_channel),
        "executive": executive_pb2_grpc.ExecutiveStub(executive_channel),
        "salience": salience_pb2_grpc.SalienceStub(salience_channel),
        "protos": {
            "common_pb2": common_pb2,
            "orchestrator_pb2": orchestrator_pb2,
            "memory_pb2": memory_pb2,
        },
    }

    yield clients

    # Cleanup channels
    await orchestrator_channel.close()
    await memory_channel.close()
    await executive_channel.close()
    await salience_channel.close()


@pytest.mark.asyncio
class TestEventPipelineE2E:
    """E2E tests for complete event processing pipeline."""

    async def test_complete_event_pipeline(self, grpc_clients):
        """Verify event flows through entire pipeline correctly."""
        orchestrator = grpc_clients["orchestrator"]
        memory = grpc_clients["memory"]
        common_pb2 = grpc_clients["protos"]["common_pb2"]
        orchestrator_pb2 = grpc_clients["protos"]["orchestrator_pb2"]

        # Create test event
        test_event = common_pb2.Event(
            id="e2e-test-" + datetime.now(timezone.utc).isoformat(),
            source="e2e-test",
            raw_text="E2E pipeline test event",
            intent="test",
        )

        # 1. Publish event via gRPC
        response = await orchestrator.PublishEvent(
            orchestrator_pb2.PublishEventRequest(event=test_event)
        )
        assert response.ack in ["queued", "immediate"]
        event_id = test_event.id

        # 2. Wait for processing (events should process quickly)
        await asyncio.sleep(2.0)

        # 3. Verify event stored in memory
        # Query events by source
        query_request = grpc_clients["protos"]["memory_pb2"].QueryEventsRequest(
            source="e2e-test", limit=10
        )
        query_response = await memory.QueryEvents(query_request)

        # Find our event
        stored_event = None
        for event in query_response.events:
            if event.id == event_id:
                stored_event = event
                break

        assert stored_event is not None, f"Event {event_id} not found in memory"

        # 4. Verify event has response
        assert stored_event.response_text != "", "Event should have response text"
        assert stored_event.response_id != "", "Event should have response ID"

        # 5. Verify decision path
        assert stored_event.decision_path in [
            "heuristic",
            "llm",
        ], f"Invalid decision path: {stored_event.decision_path}"

        # 6. Verify timestamps
        assert stored_event.received_at.seconds > 0, "Received timestamp should be set"
        # Note: processed_at may not be in proto - check if field exists

        # 7. Verify salience was computed
        assert stored_event.salience is not None, "Event should have salience"
        assert stored_event.salience.threat >= 0.0
        assert stored_event.salience.salience >= 0.0

    async def test_batch_events_all_process(self, grpc_clients):
        """Verify batch of events all process successfully."""
        orchestrator = grpc_clients["orchestrator"]
        memory = grpc_clients["memory"]
        common_pb2 = grpc_clients["protos"]["common_pb2"]
        orchestrator_pb2 = grpc_clients["protos"]["orchestrator_pb2"]

        # Publish batch of 5 events
        event_ids = []
        batch_source = f"e2e-batch-{datetime.now(timezone.utc).timestamp()}"

        for i in range(5):
            event = common_pb2.Event(
                id=f"batch-{i}-{datetime.now(timezone.utc).timestamp()}",
                source=batch_source,
                raw_text=f"Batch event {i}",
                intent="test",
            )
            event_ids.append(event.id)

            response = await orchestrator.PublishEvent(
                orchestrator_pb2.PublishEventRequest(event=event)
            )
            assert response.ack in ["queued", "immediate"]

        # Wait for all to process
        await asyncio.sleep(3.0)

        # Query events by source
        query_request = grpc_clients["protos"]["memory_pb2"].QueryEventsRequest(
            source=batch_source, limit=10
        )
        query_response = await memory.QueryEvents(query_request)

        # Verify all 5 events stored with responses
        stored_ids = [e.id for e in query_response.events]
        for event_id in event_ids:
            assert event_id in stored_ids, f"Event {event_id} not found in memory"

        # Verify all have responses
        for event in query_response.events:
            if event.id in event_ids:
                assert event.response_text != "", f"Event {event.id} missing response"

    async def test_event_with_high_threat_processes(self, grpc_clients):
        """Verify events with high threat salience process correctly."""
        orchestrator = grpc_clients["orchestrator"]
        common_pb2 = grpc_clients["protos"]["common_pb2"]
        orchestrator_pb2 = grpc_clients["protos"]["orchestrator_pb2"]
        types_pb2 = grpc_clients["protos"]["types_pb2"]

        # Create event with high threat salience
        event = common_pb2.Event(
            id=f"threat-test-{datetime.now(timezone.utc).timestamp()}",
            source="e2e-threat-test",
            raw_text="URGENT: System critical alert",
            intent="alert",
        )

        # Manually set high threat salience
        event.salience.CopyFrom(
            types_pb2.SalienceResult(
                threat=0.95, salience=0.9, habituation=0.0, model_id="manual"
            )
        )
        event.salience.vector["novelty"] = 0.8
        event.salience.vector["opportunity"] = 0.1

        # Publish
        response = await orchestrator.PublishEvent(
            orchestrator_pb2.PublishEventRequest(event=event)
        )
        assert response.ack in ["queued", "immediate"]

        # High threat events should process very quickly
        await asyncio.sleep(1.0)

        # Verify processed
        memory = grpc_clients["memory"]
        query_request = grpc_clients["protos"]["memory_pb2"].QueryEventsRequest(
            source="e2e-threat-test", limit=5
        )
        query_response = await memory.QueryEvents(query_request)

        assert len(query_response.events) > 0, "High threat event should be stored"
        stored_event = query_response.events[0]
        assert stored_event.response_text != "", "High threat event should have response"
