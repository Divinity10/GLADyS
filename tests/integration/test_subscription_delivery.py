#!/usr/bin/env python3
"""Integration test: Response Subscription Delivery.

Prerequisites:
  python scripts/local.py start all

This test verifies that queued event responses are delivered via the
SubscribeResponses streaming RPC.

Flow tested:
1. Subscribe to responses via SubscribeResponses RPC
2. Send a low-salience event (goes through queue path)
3. Verify response is received via subscription stream

Service Ports:
- Orchestrator: 50050 - Routes events, manages subscriptions
- Executive: 50053 - Generates responses
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import grpc
import pytest

# Add orchestrator to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

from gladys_orchestrator.generated import common_pb2
from gladys_orchestrator.generated import orchestrator_pb2
from gladys_orchestrator.generated import orchestrator_pb2_grpc


ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS", "localhost:50050")

# Timeout for LLM response (can be slow on first call)
RESPONSE_TIMEOUT = 60.0


async def wait_for_service(address: str, name: str, timeout: float = 30.0) -> bool:
    """Wait for a gRPC service to become available."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            channel = grpc.aio.insecure_channel(address)
            await asyncio.wait_for(channel.channel_ready(), timeout=2.0)
            await channel.close()
            print(f"[OK] {name} is ready at {address}")
            return True
        except Exception:
            await asyncio.sleep(1.0)
    print(f"[FAIL] {name} not available at {address} after {timeout}s")
    return False


@pytest.fixture
async def orchestrator_stub():
    """Create orchestrator stub."""
    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
    yield orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
    await channel.close()


@pytest.mark.asyncio
async def test_subscription_receives_queued_response(orchestrator_stub):
    """Test that queued event responses are delivered via subscription.

    This test catches the bug where Streamlit UI was not receiving responses
    because the subscription mechanism wasn't being tested.
    """
    # Check services are up
    if not await wait_for_service(ORCHESTRATOR_ADDRESS, "Orchestrator"):
        pytest.skip("Orchestrator not available")

    received_responses = []
    subscription_ready = asyncio.Event()
    subscription_error = None

    async def subscriber_task():
        """Background task to receive subscription responses."""
        nonlocal subscription_error
        try:
            subscriber_id = f"test-{uuid4().hex[:8]}"
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=True
            )
            print(f"[Subscription] Starting as {subscriber_id}")

            async for resp in orchestrator_stub.SubscribeResponses(req):
                print(f"[Subscription] Received: event_id={resp.event_id[:8]}")
                received_responses.append(resp)
                # Signal we got at least one response
                subscription_ready.set()
        except asyncio.CancelledError:
            print("[Subscription] Cancelled")
        except Exception as e:
            subscription_error = e
            print(f"[Subscription] Error: {e}")
            subscription_ready.set()

    # Start subscription in background
    sub_task = asyncio.create_task(subscriber_task())

    # Give subscription time to establish
    await asyncio.sleep(0.5)

    # Send a low-salience event (will go through queue path)
    event_id = str(uuid4())
    event = common_pb2.Event(
        id=event_id,
        source="test-subscription",
        raw_text="Testing subscription delivery mechanism",
    )
    # Force low salience to ensure queue path
    event.salience.novelty = 0.1

    print(f"[Test] Sending event {event_id[:8]} with low salience...")

    # Send event and verify it was queued
    response = await orchestrator_stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
    ack = response.ack

    assert ack is not None, "No ack received"
    assert ack.accepted, f"Event not accepted: {ack.error_message}"
    assert ack.queued, "Event should be queued (low salience)"

    print(f"[Test] Event queued, waiting for response (up to {RESPONSE_TIMEOUT}s)...")

    # Wait for response via subscription
    try:
        await asyncio.wait_for(subscription_ready.wait(), timeout=RESPONSE_TIMEOUT)
    except asyncio.TimeoutError:
        sub_task.cancel()
        pytest.fail(f"No response received via subscription after {RESPONSE_TIMEOUT}s")

    # Cancel subscription task
    sub_task.cancel()
    try:
        await sub_task
    except asyncio.CancelledError:
        pass

    # Check for subscription errors
    if subscription_error:
        pytest.fail(f"Subscription error: {subscription_error}")

    # Verify we received the response
    assert len(received_responses) >= 1, "No responses received"

    # Find our response
    our_response = next((r for r in received_responses if r.event_id == event_id), None)
    assert our_response is not None, f"Response for event {event_id[:8]} not found"

    # Verify response content
    assert our_response.routing_path == 2, f"Expected QUEUED path (2), got {our_response.routing_path}"
    assert our_response.response_text, "Response text should not be empty"

    print(f"[Test] SUCCESS: Received response via subscription")
    print(f"  - Event ID: {our_response.event_id[:8]}")
    print(f"  - Routing: QUEUED")
    print(f"  - Response: {our_response.response_text[:50]}...")


@pytest.mark.asyncio
async def test_subscription_multiple_subscribers():
    """Test that multiple subscribers can receive the same response."""
    # Check services are up
    if not await wait_for_service(ORCHESTRATOR_ADDRESS, "Orchestrator"):
        pytest.skip("Orchestrator not available")

    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

    received_by_sub1 = []
    received_by_sub2 = []

    async def subscriber_task(subscriber_num: int, responses_list: list):
        """Background task to receive subscription responses."""
        try:
            subscriber_id = f"test-multi-{subscriber_num}-{uuid4().hex[:4]}"
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=True
            )
            async for resp in stub.SubscribeResponses(req):
                responses_list.append(resp)
        except asyncio.CancelledError:
            pass

    # Start two subscribers
    sub1 = asyncio.create_task(subscriber_task(1, received_by_sub1))
    sub2 = asyncio.create_task(subscriber_task(2, received_by_sub2))

    await asyncio.sleep(0.5)

    # Send a low-salience event
    event_id = str(uuid4())
    event = common_pb2.Event(
        id=event_id,
        source="test-multi-sub",
        raw_text="Testing multiple subscribers",
    )
    event.salience.novelty = 0.1

    response = await stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
    ack = response.ack
    assert ack.queued, "Event should be queued"

    # Wait for responses
    await asyncio.sleep(RESPONSE_TIMEOUT)

    # Cancel subscribers
    sub1.cancel()
    sub2.cancel()
    try:
        await sub1
        await sub2
    except asyncio.CancelledError:
        pass

    await channel.close()

    # Both subscribers should have received the response
    found_in_sub1 = any(r.event_id == event_id for r in received_by_sub1)
    found_in_sub2 = any(r.event_id == event_id for r in received_by_sub2)

    assert found_in_sub1, "Subscriber 1 didn't receive the response"
    assert found_in_sub2, "Subscriber 2 didn't receive the response"

    print("[Test] SUCCESS: Both subscribers received the response")


if __name__ == "__main__":
    # Allow running directly for quick testing
    asyncio.run(test_subscription_receives_queued_response(
        orchestrator_pb2_grpc.OrchestratorServiceStub(
            grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
        )
    ))
