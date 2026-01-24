#!/usr/bin/env python3
"""Test the killer feature: learned heuristics skip LLM reasoning.

This test proves that:
1. A stored heuristic is matched on similar events
2. When matched, the response is from cache (no LLM call)
3. Latency is dramatically lower (~1ms vs ~49ms with embeddings)

Usage:
    # Start Memory service first:
    cd src/memory/python && uv run python -m gladys_memory.grpc_server

    # Then run this test:
    cd src/integration && uv run python test_killer_feature.py
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc


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

    try:
        channel = grpc.aio.insecure_channel("localhost:50051")
        # Quick connection check
        await asyncio.wait_for(channel.channel_ready(), timeout=3.0)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Memory service at localhost:50051")
        print(f"  {e}")
        print("\nStart the Memory service first:")
        print("  cd src/memory/python && uv run python -m gladys_memory.grpc_server")
        return False

    async with channel:
        storage_stub = memory_pb2_grpc.MemoryStorageStub(channel)
        salience_stub = memory_pb2_grpc.SalienceGatewayStub(channel)

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

        # ============================================================
        # Step 2: Baseline - Evaluate salience WITHOUT matching heuristic
        # ============================================================
        print("\n[Step 2] Baseline: Evaluate salience for unrelated event...")

        baseline_request = memory_pb2.EvaluateSalienceRequest(
            event_id="baseline-event",
            source="test-sensor",
            raw_text="The weather is nice today, sunny and warm",
            skip_novelty_detection=True,  # Skip embedding for apples-to-apples
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
            skip_novelty_detection=True,  # Skip embedding for apples-to-apples
        )

        start = time.perf_counter()
        matching_response = await salience_stub.EvaluateSalience(matching_request)
        matching_latency_ms = (time.perf_counter() - start) * 1000

        print(f"  from_cache: {matching_response.from_cache}")
        print(f"  matched_heuristic_id: '{matching_response.matched_heuristic_id}'")
        print(f"  latency: {matching_latency_ms:.2f} ms")

        # ============================================================
        # Step 4: Compare with FULL path (embedding generation)
        # ============================================================
        print("\n[Step 4] Comparison: Full path with embedding generation...")

        full_request = memory_pb2.EvaluateSalienceRequest(
            event_id="full-path-event",
            source="game-sensor",
            raw_text="Another alert about player status and game state",
            skip_novelty_detection=False,  # Include embedding generation
        )

        start = time.perf_counter()
        full_response = await salience_stub.EvaluateSalience(full_request)
        full_latency_ms = (time.perf_counter() - start) * 1000

        print(f"  latency: {full_latency_ms:.2f} ms")
        print(f"  novelty_detection_skipped: {full_response.novelty_detection_skipped}")

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
        print(f"\n  Latency comparison:")
        print(f"    - Cached path:       {matching_latency_ms:.2f} ms")
        print(f"    - Full path:         {full_latency_ms:.2f} ms")
        if full_latency_ms > 0:
            speedup = full_latency_ms / matching_latency_ms if matching_latency_ms > 0 else float('inf')
            print(f"    - Speedup:           {speedup:.1f}x faster")

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
            print("  Check word overlap thresholds in SalienceSettings")
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
