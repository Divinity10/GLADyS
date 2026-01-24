# GLADyS Performance Baseline

This document captures performance expectations, benchmark methodology, and operational guidance for the GLADyS system. It serves as a reference for understanding system behavior and knowing when to investigate performance issues.

## Overview

GLADyS uses a two-tier architecture for salience evaluation:

| Path | Implementation | Purpose |
|------|----------------|---------|
| **Fast path** | Rust, in-memory | Cache hits, known heuristics, recent events |
| **Slow path** | Python, PostgreSQL + pgvector | Cache misses, novel events, ML inference |

The fast path exists because the slow path cannot scale to real-time event processing.

## Configuration

Both paths are always running. The Orchestrator is configured to use one or the other via environment variable:

```yaml
# In src/integration/docker-compose.yml
environment:
  # Fast path (default) - use for production
  SALIENCE_MEMORY_ADDRESS: memory-rust:50052

  # Slow path - use for debugging or when cache isn't populated
  # SALIENCE_MEMORY_ADDRESS: memory-python:50051
```

| Path | Port | When to Use |
|------|------|-------------|
| Rust fast path | 50052 | Default. Production use. Cache is populated. |
| Python slow path | 50051 | Debugging. Cold start. Need full ML pipeline. |

**Note**: Both services expose the same `SalienceGateway` gRPC interface. Switching paths requires only changing the address - no code changes.

## Benchmark Results (2026-01-23)

### Test Conditions

- **Environment**: Docker containers on Windows (WSL2)
- **Hardware**: Development machine (not production representative)
- **Request pattern**: Sequential, 100 requests per service
- **Script**: `src/integration/benchmark_salience.py`
- **Path verification**: Each response includes `novelty_detection_skipped` field to confirm code path

### Apples-to-Apples Comparison (Cached Heuristics + Word Overlap)

Both paths using cached heuristics and word-overlap matching only.

| Metric | Rust (cached) | Python (cached) | Speedup |
|--------|---------------|-----------------|---------|
| Min | 0.7 ms | 0.9 ms | 1.3x |
| Median | 1.0 ms | 1.3 ms | 1.3x |
| Mean | 1.0 ms | 1.8 ms | **1.7x** |
| p95 | 1.7 ms | 2.1 ms | 1.3x |
| Max | 2.1 ms | 43.3 ms | 20x |

**Path verification**: Python cached 100/100 novelty skipped, Rust 100/100 novelty skipped.

### Full Python Path (DB Query + Embeddings + Novelty Detection)

| Metric | Rust | Python (full) | Speedup |
|--------|------|---------------|---------|
| Mean | 1.0 ms | 49.4 ms | **48.1x** |

**Path verification**: Python full 0/100 novelty skipped (embedding generation confirmed).

### Overhead Breakdown

| Component | Latency |
|-----------|---------|
| Rust (baseline) | 1.0 ms |
| Python runtime overhead | ~0.7 ms |
| Embedding/novelty overhead | ~47.6 ms |
| **Total Python (full)** | ~49.4 ms |

The 0.7ms "Python runtime overhead" represents the minimal difference between:
- Python async/await vs Rust async (tokio)
- Python gRPC (grpcio) vs Rust gRPC (tonic)
- Python object allocation vs Rust memory management

**Note**: With proper caching, Python and Rust are nearly equivalent for cached heuristic lookup (1.7x difference). The 48x speedup for full path is almost entirely due to embedding generation (~47.6ms).

### Important Caveats

**These results represent floor values, not realistic expectations.**

The benchmark measured:
- **Rust**: Cached heuristics, word-overlap matching, no embedding model
- **Python (cached)**: Cached heuristics, word-overlap matching, no embedding generation
- **Python (full)**: DB query for heuristics, word-overlap, embedding generation, novelty detection

Both paths will be slower in production with:
- More heuristics to iterate
- Lock contention under concurrent load
- Network latency variation

## Realistic Estimates

Based on expected production conditions:

| Path | Benchmark Floor | Realistic Estimate | Throughput |
|------|-----------------|-------------------|------------|
| Fast path (Rust) | ~1.0 ms | **3-10 ms** | 100-300 events/sec |
| Python cached (word-overlap) | ~1.8 ms | **5-15 ms** | 70-200 events/sec |
| Python full (embeddings) | ~49 ms | **80-150 ms** | ~7-12 events/sec |

### Key Insight

With proper caching, Python and Rust have nearly identical performance for cached heuristic lookup (~1.7x difference). The massive speedup (48x) only matters when:
- Embedding generation is required (novelty detection)
- Cache misses require DB queries

For most production traffic (cache hits), either path performs well.

### Why Paths Will Be Slower in Production

- **Network overhead**: gRPC over Docker network
- **Lock contention**: Under concurrent requests
- **Heuristic iteration**: More rules = more O(n) checking
- **Embedding generation**: ML model inference time (~47ms currently)

## Throughput Implications

| Scenario | Rust | Python Cached | Python Full | Notes |
|----------|------|---------------|-------------|-------|
| Benchmark floor | ~1000/sec | ~560/sec | ~20/sec | Sequential, optimal |
| Realistic estimate | 100-300/sec | 70-200/sec | 7-12/sec | Planning assumption |
| Under load | 50-150/sec | 40-100/sec | 5-10/sec | Degraded but functional |

**Key insight**: The fast path advantage is primarily about **avoiding embedding generation**, not raw runtime performance. When both use cached heuristics, the speedup is only 1.7x. The 48x speedup for full path is almost entirely embedding overhead.

## What to Monitor

### Latency Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `salience_evaluation_duration_ms` | Rust/Python services | p95 > 50ms (fast), p95 > 500ms (slow) |
| `grpc_request_duration_ms` | All gRPC calls | p95 > 100ms |
| `cache_hit_rate` | Rust fast path | < 80% (indicates cache misses) |

### Throughput Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `events_per_second` | Orchestrator | Sustained < 50/sec under expected load |
| `queue_depth` | Event queue | > 100 events backlogged |
| `dropped_events` | Orchestrator | Any non-zero value |

### Resource Metrics

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| CPU usage | Container stats | Sustained > 80% |
| Memory usage | Container stats | > 90% of limit |
| PostgreSQL connections | pg_stat | > 80% of pool |
| Lock contention time | Rust tracing | > 1ms average wait |

## Investigation Triggers

### When to Investigate

| Symptom | Likely Cause | First Steps |
|---------|--------------|-------------|
| Fast path p95 > 20ms | Lock contention or heuristic count | Check heuristic count, concurrent request rate |
| Slow path p95 > 500ms | DB query time or embedding generation | Check pg_stat, embedding model load |
| Cache hit rate < 70% | Too many novel events or cache too small | Review cache size, event patterns |
| Throughput < 50/sec | Bottleneck somewhere in pipeline | Profile end-to-end, identify slowest hop |

### Profiling Checklist

1. **Identify the bottleneck**: Is it fast path, slow path, or orchestrator?
2. **Check resource utilization**: CPU, memory, I/O, network
3. **Review recent changes**: New heuristics? More sensors? Code changes?
4. **Isolate components**: Run benchmark against individual services
5. **Check data growth**: How many events in DB? How many heuristics?

## Optimization Backlog

Ideas to try if profiling shows need (do not implement preemptively):

### Fast Path Optimizations

| Optimization | Complexity | Expected Gain | When to Consider |
|--------------|------------|---------------|------------------|
| Index heuristics by source | Low | 2-5x for source-filtered queries | > 100 heuristics |
| Sharded locks | Medium | Reduced contention | > 100 concurrent requests |
| Pre-compiled regex for keywords | Low | Marginal | Keyword matching is bottleneck |

### Slow Path Optimizations

| Optimization | Complexity | Expected Gain | When to Consider |
|--------------|------------|---------------|------------------|
| pgvector HNSW index | Low | O(log n) instead of O(n) | > 10k events |
| Embedding cache | Medium | Skip inference for repeated text | High text repetition |
| Query batching | Medium | Amortize connection overhead | High request rate |
| Read replicas | High | Scale read throughput | Single DB is bottleneck |

## Benchmark Reproduction

To reproduce the benchmark:

```bash
cd src/integration
docker compose up -d
# Wait for services to be healthy (~30s for embedding model load)
cd ../orchestrator
uv run python ../integration/benchmark_salience.py
```

To run with more requests:
```bash
BENCHMARK_REQUESTS=1000 uv run python ../integration/benchmark_salience.py
```

The benchmark runs two tests:
1. **Apples-to-apples**: Both paths with cached heuristics + word-overlap
2. **Full comparison**: Python full path (DB + embeddings) vs Rust

## Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-23 | Fixed benchmark with volume mounts - Python cached is 1.7x (not 20x) | Scott Mulcahy |
| 2026-01-23 | Added path verification (novelty_detection_skipped field) | Scott Mulcahy |
| 2026-01-23 | Added apples-to-apples comparison, overhead breakdown | Scott Mulcahy |
| 2026-01-22 | Initial baseline established | Scott Mulcahy |
