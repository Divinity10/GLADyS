#!/usr/bin/env python3
"""Benchmark: Python vs Rust SalienceGateway performance.

Prerequisites:
  docker-compose up -d  (from this directory)

This script compares:
1. Apples-to-apples: Python (cached heuristics + word-overlap) vs Rust (same)
2. Full Python path (DB + embeddings + novelty) vs Rust (cached + word-overlap)

The apples-to-apples comparison uses the skip_novelty_detection proto field
to skip embedding generation in Python and enable heuristic caching.

Path verification: Each response includes novelty_detection_skipped field
to confirm which code path was actually used. The summary verifies:
- Python cached: should show 100% novelty skipped
- Python full: should show 0% novelty skipped
- Rust: always shows 100% (never does novelty detection)
"""

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

import grpc

# Add orchestrator to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

from gladys_orchestrator.generated import memory_pb2
from gladys_orchestrator.generated import memory_pb2_grpc


PYTHON_ADDRESS = os.environ.get("PYTHON_ADDRESS", "localhost:50051")
RUST_ADDRESS = os.environ.get("RUST_ADDRESS", "localhost:50052")
NUM_REQUESTS = int(os.environ.get("BENCHMARK_REQUESTS", "100"))


class BenchmarkResult:
    """Result from benchmark run including latencies and path verification."""
    def __init__(self, latencies: list[float], novelty_skipped_count: int, total_count: int):
        self.latencies = latencies
        self.novelty_skipped_count = novelty_skipped_count
        self.total_count = total_count

    @property
    def novelty_skipped_pct(self) -> float:
        return (self.novelty_skipped_count / self.total_count * 100) if self.total_count > 0 else 0


async def benchmark_service(
    address: str,
    name: str,
    num_requests: int,
    skip_novelty: bool = False,
) -> BenchmarkResult:
    """Benchmark salience evaluation latency for a service."""
    channel = grpc.aio.insecure_channel(address)
    stub = memory_pb2_grpc.SalienceGatewayStub(channel)

    latencies = []
    novelty_skipped_count = 0
    total_count = 0

    # Warm-up request
    try:
        await stub.EvaluateSalience(memory_pb2.EvaluateSalienceRequest(
            event_id="warmup",
            source="benchmark",
            raw_text="warmup request",
            skip_novelty_detection=skip_novelty,
        ))
    except grpc.RpcError as e:
        print(f"[FAIL] {name} not available at {address}: {e.code()}")
        await channel.close()
        return BenchmarkResult([], 0, 0)

    # Benchmark requests
    for i in range(num_requests):
        request = memory_pb2.EvaluateSalienceRequest(
            event_id=str(uuid4()),
            source="benchmark",
            raw_text=f"Test event {i} with some keywords like danger and threat",
            skip_novelty_detection=skip_novelty,
        )

        start = time.perf_counter()
        response = await stub.EvaluateSalience(request)
        end = time.perf_counter()

        total_count += 1
        if response.novelty_detection_skipped:
            novelty_skipped_count += 1

        if response.error:
            print(f"[WARN] Request {i} error: {response.error}")
        else:
            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

    await channel.close()
    return BenchmarkResult(latencies, novelty_skipped_count, total_count)


def print_stats(name: str, result: BenchmarkResult) -> None:
    """Print latency statistics and path verification."""
    if not result.latencies:
        print(f"{name}: No data")
        return

    latencies = result.latencies
    print(f"\n{name} ({len(latencies)} requests):")
    print(f"  Min:    {min(latencies):.3f} ms")
    print(f"  Max:    {max(latencies):.3f} ms")
    print(f"  Mean:   {statistics.mean(latencies):.3f} ms")
    print(f"  Median: {statistics.median(latencies):.3f} ms")
    if len(latencies) > 1:
        print(f"  Stdev:  {statistics.stdev(latencies):.3f} ms")
    print(f"  p95:    {sorted(latencies)[int(len(latencies) * 0.95)]:.3f} ms")
    print(f"  p99:    {sorted(latencies)[int(len(latencies) * 0.99)]:.3f} ms")
    # Path verification - show AFTER timing stats
    print(f"  Path:   novelty_skipped={result.novelty_skipped_count}/{result.total_count} ({result.novelty_skipped_pct:.0f}%)")


def print_comparison(python_result: BenchmarkResult, rust_result: BenchmarkResult, mode: str) -> None:
    """Print comparison between Python and Rust."""
    if not python_result.latencies or not rust_result.latencies:
        return

    python_mean = statistics.mean(python_result.latencies)
    rust_mean = statistics.mean(rust_result.latencies)
    speedup = python_mean / rust_mean if rust_mean > 0 else 0

    print(f"\n  Python mean: {python_mean:.3f} ms")
    print(f"  Rust mean:   {rust_mean:.3f} ms")
    print(f"  Speedup:     {speedup:.2f}x {'(Rust faster)' if speedup > 1 else '(Python faster)'}")


async def main() -> int:
    """Run benchmarks."""
    print("=" * 70)
    print("GLADyS Salience Gateway Benchmark: Python vs Rust")
    print("=" * 70)
    print(f"\nRequests per service: {NUM_REQUESTS}")
    print(f"Python address: {PYTHON_ADDRESS}")
    print(f"Rust address: {RUST_ADDRESS}")

    # =========================================================================
    # Benchmark 1: Apples-to-apples (both using cached heuristics, word-overlap)
    # Run this FIRST to warm up Python's heuristic cache
    # =========================================================================
    print("\n" + "=" * 70)
    print("BENCHMARK 1: Apples-to-Apples (cached heuristics, word-overlap)")
    print("  Python: cached heuristics + word-overlap (skip_novelty=true)")
    print("  Rust:   cached heuristics + word-overlap")
    print("=" * 70)

    print(f"\nBenchmarking Python cached path ({PYTHON_ADDRESS})...")
    python_cached = await benchmark_service(PYTHON_ADDRESS, "Python (cached)", NUM_REQUESTS, skip_novelty=True)

    print(f"Benchmarking Rust ({RUST_ADDRESS})...")
    rust_result = await benchmark_service(RUST_ADDRESS, "Rust", NUM_REQUESTS)

    print_stats("Python (cached + word-overlap)", python_cached)
    print_stats("Rust (cached + word-overlap)", rust_result)

    print("\n--- Comparison (apples-to-apples) ---")
    print_comparison(python_cached, rust_result, "cached")

    # =========================================================================
    # Benchmark 2: Full Python path (DB query + embeddings + novelty)
    # =========================================================================
    print("\n" + "=" * 70)
    print("BENCHMARK 2: Full Python Path")
    print("  Python: DB query + word-overlap + embedding-based novelty detection")
    print("  Rust:   (same as benchmark 1)")
    print("=" * 70)

    print(f"\nBenchmarking Python full path ({PYTHON_ADDRESS})...")
    python_full = await benchmark_service(PYTHON_ADDRESS, "Python (full)", NUM_REQUESTS, skip_novelty=False)

    print_stats("Python (full: DB + word-overlap + embeddings)", python_full)
    print_stats("Rust (cached + word-overlap)", rust_result)

    print("\n--- Comparison (full vs apples-to-apples) ---")
    print_comparison(python_full, rust_result, "full")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if python_full.latencies and python_cached.latencies and rust_result.latencies:
        rust_mean = statistics.mean(rust_result.latencies)
        python_cached_mean = statistics.mean(python_cached.latencies)
        python_full_mean = statistics.mean(python_full.latencies)

        cached_speedup = python_cached_mean / rust_mean
        full_speedup = python_full_mean / rust_mean

        print(f"\n  Apples-to-apples (both cached + word-overlap): {cached_speedup:.1f}x speedup")
        print(f"  Full comparison (Py DB+embeddings vs Rust):    {full_speedup:.1f}x speedup")
        print(f"\n  Rust mean latency:               {rust_mean:.2f} ms")
        print(f"  Python cached mean latency:      {python_cached_mean:.2f} ms")
        print(f"  Python full mean latency:        {python_full_mean:.2f} ms")
        print(f"\n  Embedding/novelty overhead:      ~{python_full_mean - python_cached_mean:.1f} ms")
        print(f"  Python runtime overhead:         ~{python_cached_mean - rust_mean:.1f} ms")

        # Path verification summary
        print(f"\n  Path verification:")
        print(f"    Python cached: novelty_skipped={python_cached.novelty_skipped_count}/{python_cached.total_count}")
        print(f"    Python full:   novelty_skipped={python_full.novelty_skipped_count}/{python_full.total_count}")
        print(f"    Rust:          novelty_skipped={rust_result.novelty_skipped_count}/{rust_result.total_count}")

        # Verify expected behavior
        if python_cached.novelty_skipped_pct < 100:
            print(f"\n  WARNING: Python cached path did NOT skip novelty for all requests!")
            print(f"           Expected 100%, got {python_cached.novelty_skipped_pct:.0f}%")
            print(f"           Cache may not be working - check logs!")
        if python_full.novelty_skipped_pct > 0:
            print(f"\n  WARNING: Python full path skipped novelty unexpectedly!")
            print(f"           Expected 0%, got {python_full.novelty_skipped_pct:.0f}%")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
