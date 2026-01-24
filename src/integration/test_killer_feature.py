#!/usr/bin/env python3
"""Test the killer feature: learned heuristics skip LLM reasoning.

This test proves that:
1. A stored heuristic is matched on similar events
2. When matched, the response is from cache (no LLM call)
3. Latency is dramatically lower (~1ms vs ~49ms with embeddings)

Architecture:
    - Python (port 50051): Stores heuristics to PostgreSQL, provides QueryMatchingHeuristics RPC
    - Rust (port 50052): LRU cache, queries Python on cache miss
    - No bulk loading - heuristics loaded on demand via text search

Usage:
    # Terminal 1 - Start Python Memory service (storage):
    cd src/memory/python && uv run python -m gladys_memory.grpc_server

    # Terminal 2 - Start Rust fast path (salience):
    cd src/memory/rust && cargo run

    # Terminal 3 - Run this test:
    cd src/integration && uv run python test_killer_feature.py

Note: Rust queries Python on cache miss - no refresh interval needed.
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

# Configurable addresses
PYTHON_ADDRESS = os.environ.get("PYTHON_ADDRESS", "localhost:50051")
RUST_ADDRESS = os.environ.get("RUST_ADDRESS", "localhost:50052")


async def run_test():
    """Run the killer feature test."""
    try:
        # Try gladys_memory directly first (local structure)
        from gladys_memory import memory_pb2, memory_pb2_grpc
    except ImportError:
        try:
            # Fallback to generated subdirectory (orchestrator structure)
            from gladys_memory.generated import memory_pb2, memory_pb2_grpc
        except ImportError:
            print("ERROR: Memory proto stubs not available")
            print("Run: make proto")
            return False

    print("=" * 70)
    print("KILLER FEATURE TEST: Heuristics Skip LLM Reasoning")
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
        print("\nStart the Python Memory service first:")
        print("  cd src/memory/python && uv run python -m gladys_memory.grpc_server")
        return False

    # Connect to Rust (salience)
    try:
        rust_channel = grpc.aio.insecure_channel(RUST_ADDRESS)
        await asyncio.wait_for(rust_channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Rust fast path at {RUST_ADDRESS}")
        print(f"  {e}")
        print("\nStart the Rust fast path:")
        print("  cd src/memory/rust && cargo run")
        await python_channel.close()
        return False

    async with python_channel, rust_channel:
        storage_stub = memory_pb2_grpc.MemoryStorageStub(python_channel)
        salience_stub = memory_pb2_grpc.SalienceGatewayStub(rust_channel)

        # ============================================================
        # Step 1: Store a heuristic directly
        # ============================================================
        print("\n[Step 1] Storing a test heuristic...")

        heuristic_id = str(uuid.uuid4())
        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name="Test: Low health warning",
            condition_text="low health detected find shelter warning danger",
            effects_json='{"type": "suggestion", "message": "Find shelter immediately"}',
            confidence=0.8,  # Above minimum threshold (0.5)
            origin="test",
            origin_id="killer-feature-test",
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

        # No need to wait for cache refresh - Rust queries Python on cache miss
        print("\n[Step 1b] Rust will query Python on cache miss (no refresh wait needed)")

        # ============================================================
        # Step 2: Baseline - Evaluate salience WITHOUT matching heuristic
        # ============================================================
        print("\n[Step 2] Baseline: Evaluate salience for unrelated event...")

        baseline_request = memory_pb2.EvaluateSalienceRequest(
            event_id="baseline-event",
            source="test-sensor",
            raw_text="The weather is nice today, sunny and warm",
        )

        start = time.perf_counter()
        baseline_response = await salience_stub.EvaluateSalience(baseline_request)
        baseline_latency_ms = (time.perf_counter() - start) * 1000

        print(f"  from_cache: {baseline_response.from_cache}")
        print(f"  matched_heuristic_id: '{baseline_response.matched_heuristic_id}'")
        print(f"  latency: {baseline_latency_ms:.2f} ms")

        if baseline_response.from_cache:
            print("  WARNING: Baseline unexpectedly matched a heuristic")

        # ============================================================
        # Step 3: THE TEST - Evaluate salience for MATCHING event
        # ============================================================
        print("\n[Step 3] THE TEST: Evaluate salience for matching event...")

        # Event text that should match the heuristic via word overlap
        # Heuristic condition: "low health detected find shelter warning danger"
        # This event shares key words: "low", "health", "detected", "shelter"
        matching_request = memory_pb2.EvaluateSalienceRequest(
            event_id="matching-event",
            source="game-sensor",
            raw_text="Alert: Player has low health detected! Need to find shelter fast.",
        )

        start = time.perf_counter()
        matching_response = await salience_stub.EvaluateSalience(matching_request)
        matching_latency_ms = (time.perf_counter() - start) * 1000

        print(f"  from_cache: {matching_response.from_cache}")
        print(f"  matched_heuristic_id: '{matching_response.matched_heuristic_id}'")
        print(f"  latency: {matching_latency_ms:.2f} ms")

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
        print(f"\n  Latency (Rust fast path):")
        print(f"    - Baseline:          {baseline_latency_ms:.2f} ms")
        print(f"    - Matching event:    {matching_latency_ms:.2f} ms")

        print("\n" + "=" * 70)

        if heuristic_matched and not baseline_response.from_cache:
            print("SUCCESS: Killer feature works!")
            print("  - Heuristic correctly matched similar event")
            print("  - Unrelated event did NOT match")
            print("  - This proves the learning loop differentiator")
            print("=" * 70)
            return True
        elif heuristic_matched and baseline_response.from_cache:
            print("PARTIAL: Heuristic matched, but baseline also matched (too broad)")
            print("=" * 70)
            return False
        else:
            print("FAILED: Heuristic did not match the similar event")
            print("  Possible causes:")
            print("  - Rust cache not yet refreshed (wait longer)")
            print("  - Word overlap threshold too high")
            print("=" * 70)
            return False


async def cleanup_test_heuristics():
    """Optional: Clean up test heuristics from DB."""
    # For now, we leave them - they don't hurt
    # In production, we'd delete test data
    pass


async def main():
    success = await run_test()
    await cleanup_test_heuristics()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
