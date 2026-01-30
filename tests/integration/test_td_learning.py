#!/usr/bin/env python3
"""Test TD learning: confidence updates based on feedback.

This test proves that:
1. Positive feedback increases heuristic confidence (simple mode)
2. Negative feedback decreases heuristic confidence (simple mode)
3. Confidence is clamped to [0, 1]
4. TD learning with prediction error works (learn more from surprises)
5. Correct predictions result in small updates
6. Wrong predictions result in large updates

Usage (via wrapper scripts - recommended):
    python scripts/local.py test test_td_learning.py   # Test against LOCAL
    python scripts/docker.py test test_td_learning.py  # Test against DOCKER

Manual usage (must set env vars):
    PYTHON_ADDRESS=localhost:50051 uv run python test_td_learning.py  # LOCAL
    PYTHON_ADDRESS=localhost:50061 uv run python test_td_learning.py  # DOCKER
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc

# Require explicit environment - no defaults to prevent wrong-environment testing
PYTHON_ADDRESS = os.environ.get("PYTHON_ADDRESS")
if not PYTHON_ADDRESS:
    print("ERROR: PYTHON_ADDRESS environment variable not set.")
    print("Use wrapper scripts to run tests:")
    print("  python scripts/local.py test test_td_learning.py   # LOCAL")
    print("  python scripts/docker.py test test_td_learning.py  # DOCKER")
    sys.exit(1)


async def run_test():
    """Run the TD learning test."""
    try:
        from gladys_memory import memory_pb2, memory_pb2_grpc
    except ImportError:
        from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc

    print("=" * 60)
    print("TD Learning Test - Confidence Updates")
    print("=" * 60)
    print(f"\nConnecting to Python Memory at {PYTHON_ADDRESS}...")

    channel = grpc.aio.insecure_channel(PYTHON_ADDRESS)
    try:
        await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
    except asyncio.TimeoutError:
        print(f"ERROR: Could not connect to Python Memory service at {PYTHON_ADDRESS}")
        print("Make sure the service is running:")
        print("  cd src/memory/python && uv run python -m gladys_memory.grpc_server")
        return False

    storage_stub = memory_pb2_grpc.MemoryStorageStub(channel)

    # Step 1: Create a test heuristic with initial confidence
    print("\n--- Step 1: Create test heuristic ---")
    heuristic_id = str(uuid.uuid4())
    initial_confidence = 0.5

    heuristic = memory_pb2.Heuristic(
        id=heuristic_id,
        name="TD Test Heuristic",
        condition_text="test td learning confidence",
        effects_json='{"action": "test_action"}',
        confidence=initial_confidence,
        learning_rate=0.1,  # 10% learning rate
        origin="test",
    )

    request = memory_pb2.StoreHeuristicRequest(
        heuristic=heuristic,
        generate_embedding=True,
    )
    response = await storage_stub.StoreHeuristic(request)

    if not response.success:
        print(f"ERROR: Failed to store heuristic: {response.error}")
        return False

    print(f"  Created heuristic: {heuristic_id}")
    print(f"  Initial confidence: {initial_confidence}")

    # Step 2: Send positive feedback and verify confidence increases
    print("\n--- Step 2: Positive feedback ---")
    pos_request = memory_pb2.UpdateHeuristicConfidenceRequest(
        heuristic_id=heuristic_id,
        positive=True,
    )
    pos_response = await storage_stub.UpdateHeuristicConfidence(pos_request)

    if not pos_response.success:
        print(f"ERROR: Positive feedback failed: {pos_response.error}")
        return False

    print(f"  Old confidence: {pos_response.old_confidence:.3f}")
    print(f"  New confidence: {pos_response.new_confidence:.3f}")
    print(f"  Delta: {pos_response.delta:+.3f}")

    expected_after_positive = min(1.0, initial_confidence + 0.1)  # lr * delta = 0.1 * 1.0
    if abs(pos_response.new_confidence - expected_after_positive) > 0.001:
        print(f"ERROR: Expected confidence {expected_after_positive}, got {pos_response.new_confidence}")
        return False
    print("  [OK] Positive feedback increased confidence correctly")

    # Step 3: Send negative feedback and verify confidence decreases
    print("\n--- Step 3: Negative feedback ---")
    neg_request = memory_pb2.UpdateHeuristicConfidenceRequest(
        heuristic_id=heuristic_id,
        positive=False,
    )
    neg_response = await storage_stub.UpdateHeuristicConfidence(neg_request)

    if not neg_response.success:
        print(f"ERROR: Negative feedback failed: {neg_response.error}")
        return False

    print(f"  Old confidence: {neg_response.old_confidence:.3f}")
    print(f"  New confidence: {neg_response.new_confidence:.3f}")
    print(f"  Delta: {neg_response.delta:+.3f}")

    # After +positive and +negative, should be back to 0.5
    expected_after_negative = expected_after_positive - 0.1  # lr * delta = 0.1 * -1.0
    if abs(neg_response.new_confidence - expected_after_negative) > 0.001:
        print(f"ERROR: Expected confidence {expected_after_negative}, got {neg_response.new_confidence}")
        return False
    print("  [OK] Negative feedback decreased confidence correctly")

    # Step 4: Test clamping at 0 (multiple negative feedbacks)
    print("\n--- Step 4: Test lower bound clamping ---")

    # Set confidence to low value
    await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=heuristic_id,
            positive=False,
            learning_rate=0.5,  # Big decrease
        )
    )

    # Try to go below zero
    clamp_response = await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=heuristic_id,
            positive=False,
            learning_rate=1.0,  # Try to drop by 1.0
        )
    )

    if not clamp_response.success:
        print(f"ERROR: Clamp test failed: {clamp_response.error}")
        return False

    print(f"  Old confidence: {clamp_response.old_confidence:.3f}")
    print(f"  New confidence: {clamp_response.new_confidence:.3f}")

    if clamp_response.new_confidence < 0.0:
        print(f"ERROR: Confidence went below 0!")
        return False
    print(f"  [OK] Confidence clamped at lower bound (0.0)")

    # Step 5: Test clamping at 1 (multiple positive feedbacks)
    print("\n--- Step 5: Test upper bound clamping ---")

    # Boost confidence high
    await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=heuristic_id,
            positive=True,
            learning_rate=1.0,  # Big increase
        )
    )

    # Try to go above 1
    upper_clamp_response = await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=heuristic_id,
            positive=True,
            learning_rate=1.0,  # Try to add 1.0
        )
    )

    if not upper_clamp_response.success:
        print(f"ERROR: Upper clamp test failed: {upper_clamp_response.error}")
        return False

    print(f"  Old confidence: {upper_clamp_response.old_confidence:.3f}")
    print(f"  New confidence: {upper_clamp_response.new_confidence:.3f}")

    if upper_clamp_response.new_confidence > 1.0:
        print(f"ERROR: Confidence went above 1!")
        return False
    print(f"  [OK] Confidence clamped at upper bound (1.0)")

    # =========================================================================
    # TD Learning with Prediction Error (new tests)
    # =========================================================================

    # Create a fresh heuristic for TD tests
    print("\n--- Step 6: Create heuristic for TD learning tests ---")
    td_heuristic_id = str(uuid.uuid4())
    initial_confidence = 0.5

    td_heuristic = memory_pb2.Heuristic(
        id=td_heuristic_id,
        name="TD Prediction Test Heuristic",
        condition_text="test td prediction error",
        effects_json='{"action": "td_test"}',
        confidence=initial_confidence,
        origin="test",
    )

    request = memory_pb2.StoreHeuristicRequest(
        heuristic=td_heuristic,
        generate_embedding=True,
    )
    response = await storage_stub.StoreHeuristic(request)
    if not response.success:
        print(f"ERROR: Failed to store TD heuristic: {response.error}")
        return False
    print(f"  Created heuristic: {td_heuristic_id}")
    print(f"  Initial confidence: {initial_confidence}")

    # Step 7: Test TD learning - correct prediction (small update)
    print("\n--- Step 7: TD Learning - Correct prediction (small update) ---")
    # We predicted 0.9 success, and it succeeded (actual=1.0)
    # td_error = 1.0 - 0.9 = 0.1 → small positive update
    td_correct_response = await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=td_heuristic_id,
            positive=True,  # actual = 1.0 (success)
            learning_rate=0.5,  # Use larger rate to make effect visible
            predicted_success=0.9,  # We predicted 90% success
        )
    )

    if not td_correct_response.success:
        print(f"ERROR: TD correct prediction failed: {td_correct_response.error}")
        return False

    print(f"  Prediction: 0.9, Actual: 1.0 (success)")
    print(f"  TD error: {td_correct_response.td_error:.3f}")
    print(f"  Old confidence: {td_correct_response.old_confidence:.3f}")
    print(f"  New confidence: {td_correct_response.new_confidence:.3f}")
    print(f"  Delta: {td_correct_response.delta:+.3f}")

    # td_error should be 0.1, delta should be 0.5 * 0.1 = 0.05
    expected_td_error = 1.0 - 0.9  # 0.1
    expected_delta = 0.5 * expected_td_error  # 0.05
    if abs(td_correct_response.td_error - expected_td_error) > 0.001:
        print(f"ERROR: Expected td_error {expected_td_error:.3f}, got {td_correct_response.td_error:.3f}")
        return False
    if abs(td_correct_response.delta - expected_delta) > 0.001:
        print(f"ERROR: Expected delta {expected_delta:.3f}, got {td_correct_response.delta:.3f}")
        return False
    print("  [OK] Correct prediction resulted in small positive update")

    # Step 8: Test TD learning - wrong prediction (large update)
    print("\n--- Step 8: TD Learning - Surprising success (large update) ---")
    # We predicted 0.1 success (pessimistic), but it succeeded (actual=1.0)
    # td_error = 1.0 - 0.1 = 0.9 → large positive update (surprise!)
    td_surprise_response = await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=td_heuristic_id,
            positive=True,  # actual = 1.0 (success)
            learning_rate=0.5,
            predicted_success=0.1,  # We predicted only 10% success
        )
    )

    if not td_surprise_response.success:
        print(f"ERROR: TD surprise success failed: {td_surprise_response.error}")
        return False

    print(f"  Prediction: 0.1, Actual: 1.0 (success)")
    print(f"  TD error: {td_surprise_response.td_error:.3f}")
    print(f"  Old confidence: {td_surprise_response.old_confidence:.3f}")
    print(f"  New confidence: {td_surprise_response.new_confidence:.3f}")
    print(f"  Delta: {td_surprise_response.delta:+.3f}")

    # td_error should be 0.9, delta should be 0.5 * 0.9 = 0.45
    expected_td_error = 1.0 - 0.1  # 0.9
    expected_delta = 0.5 * expected_td_error  # 0.45
    if abs(td_surprise_response.td_error - expected_td_error) > 0.001:
        print(f"ERROR: Expected td_error {expected_td_error:.3f}, got {td_surprise_response.td_error:.3f}")
        return False
    if abs(td_surprise_response.delta - expected_delta) > 0.001:
        print(f"ERROR: Expected delta {expected_delta:.3f}, got {td_surprise_response.delta:.3f}")
        return False
    print("  [OK] Surprising success resulted in large positive update")

    # Step 9: Test TD learning - surprising failure (large negative update)
    print("\n--- Step 9: TD Learning - Surprising failure (large negative update) ---")
    # We predicted 0.9 success (optimistic), but it failed (actual=0.0)
    # td_error = 0.0 - 0.9 = -0.9 → large negative update (surprise!)
    td_failure_response = await storage_stub.UpdateHeuristicConfidence(
        memory_pb2.UpdateHeuristicConfidenceRequest(
            heuristic_id=td_heuristic_id,
            positive=False,  # actual = 0.0 (failure)
            learning_rate=0.5,
            predicted_success=0.9,  # We predicted 90% success
        )
    )

    if not td_failure_response.success:
        print(f"ERROR: TD surprise failure failed: {td_failure_response.error}")
        return False

    print(f"  Prediction: 0.9, Actual: 0.0 (failure)")
    print(f"  TD error: {td_failure_response.td_error:.3f}")
    print(f"  Old confidence: {td_failure_response.old_confidence:.3f}")
    print(f"  New confidence: {td_failure_response.new_confidence:.3f}")
    print(f"  Delta: {td_failure_response.delta:+.3f}")

    # td_error should be -0.9, delta should be 0.5 * -0.9 = -0.45
    expected_td_error = 0.0 - 0.9  # -0.9
    expected_delta = 0.5 * expected_td_error  # -0.45
    if abs(td_failure_response.td_error - expected_td_error) > 0.001:
        print(f"ERROR: Expected td_error {expected_td_error:.3f}, got {td_failure_response.td_error:.3f}")
        return False
    if abs(td_failure_response.delta - expected_delta) > 0.001:
        print(f"ERROR: Expected delta {expected_delta:.3f}, got {td_failure_response.delta:.3f}")
        return False
    print("  [OK] Surprising failure resulted in large negative update")

    # Cleanup
    await channel.close()

    print("\n" + "=" * 60)
    print("SUCCESS: TD Learning working correctly!")
    print("  - Simple mode (no prediction): Works")
    print("  - TD mode (with prediction): Works")
    print("  - Learn more from surprises: Works")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
