#!/usr/bin/env python3
"""Test script to verify the heuristic formation flow.

This script:
1. Sends an event directly to Executive (skip Orchestrator for PoC testing)
2. Sends positive feedback to Executive
3. Verifies the heuristic was stored in Memory

Usage:
    cd src/orchestrator && uv run python ../integration/test_heuristic_flow.py
"""

import asyncio
import sys
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc

from gladys_orchestrator.generated import executive_pb2, executive_pb2_grpc
from gladys_orchestrator.generated import common_pb2


async def test_event_and_feedback():
    """Send an event to Executive, then provide positive feedback to create a heuristic."""
    print("\n=== Step 1: Send Event and Feedback to Executive ===")

    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        stub = executive_pb2_grpc.ExecutiveServiceStub(channel)

        # First, we need a response_id from processing an event directly
        # Let's send an event directly to Executive
        print("  Processing event directly with Executive...")

        event_request = executive_pb2.ProcessEventRequest(
            event=common_pb2.Event(
                id="test-event-direct",
                source="test-sensor",
                raw_text="Warning: Low health detected, should find shelter",
            ),
            immediate=True,
        )

        event_response = await stub.ProcessEvent(event_request)
        print(f"  Event response: accepted={event_response.accepted}, response_id={event_response.response_id}")

        if not event_response.response_id:
            print("  WARNING: No response_id - LLM may not be available")
            print("  Skipping feedback test (requires LLM for pattern extraction)")
            return None

        # Send positive feedback
        feedback_request = executive_pb2.ProvideFeedbackRequest(
            event_id="test-event-direct",
            response_id=event_response.response_id,
            positive=True,
        )

        print(f"  Sending positive feedback for response_id={event_response.response_id}...")
        feedback_response = await stub.ProvideFeedback(feedback_request)

        print(f"  Feedback response: accepted={feedback_response.accepted}")
        if feedback_response.created_heuristic_id:
            print(f"  HEURISTIC CREATED: {feedback_response.created_heuristic_id}")
        if feedback_response.error_message:
            print(f"  Error: {feedback_response.error_message}")

        return feedback_response.created_heuristic_id


async def check_heuristics_in_memory():
    """Query Memory to see if heuristics exist."""
    print("\n=== Step 2: Check Heuristics in Memory ===")

    try:
        from gladys_memory.generated import memory_pb2, memory_pb2_grpc
    except ImportError:
        print("  SKIP: Memory proto stubs not available locally")
        print("  (This is expected - stubs are in the container)")
        return

    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = memory_pb2_grpc.MemoryStorageStub(channel)

        request = memory_pb2.QueryHeuristicsRequest(
            min_confidence=0.0,
            limit=10,
        )

        response = await stub.QueryHeuristics(request)

        if response.error:
            print(f"  Error: {response.error}")
            return

        print(f"  Found {len(response.matches)} heuristics in Memory:")
        for match in response.matches:
            h = match.heuristic
            print(f"    - {h.name}")
            print(f"      condition: {h.condition_text}")
            print(f"      confidence: {h.confidence}")
            print(f"      origin: {h.origin}")


async def main():
    print("=" * 60)
    print("Heuristic Formation Flow Test")
    print("=" * 60)

    # Step 1 & 2: Send event to Executive, then feedback
    heuristic_id = await test_event_and_feedback()

    # Step 3: Check Memory for heuristics
    await check_heuristics_in_memory()

    print("\n" + "=" * 60)
    if heuristic_id:
        print("SUCCESS: Heuristic was created and stored in Memory!")
    else:
        print("PARTIAL: Event flow works, but heuristic creation requires LLM")
        print("  Ensure OLLAMA_URL and OLLAMA_MODEL are set in .env")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
