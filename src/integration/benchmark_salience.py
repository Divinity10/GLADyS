#!/usr/bin/env python3
"""Benchmark: Python vs Rust SalienceGateway performance.

Prerequisites:
  docker-compose up -d  (from this directory)

This script:
1. Sends N salience evaluation requests to Python (50051)
2. Sends N salience evaluation requests to Rust (50052)
3. Compares latency statistics
"""

import asyncio
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


PYTHON_ADDRESS = "localhost:50051"
RUST_ADDRESS = "localhost:50052"
NUM_REQUESTS = 100


async def benchmark_service(address: str, name: str, num_requests: int) -> list[float]:
    """Benchmark salience evaluation latency for a service."""
    channel = grpc.aio.insecure_channel(address)
    stub = memory_pb2_grpc.SalienceGatewayStub(channel)

    latencies = []

    # Warm-up request
    try:
        await stub.EvaluateSalience(memory_pb2.EvaluateSalienceRequest(
            event_id="warmup",
            source="benchmark",
            raw_text="warmup request",
        ))
    except grpc.RpcError as e:
        print(f"[FAIL] {name} not available at {address}: {e.code()}")
        await channel.close()
        return []

    # Benchmark requests
    for i in range(num_requests):
        request = memory_pb2.EvaluateSalienceRequest(
            event_id=str(uuid4()),
            source="benchmark",
            raw_text=f"Test event {i} with some keywords like danger and threat",
        )

        start = time.perf_counter()
        response = await stub.EvaluateSalience(request)
        end = time.perf_counter()

        if response.error:
            print(f"[WARN] Request {i} error: {response.error}")
        else:
            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

    await channel.close()
    return latencies


def print_stats(name: str, latencies: list[float]) -> None:
    """Print latency statistics."""
    if not latencies:
        print(f"{name}: No data")
        return

    print(f"\n{name} ({len(latencies)} requests):")
    print(f"  Min:    {min(latencies):.3f} ms")
    print(f"  Max:    {max(latencies):.3f} ms")
    print(f"  Mean:   {statistics.mean(latencies):.3f} ms")
    print(f"  Median: {statistics.median(latencies):.3f} ms")
    print(f"  Stdev:  {statistics.stdev(latencies):.3f} ms" if len(latencies) > 1 else "")
    print(f"  p95:    {sorted(latencies)[int(len(latencies) * 0.95)]:.3f} ms")
    print(f"  p99:    {sorted(latencies)[int(len(latencies) * 0.99)]:.3f} ms")


async def main() -> int:
    """Run benchmarks."""
    print("=" * 60)
    print("GLADyS Salience Gateway Benchmark: Python vs Rust")
    print("=" * 60)
    print(f"\nRequests per service: {NUM_REQUESTS}")

    # Benchmark Python
    print(f"\nBenchmarking Python ({PYTHON_ADDRESS})...")
    python_latencies = await benchmark_service(PYTHON_ADDRESS, "Python", NUM_REQUESTS)

    # Benchmark Rust
    print(f"Benchmarking Rust ({RUST_ADDRESS})...")
    rust_latencies = await benchmark_service(RUST_ADDRESS, "Rust", NUM_REQUESTS)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print_stats("Python SalienceGateway", python_latencies)
    print_stats("Rust SalienceGateway", rust_latencies)

    # Comparison
    if python_latencies and rust_latencies:
        python_mean = statistics.mean(python_latencies)
        rust_mean = statistics.mean(rust_latencies)
        speedup = python_mean / rust_mean if rust_mean > 0 else 0

        print(f"\n{'=' * 60}")
        print("COMPARISON")
        print("=" * 60)
        print(f"  Python mean: {python_mean:.3f} ms")
        print(f"  Rust mean:   {rust_mean:.3f} ms")
        print(f"  Speedup:     {speedup:.2f}x {'(Rust faster)' if speedup > 1 else '(Python faster)'}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
