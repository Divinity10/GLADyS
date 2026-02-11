# Audit: Salience Service (Rust) Test Coverage

## 1. Test Inventory

| Source file | Test count | Test type (unit/integration) |
|-------------|------------|------------------------------|
| `lib.rs` | 13 | Unit (Cache, Math, Novelty) |
| `server.rs` | 8 | Unit (Scorer, Boost, Cache RPCs) |
| `client.rs` | 3 | Unit (Proto builders, Roundtrip) |
| `config.rs` | 1 | Unit (Defaults) |
| `main.rs` | 1 | Unit (Scorer factory) |
| `tests/integration_test.rs` | 5 | Integration (gRPC Client to Python) |
| **Total** | **31** | |

## 2. Coverage Map

### gRPC Handlers (server.rs)
- [x] `evaluate_salience` -- scoring, salience boost, cache hit/miss recording
  - `test_scorer_cache_hit`
  - `test_apply_salience_boost`
- [x] `flush_cache` -- clear all, return count
  - `test_cache_management_rpcs`
- [x] `evict_from_cache` -- single removal
  - `test_cache_management_rpcs`
- [x] `get_cache_stats` -- hit rate calculation
  - `test_cache_management_rpcs`
- [x] `list_cached_heuristics` -- sorted by last_accessed, limit
  - `test_cache_management_rpcs`
- [x] `notify_heuristic_change` -- created/updated/deleted change types
  - `test_cache_invalidation_removes_heuristic` (lib.rs)
- [ ] `get_health` / `get_health_details` (Untested)

### Scoring (EmbeddingSimilarityScorer)
- [x] Embedding generation from event text
  - `test_scorer_cache_hit`
- [x] Cache-first lookup with similarity threshold
  - `test_scorer_cache_hit`
- [x] Storage fallback on cache miss
  - `test_scorer_storage_fallback`
- [x] Storage fallback on embedding failure
  - `test_embedding_failure_falls_back_to_storage`
- [x] Cache warming from storage results
  - `test_storage_match_warms_cache`
- [x] Empty text handling
  - `test_scorer_empty_text`
- [x] Source filter propagation to storage
  - `test_source_passed_to_storage`

### L0 Cache (MemoryCache in lib.rs)
- [x] Event add/get with FIFO eviction
  - `test_cache_eviction`
- [x] Heuristic add/get with LRU eviction
  - `test_heuristic_lru_eviction`
- [x] `touch_heuristic()` -- LRU update
  - `test_heuristic_touch_updates_lru`
- [x] `find_matching_heuristics()` -- similarity threshold, confidence filter, TTL expiry
  - `test_find_matching_heuristics_basic`
  - `test_find_matching_heuristics_ttl_expiry`
- [x] `is_novel()` -- novelty detection
  - `test_novelty_with_similar_event`
- [x] `find_similar()` -- best match retrieval
  - `test_find_similar`
- [x] `flush_heuristics()` -- clear and count
  - `test_cache_management_rpcs`
- [x] Cache stats (hits, misses, counts)
  - `test_cache_management_rpcs`
- [x] `remove_heuristic()` -- single invalidation
  - `test_cache_invalidation_removes_heuristic`

### Storage Backend (GrpcStorageBackend)
- [ ] `query_matching_heuristics()` -- proto conversion, UUID parsing, JSON parsing (Untested directly)
- [ ] `generate_embedding()` -- 384-dim vector return (Untested directly)
- [ ] Connection error handling (Untested)

### Math (lib.rs)
- [x] `cosine_similarity()` -- identical, orthogonal, mismatched dimensions, zero norms
  - `test_cosine_similarity_identical`
  - `test_cosine_similarity_orthogonal`

### Configuration (config.rs)
- [x] Default values
  - `test_default_config`
- [ ] Environment variable overrides (Untested)

### Trace ID (logging.rs)
- [ ] Generation, extraction from gRPC metadata (Untested)

## 3. Quality Assessment

- **Mock Accuracy**: High. The `MockStorageBackend` in `server.rs` correctly implements the `StorageBackend` trait, allowing comprehensive testing of the `EmbeddingSimilarityScorer` logic without external dependencies.
- **Assertion Quality**: Good. Tests verify specific cache behaviors (eviction, TTL, LRU), salience boosts, and scoring fallback paths.
- **Edge Case Coverage**: Very Good for the cache layer (empty embeddings, expired TTLs, similarity thresholds). However, the gRPC boundary and storage backend error paths (parsing failures, connection drops) are less covered.
- **Async Coverage**: Excellent. `tokio::test` is used for all async logic, including scorer fallbacks and gRPC handlers.
- **Integration Test Dependencies**: Integration tests require the Python Memory service. These correctly use `eprintln!` and `return` to skip gracefully if the server is not running, though this means they may be silently skipped in CI environments without setup.

## 4. Recommendations

### Priority 1: Data Integrity & Matching Correctness
- **Storage Backend Parsing**: Add unit tests for `GrpcStorageBackend` to verify that it correctly handles malformed effects JSON, missing heuristic fields, and UUID parsing errors from the Python response. (3 tests)
- **Trace ID Propagation**: Verify that trace IDs are correctly extracted from gRPC metadata and passed through the scorer to the storage backend. (1 test)

### Priority 2: Cache Reliability
- **Heuristic Change Notifications**: Add a specific test for the `notify_heuristic_change` handler in `server.rs` to verify that all change types ("created", "updated", "deleted") correctly result in cache eviction. (1 test)
- **TTL Precision**: Add tests for `heuristic_ttl_ms = 0` (no TTL) and verify that heuristics never expire in this mode. (1 test)

### Priority 3: Configuration & Health
- **Env Override Testing**: Add unit tests for `Config::from_env()` by temporarily setting environment variables using `temp_env` or similar, ensuring that all overrides work as expected. (2 tests)
- **Health RPCs**: Add basic tests for `get_health` and `get_health_details` to verify they return valid proto responses and correct uptime/metrics. (2 tests)
