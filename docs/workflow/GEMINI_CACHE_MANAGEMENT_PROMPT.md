# Gemini Task: Phase 6 - Cache Management

## Context

You are implementing Phase 6 of the Service Scripts refactor. Phases 1-4 are complete:
- Phase 1-2 (you): Core framework and Docker backend
- Phase 3-4 (Claude): Local backend and sync-check

**Design Doc**: [SERVICE_SCRIPTS_DESIGN.md](../design/SERVICE_SCRIPTS_DESIGN.md)
**Work Log**: [SERVICE_SCRIPTS_WORKLOG.md](SERVICE_SCRIPTS_WORKLOG.md)

---

## Your Task

Implement cache management for the Rust salience gateway (`memory-rust`).

### Deliverables

1. **Proto additions** to `src/memory/proto/memory.proto`:

```protobuf
// Add to SalienceGateway service
service SalienceGateway {
    // Existing RPCs...

    // Cache management (NEW)
    rpc FlushCache(FlushCacheRequest) returns (FlushCacheResponse);
    rpc EvictFromCache(EvictFromCacheRequest) returns (EvictFromCacheResponse);
    rpc GetCacheStats(GetCacheStatsRequest) returns (GetCacheStatsResponse);
    rpc ListCachedHeuristics(ListCachedHeuristicsRequest) returns (ListCachedHeuristicsResponse);
}

message FlushCacheRequest {}
message FlushCacheResponse {
    int32 entries_flushed = 1;
}

message EvictFromCacheRequest {
    string heuristic_id = 1;
}
message EvictFromCacheResponse {
    bool found = 1;
}

message GetCacheStatsRequest {}
message GetCacheStatsResponse {
    int32 current_size = 1;
    int32 max_capacity = 2;
    float hit_rate = 3;
    int64 total_hits = 4;
    int64 total_misses = 5;
}

message ListCachedHeuristicsRequest {
    int32 limit = 1;  // 0 = all
}
message CachedHeuristicInfo {
    string heuristic_id = 1;
    string name = 2;
    int32 hit_count = 3;
    int64 cached_at_unix = 4;
    int64 last_hit_unix = 5;
}
message ListCachedHeuristicsResponse {
    repeated CachedHeuristicInfo heuristics = 1;
}
```

2. **Rust implementation** in `src/memory/rust/src/`:
   - Add RPC handlers for each cache management endpoint
   - Track hit/miss statistics in the cache
   - Track per-heuristic metadata (cached_at, last_hit, hit_count)

3. **CLI commands** in `scripts/_docker_backend.py` and `scripts/_service_base.py`:

```bash
python scripts/docker.py cache stats      # Show cache statistics
python scripts/docker.py cache list       # List cached heuristics
python scripts/docker.py cache flush      # Clear entire cache
python scripts/docker.py cache evict <id> # Remove single heuristic
```

---

## Implementation Notes

### Rust Cache Enhancement

The current LRU cache needs metadata tracking. Consider:

```rust
struct CacheEntry {
    heuristic: Heuristic,
    cached_at: SystemTime,
    last_hit: SystemTime,
    hit_count: u64,
}

struct CacheStats {
    hits: AtomicU64,
    misses: AtomicU64,
}
```

### CLI Integration

Add cache subcommand to `_service_base.py`:

```python
# In _setup_parser()
cache = subparsers.add_parser("cache", help="Cache management")
cache_sub = cache.add_subparsers(dest="cache_command", required=True)

cache_stats = cache_sub.add_parser("stats", help="Show cache statistics")
cache_stats.set_defaults(func=self.cmd_cache_stats)

cache_list = cache_sub.add_parser("list", help="List cached heuristics")
cache_list.set_defaults(func=self.cmd_cache_list)

cache_flush = cache_sub.add_parser("flush", help="Clear entire cache")
cache_flush.set_defaults(func=self.cmd_cache_flush)

cache_evict = cache_sub.add_parser("evict", help="Evict specific heuristic")
cache_evict.add_argument("heuristic_id", help="Heuristic ID to evict")
cache_evict.set_defaults(func=self.cmd_cache_evict)
```

The backend calls will go via gRPC to memory-rust.

---

## Testing

1. Start Docker services: `python scripts/docker.py start all`
2. Run sync-check: `python scripts/docker.py sync-check`
3. Store some heuristics via tests
4. Test cache commands:
   ```bash
   python scripts/docker.py cache stats
   python scripts/docker.py cache list
   python scripts/docker.py cache evict <some-id>
   python scripts/docker.py cache flush
   ```

---

## When Done

1. Update [SERVICE_SCRIPTS_WORKLOG.md](SERVICE_SCRIPTS_WORKLOG.md):
   - Mark Phase 6 as complete
   - Add entry to "Completed Work" section
2. Run `python scripts/proto_sync.py` to sync proto changes
3. Test that both Docker and local environments work

---

## Questions?

If you need clarification on the design or hit blockers, add them to the work log's "Blockers/Issues" section.
