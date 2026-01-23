# GLADyS Performance Baseline

This document captures performance expectations, benchmark methodology, and operational guidance for the GLADyS system. It serves as a reference for understanding system behavior and knowing when to investigate performance issues.

## Overview

GLADyS uses a two-tier architecture for salience evaluation:

| Path | Implementation | Purpose |
|------|----------------|---------|
| **Fast path** | Rust, in-memory | Cache hits, known heuristics, recent events |
| **Slow path** | Python, PostgreSQL + pgvector | Cache misses, novel events, ML inference |

The fast path exists because the slow path cannot scale to real-time event processing.

## Benchmark Results (2026-01-22)

### Test Conditions

- **Environment**: Docker containers on Windows (WSL2)
- **Hardware**: Development machine (not production representative)
- **Data state**: Empty cache (Rust), empty database (Python)
- **Request pattern**: Sequential, 100 requests per service
- **Script**: `src/integration/benchmark_salience.py`

### Raw Results

| Metric | Fast Path (Rust) | Slow Path (Python) |
|--------|------------------|-------------------|
| Min | 0.7 ms | 31.2 ms |
| Median | 1.0 ms | 48.2 ms |
| Mean | 1.1 ms | 53.2 ms |
| p95 | 1.9 ms | 78.2 ms |
| Max | 2.8 ms | 303.5 ms |

### Important Caveats

**These results represent floor values, not realistic expectations.**

The benchmark measured:
- **Rust**: Empty cache, no heuristics to iterate, no lock contention
- **Python**: Empty database, minimal query time, no vector comparisons

Both paths will be slower in production with real data and load.

## Realistic Estimates

Based on expected production conditions:

| Path | Benchmark Floor | Realistic Estimate | Throughput |
|------|-----------------|-------------------|------------|
| Fast path | ~1 ms | **5-10 ms** | 100-200 events/sec |
| Slow path | ~53 ms | **100+ ms** | ~10 events/sec |

### Why Fast Path Will Be Slower

- **Network overhead**: gRPC over Docker network
- **Lock contention**: `RwLock` under concurrent requests
- **Heuristic iteration**: More rules = more O(n) checking
- **Serialization**: Protobuf encode/decode overhead
- **System noise**: Other processes, Docker overhead

### Why Slow Path Will Be Slower

- **More heuristics**: Larger query results to process
- **Vector search**: More embeddings to compare (O(n) or O(log n) with indexing)
- **DB contention**: Multiple concurrent queries
- **Embedding generation**: ML model inference time (currently ~30ms alone)

## Throughput Implications

| Scenario | Fast Path | Slow Path | Notes |
|----------|-----------|-----------|-------|
| Benchmark floor | ~1000/sec | ~19/sec | Not achievable in production |
| Realistic estimate | 100-200/sec | ~10/sec | Planning assumption |
| Under load | 50-100/sec | 5-10/sec | Degraded but functional |

**Key insight**: The fast path provides 10-20x throughput improvement over the slow path. Without it, GLADyS cannot keep up with moderate sensor activity.

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
docker-compose up -d
# Wait for services to be healthy
python benchmark_salience.py
```

To run with more requests:
```python
# Edit benchmark_salience.py
NUM_REQUESTS = 1000  # Default is 100
```

## Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-22 | Initial baseline established | Scott Mulcahy |
