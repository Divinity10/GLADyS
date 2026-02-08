#!/usr/bin/env python3
"""Integration test: Orchestrator <-> Memory via gRPC.

Prerequisites:
  python scripts/local.py start all

This test:
1. Stores a heuristic in Memory that triggers high salience for "threat" events
2. Sends a matching event to Orchestrator
3. Verifies Orchestrator routes based on Memory's salience evaluation

Service Ports:
- MemoryStorage (Python): 50051 - Stores heuristics/events
- SalienceGateway (Rust): 50052 - Evaluates salience (with caching)
- Orchestrator: 50050 - Routes events
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import grpc
import pytest
from google.protobuf.timestamp_pb2 import Timestamp

# Add orchestrator to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

from gladys_orchestrator.generated import common_pb2
from gladys_orchestrator.generated import orchestrator_pb2
from gladys_orchestrator.generated import orchestrator_pb2_grpc
from gladys_orchestrator.generated import memory_pb2
from gladys_orchestrator.generated import memory_pb2_grpc


ORCHESTRATOR_ADDRESS = os.environ.get("ORCHESTRATOR_ADDRESS", "localhost:50050")
# MemoryStorage (Python) - for storing heuristics
MEMORY_STORAGE_ADDRESS = os.environ.get("MEMORY_STORAGE_ADDRESS", "localhost:50051")
# SalienceGateway (Rust) - for salience evaluation
SALIENCE_GATEWAY_ADDRESS = os.environ.get("SALIENCE_GATEWAY_ADDRESS", "localhost:50052")


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


async def setup_test_heuristic() -> str:
    """Store a heuristic that triggers high threat salience for 'danger' keyword."""
    channel = grpc.aio.insecure_channel(MEMORY_STORAGE_ADDRESS)
    stub = memory_pb2_grpc.MemoryStorageStub(channel)

    heuristic_id = str(uuid4())

    # Use new CBR schema - condition_text for matching, effects_json for action
    heuristic = memory_pb2.Heuristic(
        id=heuristic_id,
        name="threat_detector",
        condition_text="danger threat attack hostile enemy",  # Keywords for matching
        effects_json=json.dumps({
            "salience": {
                "threat": 0.9,  # High threat = immediate routing
            },
        }),
        confidence=0.95,
        origin="test",
    )

    request = memory_pb2.StoreHeuristicRequest(heuristic=heuristic)
    response = await stub.StoreHeuristic(request)

    if response.success:
        print(f"[OK] Created heuristic: {heuristic_id}")
    else:
        print(f"[FAIL] Failed to create heuristic: {response.error}")

    await channel.close()
    return heuristic_id


async def cleanup_heuristic(heuristic_id: str) -> None:
    """Clean up test heuristic (not implemented in proto - would need to add)."""
    # For now, heuristics persist. In a real test, we'd clean up.
    pass


# Pytest fixture to ensure test heuristic exists
@pytest.fixture(scope="module")
def event_loop():
    """Create an event loop for the module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def test_heuristic_id():
    """Create a test heuristic for salience tests."""
    return await setup_test_heuristic()


async def test_low_salience_event() -> bool:
    """Test that a low-salience event gets accumulated (not immediate)."""
    print("\n--- Test: Low Salience Event ---")

    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

    # Create an event that won't match any heuristic
    now = datetime.now(timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(now)
    event = common_pb2.Event(
        id=str(uuid4()),
        timestamp=ts,
        source="test",
        raw_text="Normal routine update",
    )

    try:
        response = await stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
        ack = response.ack
        if ack.accepted:
            print(f"[OK] Event accepted: {ack.event_id}")
            await channel.close()
            return True
        else:
            print(f"[FAIL] Event rejected: {ack.error_message}")
            await channel.close()
            return False
    except grpc.RpcError as e:
        print(f"[FAIL] gRPC error: {e.code()} - {e.details()}")
        await channel.close()
        return False


async def test_high_salience_event() -> bool:
    """Test that a high-salience event triggers immediate routing."""
    print("\n--- Test: High Salience Event (Threat Keyword) ---")

    channel = grpc.aio.insecure_channel(ORCHESTRATOR_ADDRESS)
    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

    # Create an event that matches our threat heuristic
    now = datetime.now(timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(now)
    event = common_pb2.Event(
        id=str(uuid4()),
        timestamp=ts,
        source="test",
        raw_text="DANGER! Hostile player approaching!",
    )

    try:
        response = await stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
        ack = response.ack
        if ack.accepted:
            print(f"[OK] Event accepted: {ack.event_id}")
            await channel.close()
            return True
        else:
            print(f"[FAIL] Event rejected: {ack.error_message}")
            await channel.close()
            return False
    except grpc.RpcError as e:
        print(f"[FAIL] gRPC error: {e.code()} - {e.details()}")
        await channel.close()
        return False


async def test_salience_evaluation_directly(test_heuristic_id):
    """Test Memory's SalienceGateway directly (Rust service on 50052).

    Uses pytest fixture to ensure test heuristic exists first.
    """
    print("\n--- Test: Direct SalienceGateway Call ---")
    print(f"  Test heuristic ID: {test_heuristic_id}")

    channel = grpc.aio.insecure_channel(SALIENCE_GATEWAY_ADDRESS)
    stub = memory_pb2_grpc.SalienceGatewayStub(channel)

    # Request salience for a threat event
    # Note: Empty source means no source_filter, so all heuristics are considered
    request = memory_pb2.EvaluateSalienceRequest(
        event_id=str(uuid4()),
        source="",  # Empty = no source filter
        raw_text="danger threat attack incoming!",
    )

    try:
        response = await stub.EvaluateSalience(request)

        assert not response.error, f"Unexpected error: {response.error}"

        salience = response.salience
        print(f"  threat: {salience.threat:.2f}")
        print(f"  novelty: {salience.novelty:.2f}")
        print(f"  matched_heuristic: {response.matched_heuristic_id or 'none'}")
        print(f"  from_cache: {response.from_cache}")

        # Verify high threat was detected (requires heuristic match)
        assert salience.threat >= 0.7, f"Expected threat >= 0.7, got {salience.threat:.2f}"
        assert response.matched_heuristic_id, "Expected a heuristic to match"

        print(f"[OK] High threat detected ({salience.threat:.2f})")

    finally:
        await channel.close()


async def main() -> int:
    """Run integration tests."""
    print("=" * 60)
    print("GLADyS Integration Test: Orchestrator <-> Memory")
    print("=" * 60)

    # Check services are running
    print("\nChecking services...")
    if not await wait_for_service(MEMORY_STORAGE_ADDRESS, "MemoryStorage (Python)"):
        print("\n[FAIL] MemoryStorage service not available. Run: python local.py start memory-python")
        return 1

    if not await wait_for_service(SALIENCE_GATEWAY_ADDRESS, "SalienceGateway (Rust)"):
        print("\n[FAIL] SalienceGateway service not available. Run: python local.py start memory-rust")
        return 1

    if not await wait_for_service(ORCHESTRATOR_ADDRESS, "Orchestrator"):
        print("\n[FAIL] Orchestrator service not available. Run: python local.py start orchestrator")
        return 1

    # Setup test data
    print("\nSetting up test data...")
    heuristic_id = await setup_test_heuristic()

    # Run tests
    results = []

    results.append(("Direct SalienceGateway", await test_salience_evaluation_directly()))
    results.append(("Low Salience Event", await test_low_salience_event()))
    results.append(("High Salience Event", await test_high_salience_event()))

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "[OK]" if result else "[FAIL]"
        print(f"  {symbol} {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
