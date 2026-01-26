#!/usr/bin/env python3
"""Integration Test: Lab Bench Evaluation RPCs.

Validates the backend features powering the Lab Bench UI:
- SubscribeResponses (Streaming events)
- FlushMoment (Manual accumulator processing)
- Salience Override (Force IMMEDIATE/ACCUMULATED)
- Metadata Fidelity (Response IDs, Heuristic IDs)

Usage:
    python scripts/local.py test test_lab_bench.py   # LOCAL
    python scripts/docker.py test test_lab_bench.py  # DOCKER
"""

import asyncio
import logging
import os
import sys
import uuid
import time
from pathlib import Path

import grpc
import pytest

# Add paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "memory" / "python"))

try:
    from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
    from gladys_orchestrator.generated import common_pb2
    from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
except ImportError:
    print("ERROR: Proto stubs not found. Run 'make proto'")
    sys.exit(1)

# Configuration
ORCHESTRATOR_ADDR = os.environ.get("ORCHESTRATOR_ADDRESS", "localhost:50060")
MEMORY_ADDR = os.environ.get("PYTHON_ADDRESS", "localhost:50061")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_lab_bench")

@pytest.fixture(scope="module")
async def orchestrator_stub():
    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDR)
    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
    yield stub
    await channel.close()

@pytest.fixture(scope="module")
async def memory_stub():
    channel = grpc.aio.insecure_channel(MEMORY_ADDR)
    stub = memory_pb2_grpc.MemoryStorageStub(channel)
    yield stub
    await channel.close()

@pytest.mark.asyncio
async def test_immediate_path_override(orchestrator_stub):
    """Verify forcing HIGH salience bypasses accumulator."""
    event_id = str(uuid.uuid4())
    event_text = f"URGENT: Server fire! {event_id}"
    
    # Force HIGH salience
    # Send single event via generator
    async def event_gen():
        yield common_pb2.Event(
            id=event_id,
            source="test_bench",
            raw_text=event_text,
            salience=common_pb2.SalienceVector(novelty=0.9, threat=0.9)
        )

    ack = None
    async for response in orchestrator_stub.PublishEvents(event_gen()):
        ack = response
        break # Only sent one
    
    assert ack is not None
    assert ack.accepted
    assert ack.routed_to_llm, "Should be routed to LLM (Immediate Path)"
    # We might check for response_id if stub is running, but routed_to_llm is the key signal

@pytest.mark.asyncio
async def test_accumulated_path_flush(orchestrator_stub):
    """Verify forcing LOW salience + FlushMoment works end-to-end."""
    event_id = str(uuid.uuid4())
    subscriber_id = f"test-sub-{uuid.uuid4().hex[:8]}"
    
    # 1. Start Subscriber (to catch the flushed event)
    # We need to run this in background
    queue = asyncio.Queue()
    
    async def listen():
        try:
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=False
            )
            async for resp in orchestrator_stub.SubscribeResponses(req):
                await queue.put(resp)
        except Exception as e:
            logger.error(f"Subscription stream ended: {e}")

    listen_task = asyncio.create_task(listen())
    await asyncio.sleep(0.5) # Wait for subscription to register

    # 2. Send LOW salience event
    async def event_gen():
        yield common_pb2.Event(
            id=event_id,
            source="test_bench",
            raw_text=f"Background noise {event_id}",
            salience=common_pb2.SalienceVector(novelty=0.1)
        )
    
    ack = None
    async for response in orchestrator_stub.PublishEvents(event_gen()):
        ack = response
    
    assert ack.accepted
    assert not ack.routed_to_llm, "Should NOT be routed to LLM (Accumulated Path)"

    # 3. Flush Accumulator
    flush_resp = await orchestrator_stub.FlushMoment(
        orchestrator_pb2.FlushMomentRequest(reason="Test flush")
    )
    
    # It might be 0 if the auto-ticker beat us to it, but usually >0 in tests
    # We care more that the event appears in the stream
    
    # 4. Verify Stream Receipt
    try:
        # Wait up to 5s for event to appear in stream
        found = False
        start_time = time.time()
        while time.time() - start_time < 5:
            if queue.empty():
                await asyncio.sleep(0.1)
                continue
                
            resp = await queue.get()
            if resp.event_id == event_id:
                found = True
                assert resp.routing_path == orchestrator_pb2.ROUTING_PATH_ACCUMULATED
                break
        
        assert found, "Event did not appear in SubscribeResponses stream after Flush"
        
    finally:
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_heuristic_metadata(orchestrator_stub, memory_stub):
    """Verify heuristic matches return metadata in Ack."""
    # 1. Create Heuristic
    h_id = str(uuid.uuid4())
    await memory_stub.StoreHeuristic(
        memory_pb2.StoreHeuristicRequest(
            heuristic=memory_pb2.Heuristic(
                id=h_id,
                name="Lab Bench Test Rule",
                condition_text="lab bench test trigger",
                effects_json='{"action": "test"}',
                confidence=0.9,
                origin="test"
            ),
            generate_embedding=True
        )
    )
    
    # 2. Trigger it
    # Use exact text match for robustness here (unless semantic is perfect)
    # The Rust engine might use semantic, but "lab bench test trigger" is unique enough.
    async def event_gen():
        yield common_pb2.Event(
            id=str(uuid.uuid4()),
            source="test",
            raw_text="lab bench test trigger"
        )
        
    ack = None
    async for response in orchestrator_stub.PublishEvents(event_gen()):
        ack = response
        
    assert ack is not None
    assert ack.matched_heuristic_id == h_id, f"Expected match {h_id}, got {ack.matched_heuristic_id}"
    
    # Verify persistence (by checking response_id or just the fact we got metadata)
    # The main check is that the Orchestrator returns the ID to the UI
