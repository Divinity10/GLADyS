#!/usr/bin/env python3
"""Integration Test: Feedback → Confidence Update E2E.

Verifies the Bayesian Beta-Binomial confidence update path:
- Positive feedback increases confidence
- Negative feedback decreases confidence

Requires Memory service running. Uses PYTHON_ADDRESS env var.

Usage:
    python scripts/local.py test test_feedback_e2e.py
    python scripts/docker.py test test_feedback_e2e.py
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import grpc

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))

try:
    from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
except ImportError:
    print("ERROR: Proto stubs not found. Run 'make proto'")
    sys.exit(1)

MEMORY_ADDRESS = os.environ.get("PYTHON_ADDRESS")
if not MEMORY_ADDRESS:
    print("ERROR: PYTHON_ADDRESS environment variable required.")
    print("Use wrapper scripts: python scripts/local.py test test_feedback_e2e.py")
    sys.exit(1)


async def create_test_heuristic(stub, heuristic_id: str, confidence: float = 0.5):
    """Create a heuristic with known confidence for testing."""
    await stub.StoreHeuristic(
        memory_pb2.StoreHeuristicRequest(
            heuristic=memory_pb2.Heuristic(
                id=heuristic_id,
                name="feedback-test-heuristic",
                condition_text="test condition for feedback verification",
                effects_json='{"type": "suggest", "message": "test action"}',
                confidence=confidence,
                origin="test",
            ),
            generate_embedding=True,
        )
    )


async def get_confidence(stub, heuristic_id: str) -> float:
    """Get current confidence for a heuristic."""
    resp = await stub.GetHeuristic(memory_pb2.GetHeuristicRequest(id=heuristic_id))
    if resp.error:
        raise ValueError(f"GetHeuristic failed: {resp.error}")
    return resp.heuristic.confidence


async def record_fire(stub, heuristic_id: str, event_id: str):
    """Record a heuristic fire (required before confidence update)."""
    await stub.RecordHeuristicFire(
        memory_pb2.RecordHeuristicFireRequest(
            heuristic_id=heuristic_id,
            event_id=event_id,
        )
    )


async def run_tests():
    channel = grpc.aio.insecure_channel(MEMORY_ADDRESS)
    stub = memory_pb2_grpc.MemoryStorageStub(channel)

    print("\n" + "=" * 60)
    print("FEEDBACK CONFIDENCE E2E TEST")
    print("=" * 60)

    passed = 0
    failed = 0

    # --- Test 1: Positive feedback increases confidence ---
    print("\n>>> Test 1: Positive feedback increases confidence")
    h_id = str(uuid.uuid4())
    event_id = f"test-event-{uuid.uuid4()}"

    await create_test_heuristic(stub, h_id, confidence=0.5)

    # Record a fire first (fire_count must be incremented for Bayesian update)
    await record_fire(stub, h_id, event_id)

    old_conf = await get_confidence(stub, h_id)
    resp = await stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=h_id,
            positive=True,
        )
    )

    if resp.success and resp.new_confidence > old_conf:
        print(f"    [Pass] {old_conf:.3f} → {resp.new_confidence:.3f} (delta={resp.delta:.3f})")
        passed += 1
    else:
        print(f"    [FAIL] success={resp.success}, old={old_conf}, new={resp.new_confidence}")
        failed += 1

    # --- Test 2: Negative feedback decreases confidence ---
    print("\n>>> Test 2: Negative feedback decreases confidence")
    h_id2 = str(uuid.uuid4())
    event_id2 = f"test-event-{uuid.uuid4()}"

    await create_test_heuristic(stub, h_id2, confidence=0.7)
    await record_fire(stub, h_id2, event_id2)

    old_conf2 = await get_confidence(stub, h_id2)
    resp2 = await stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=h_id2,
            positive=False,
        )
    )

    if resp2.success and resp2.new_confidence < old_conf2:
        print(f"    [Pass] {old_conf2:.3f} → {resp2.new_confidence:.3f} (delta={resp2.delta:.3f})")
        passed += 1
    else:
        print(f"    [FAIL] success={resp2.success}, old={old_conf2}, new={resp2.new_confidence}")
        failed += 1

    # --- Test 3: Multiple positive feedbacks converge toward 1.0 ---
    print("\n>>> Test 3: Multiple positive feedbacks converge toward 1.0")
    h_id3 = str(uuid.uuid4())

    await create_test_heuristic(stub, h_id3, confidence=0.5)

    for i in range(5):
        ev = f"test-event-{uuid.uuid4()}"
        await record_fire(stub, h_id3, ev)
        await stub.UpdateHeuristicConfidence(
            memory_pb2.UpdateHeuristicConfidenceRequest(
                heuristic_id=h_id3,
                positive=True,
            )
        )

    final_conf = await get_confidence(stub, h_id3)
    if final_conf > 0.8:
        print(f"    [Pass] After 5 positive: confidence={final_conf:.3f} (>0.8)")
        passed += 1
    else:
        print(f"    [FAIL] After 5 positive: confidence={final_conf:.3f} (expected >0.8)")
        failed += 1

    # --- Test 4: Nonexistent heuristic returns error ---
    print("\n>>> Test 4: Nonexistent heuristic returns error")
    fake_id = str(uuid.uuid4())
    try:
        await stub.UpdateHeuristicConfidence(
            memory_pb2.UpdateHeuristicConfidenceRequest(
                heuristic_id=fake_id,
                positive=True,
            )
        )
        print(f"    [FAIL] Expected error for nonexistent heuristic")
        failed += 1
    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            print(f"    [Pass] Got NOT_FOUND as expected")
            passed += 1
        else:
            print(f"    [FAIL] Expected NOT_FOUND, got {e.code()}")
            failed += 1

    await channel.close()

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)