#!/usr/bin/env python3
"""Test semantic generalization: heuristics match events with different words but same meaning.

This test proves that:
1. A stored heuristic is matched on semantically similar events even if words differ.
2. Embeddings capture the underlying concept (e.g., fire/emergency).
3. The Rust fast path correctly delegates to semantic matching when enabled.

Usage:
    python scripts/docker.py test test_generalization.py  # DOCKER
"""

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc

# Require explicit environment - no defaults to prevent wrong-environment testing
PYTHON_ADDRESS = os.environ.get("PYTHON_ADDRESS")
RUST_ADDRESS = os.environ.get("RUST_ADDRESS")
if not PYTHON_ADDRESS or not RUST_ADDRESS:
    print("ERROR: PYTHON_ADDRESS and RUST_ADDRESS environment variables required.")
    print("Use wrapper scripts to run tests:")
    print("  python scripts/docker.py test test_generalization.py  # DOCKER")
    sys.exit(1)


async def run_test():
    """Run the semantic generalization test."""
    try:
        # Try gladys_memory directly first (local structure)
        from gladys_memory import memory_pb2, memory_pb2_grpc
    except ImportError:
        try:
            # Fallback to orchestrator's generated stubs
            from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
        except ImportError:
            print("ERROR: Memory proto stubs not available")
            print("Run: make proto")
            return False

    print("=" * 70)
    print("SEMANTIC GENERALIZATION TEST: Meanings match across lexical gaps")
    print("=" * 70)
    print(f"\n  Python (storage):  {PYTHON_ADDRESS}")
    print(f"  Rust (salience):   {RUST_ADDRESS}")

    # Connect to Python (storage)
    try:
        python_channel = grpc.aio.insecure_channel(PYTHON_ADDRESS)
        await asyncio.wait_for(python_channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Python Memory service at {PYTHON_ADDRESS}")
        print(f"  {e}")
        return False

    # Connect to Rust (salience)
    try:
        rust_channel = grpc.aio.insecure_channel(RUST_ADDRESS)
        await asyncio.wait_for(rust_channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Rust fast path at {RUST_ADDRESS}")
        print(f"  {e}")
        await python_channel.close()
        return False

    async with python_channel, rust_channel:
        storage_stub = memory_pb2_grpc.MemoryStorageStub(python_channel)
        salience_stub = memory_pb2_grpc.SalienceGatewayStub(rust_channel)

        # ============================================================
        # Step 1: Store a heuristic directly
        # ============================================================
        print("\n[Step 1] Storing a test heuristic for 'Mike Sarcasm'...")

        unique_id = str(uuid.uuid4())
        heuristic_id = str(uuid.uuid4())
        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name="Social: Mike Sarcasm (Test)",
            # Pure semantic condition without prefix to prove generalization
            condition_text="email from Mike Mulcahy about killing",
            effects_json='{"type": "suggestion", "message": "Haha, classic Mike."}',
            confidence=0.9,  
            origin="test",
            origin_id="generalization-test",
            created_at_ms=int(time.time() * 1000),
        )

        store_request = memory_pb2.StoreHeuristicRequest(
            heuristic=heuristic,
            generate_embedding=True,
        )

        store_response = await storage_stub.StoreHeuristic(store_request)

        if not store_response.success:
            print(f"  ERROR: Failed to store heuristic: {store_response.error}")
            return False

        print(f"  Stored heuristic: id={store_response.heuristic_id}")
        print(f"  Condition: '{heuristic.condition_text}'")

        # ============================================================
        # Step 2: Baseline - Evaluate salience for unrelated event
        # ============================================================
        print("\n[Step 2] Baseline: Evaluate salience for unrelated event...")

        baseline_request = memory_pb2.EvaluateSalienceRequest(
            event_id=f"baseline-{unique_id}",
            source="", 
            raw_text="The weather is nice today, perfect for a walk.",
        )

        baseline_response = await salience_stub.EvaluateSalience(baseline_request)

        print(f"  from_cache: {baseline_response.from_cache}")
        print(f"  matched_heuristic_id: '{baseline_response.matched_heuristic_id}'")

        if baseline_response.from_cache:
            print(f"  WARNING: Baseline unexpectedly matched heuristic: {baseline_response.matched_heuristic_id}")

        # ============================================================
        # Step 3: THE TEST - Evaluate salience for semantically similar event
        # ============================================================
        print("\n[Step 3] THE TEST: Evaluate salience for semantically similar event...")
        event_text = "Mike sent a message about murdering the person next door."
        print(f"  Event text: '{event_text}'")

        matching_request = memory_pb2.EvaluateSalienceRequest(
            event_id=f"matching-{unique_id}",
            source="", 
            raw_text=event_text,
        )

        # Give it a moment just in case embedding generation is slightly async (usually isn't)
        await asyncio.sleep(0.5)

        start = time.perf_counter()
        matching_response = await salience_stub.EvaluateSalience(matching_request)
        latency_ms = (time.perf_counter() - start) * 1000

        print(f"  from_cache: {matching_response.from_cache}")
        print(f"  matched_heuristic_id: '{matching_response.matched_heuristic_id}'")
        print(f"  latency: {latency_ms:.2f} ms")

        # ============================================================
        # Results
        # ============================================================
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        # Check if heuristic matched
        heuristic_matched = (
            matching_response.from_cache and
            matching_response.matched_heuristic_id == heuristic_id
        )

        print(f"\n  Heuristic matched:     {'YES' if heuristic_matched else 'NO'}")
        print(f"  Baseline matched:      {'YES' if baseline_response.from_cache else 'NO'}")
        print(f"  Latency:               {latency_ms:.2f} ms")

        print("\n" + "=" * 70)

        if heuristic_matched and not baseline_response.from_cache:
            print("SUCCESS: Semantic generalization works!")
            print("  - Heuristic matched event with different words but same meaning")
            print("  - Unrelated event did NOT match")
            print("=" * 70)
            return True
        else:
            print("FAILED: Semantic generalization failed")
            if not heuristic_matched:
                print("  - The similar event did NOT trigger the heuristic.")
                print("  - Possible cause: Cosine similarity threshold (0.7) not met.")
            if baseline_response.from_cache:
                print("  - The baseline event WRONGLY triggered a heuristic.")
            print("=" * 70)
            return False


async def main():
    success = await run_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
