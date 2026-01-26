#!/usr/bin/env python3
"""Test evaluation RPCs: FlushMoment and SubscribeResponses.

This test proves that:
1. FlushMoment returns 0 when accumulator is empty
2. LOW salience events go to accumulator (not IMMEDIATE)
3. FlushMoment flushes accumulated events
4. SubscribeResponses receives responses for accumulated events

Usage (via wrapper scripts - recommended):
    python scripts/local.py test test_evaluation_rpcs.py   # Test against LOCAL
    python scripts/docker.py test test_evaluation_rpcs.py  # Test against DOCKER

Manual usage (must set env vars):
    ORCHESTRATOR_ADDRESS=localhost:50050 uv run python test_evaluation_rpcs.py  # LOCAL
    ORCHESTRATOR_ADDRESS=localhost:50060 uv run python test_evaluation_rpcs.py  # DOCKER
"""

import asyncio
import os
import sys
import uuid
import threading
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

import grpc

# Require explicit environment - no defaults to prevent wrong-environment testing
ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS")
if not ORCHESTRATOR_ADDRESS:
    print("ERROR: ORCHESTRATOR_ADDRESS environment variable not set.")
    print("Use wrapper scripts to run tests:")
    print("  python scripts/local.py test test_evaluation_rpcs.py   # LOCAL")
    print("  python scripts/docker.py test test_evaluation_rpcs.py  # DOCKER")
    sys.exit(1)


async def run_test():
    """Run the evaluation RPCs test."""
    from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
    from gladys_orchestrator.generated import common_pb2

    print("=" * 60)
    print("Evaluation RPCs Test - FlushMoment & SubscribeResponses")
    print("=" * 60)
    print(f"\nConnecting to Orchestrator at {ORCHESTRATOR_ADDRESS}...")

    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
    try:
        await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
    except asyncio.TimeoutError:
        print(f"ERROR: Could not connect to Orchestrator at {ORCHESTRATOR_ADDRESS}")
        return False

    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
    all_passed = True

    # Test 1: FlushMoment with empty accumulator
    print("\n--- Test 1: FlushMoment with empty accumulator ---")
    try:
        response = await stub.FlushMoment(
            orchestrator_pb2.FlushMomentRequest(reason="test empty")
        )
        if response.events_flushed == 0 and not response.moment_sent:
            print("PASS: FlushMoment correctly returns 0 events when empty")
        else:
            print(f"FAIL: Expected 0 events, got {response.events_flushed}")
            all_passed = False
    except Exception as e:
        print(f"FAIL: FlushMoment raised exception: {e}")
        all_passed = False

    # Test 2: Send LOW salience event and flush
    print("\n--- Test 2: LOW salience event goes to accumulator ---")
    try:
        event_id = str(uuid.uuid4())

        # Create event with LOW salience (novelty=0.1, below 0.7 threshold)
        event = common_pb2.Event(
            id=event_id,
            source="test-evaluation-rpcs",
            raw_text="This is a low salience test event",
        )
        # Set LOW salience to force accumulator path
        event.salience.novelty = 0.1

        # Send event via PublishEvents streaming RPC
        async def event_generator():
            yield event

        acks = []
        async for ack in stub.PublishEvents(event_generator()):
            acks.append(ack)

        if len(acks) == 1:
            ack = acks[0]
            if ack.accepted and not ack.routed_to_llm:
                print(f"PASS: Event accepted, routed_to_llm=False (went to accumulator)")
            elif ack.routed_to_llm:
                print(f"FAIL: Event was routed to LLM (expected accumulator)")
                all_passed = False
            else:
                print(f"FAIL: Event not accepted: {ack.error_message}")
                all_passed = False
        else:
            print(f"FAIL: Expected 1 ack, got {len(acks)}")
            all_passed = False

    except Exception as e:
        print(f"FAIL: PublishEvents raised exception: {e}")
        all_passed = False

    # Test 3: FlushMoment should now have 1 event
    print("\n--- Test 3: FlushMoment flushes accumulated event ---")
    try:
        response = await stub.FlushMoment(
            orchestrator_pb2.FlushMomentRequest(reason="test flush")
        )
        if response.events_flushed == 1 and response.moment_sent:
            print(f"PASS: FlushMoment flushed {response.events_flushed} event(s)")
        elif response.events_flushed == 0:
            print("FAIL: Expected 1 event, got 0 (event may have gone to IMMEDIATE path)")
            all_passed = False
        else:
            print(f"INFO: Flushed {response.events_flushed} events (may include other accumulated events)")
    except Exception as e:
        print(f"FAIL: FlushMoment raised exception: {e}")
        all_passed = False

    # Test 4: SubscribeResponses receives responses
    print("\n--- Test 4: SubscribeResponses receives responses ---")
    try:
        # Start subscriber FIRST, before sending event
        responses_received = []
        subscriber_started = asyncio.Event()

        async def subscribe_responses():
            request = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id="test-subscriber-" + str(uuid.uuid4())[:8],
                include_immediate=False,  # Only ACCUMULATED
            )
            try:
                call = stub.SubscribeResponses(request)
                subscriber_started.set()  # Signal that RPC call is made
                async for response in call:
                    responses_received.append(response)
                    return  # Got a response, exit
            except grpc.aio.AioRpcError as e:
                if e.code() != grpc.StatusCode.CANCELLED:
                    raise

        # Start subscriber task
        subscriber_task = asyncio.create_task(subscribe_responses())
        await subscriber_started.wait()
        # Give server time to process the subscription registration
        await asyncio.sleep(0.3)

        # NOW send the LOW salience event
        event_id2 = str(uuid.uuid4())
        event2 = common_pb2.Event(
            id=event_id2,
            source="test-evaluation-rpcs",
            raw_text="Second low salience test event",
        )
        event2.salience.novelty = 0.1

        async def event_generator2():
            yield event2

        async for ack in stub.PublishEvents(event_generator2()):
            pass  # Just send the event

        # Flush to trigger response broadcast
        flush_resp = await stub.FlushMoment(
            orchestrator_pb2.FlushMomentRequest(reason="test subscribe")
        )
        print(f"  Flush: {flush_resp.events_flushed} events flushed")

        # Wait for subscriber to receive response
        try:
            await asyncio.wait_for(subscriber_task, timeout=2.0)
        except asyncio.TimeoutError:
            subscriber_task.cancel()
            try:
                await subscriber_task
            except asyncio.CancelledError:
                pass

        # Check if we received the response
        if responses_received:
            response = responses_received[0]
            if response.routing_path == orchestrator_pb2.ROUTING_PATH_ACCUMULATED:
                print(f"PASS: Received ACCUMULATED response for event {response.event_id[:8]}...")
            else:
                print(f"FAIL: Response routing_path was {response.routing_path}, expected ACCUMULATED")
                all_passed = False
        else:
            print(f"FAIL: Did not receive any responses")
            all_passed = False

    except Exception as e:
        print(f"FAIL: SubscribeResponses test raised exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    await channel.close()

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
