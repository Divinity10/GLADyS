# Audit: Salience Service (Rust) Test Coverage

**Report Date**: 2026-02-09
**Validated**: 2026-02-12
**Status**: Report remains 100% accurate. No code changes since Feb 9. All gaps still valid.

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

## 4. New Gaps (Since Feb 9)

1. **GrpcStorageBackend proto conversion** (server.rs:81-123):
   - `bytes_to_embedding` conversion (line 105) assumes valid 4-byte chunks - will panic if `condition_embedding` bytes are not a multiple of 4
   - No test covers malformed embedding bytes

2. **Trace ID integration in GrpcStorageBackend** (server.rs:68-72):
   - trace_id passed to `with_trace_id()` but no verification it propagates to Python via gRPC headers
   - Integration test doesn't check trace ID headers

3. **Storage backend timeout errors** (server.rs:129, 152):
   - Both `query_matching_heuristics` and `generate_embedding` catch errors generically
   - No unit test for actual timeout behavior (mock always succeeds)

4. **ScoringError::NoMatches dead code** (lib.rs:59-66):
   - `ScoringError::NoMatches` variant defined but never returned in code
   - `EmbeddingSimilarityScorer.score()` returns `Ok([])` instead of `NoMatches`

5. **Salience vector dimension validation** (server.rs:283-310):
   - `apply_salience_boost` assumes boost JSON contains valid dimension keys
   - No validation that output vector dimensions stay in reasonable range
   - No test for NaN values in boost

## 5. Recommendations

### Priority 1: Data Integrity & Matching Correctness (CRITICAL - recommend Gemini trace)

- **GrpcStorageBackend proto parsing** (server.rs:81-123):
  - Risk: Silent data corruption. Malformed embeddings cause panic, missing fields silently dropped, invalid UUIDs silently skipped.
  - Add 3 unit tests: missing heuristic field, non-4-byte-aligned condition_embedding, unparseable UUID
  - These paths are code-covered but untested at assertion level

- **Trace ID propagation end-to-end** (logging.rs:113-124 → client.rs:91-98 → server.rs:68-72):
  - Risk: Request correlation breaks silently if trace_id not threaded through
  - Add 1 integration test verifying trace_id header in outgoing gRPC calls to Python storage

- **apply_salience_boost dimension handling** (server.rs:283-310):
  - Risk: Heuristics with malformed boost JSON could silently degrade salience
  - Add 2 unit tests: boost with NaN values, boost with dimension keys outside expected set

### Priority 2: Cache Reliability & Configuration (IMPORTANT)

- **Environment variable override testing** (config.rs):
  - Risk: Config mismatches between CI (env vars) and local (defaults)
  - Add 4 tests using temp_env: GRPC_PORT, STORAGE_ADDRESS, CACHE_HEURISTIC_TTL_MS, SALIENCE_MIN_HEURISTIC_SIMILARITY

- **Storage backend timeout simulation** (server.rs:144-154, client.rs:69-81):
  - Risk: Timeouts in production aren't covered by unit tests (only happy path mocked)
  - Add 2 tests with DelayedMockStorage that sleeps longer than timeout

- **TTL Precision**: Add tests for `heuristic_ttl_ms = 0` (no TTL) and verify that heuristics never expire in this mode. (1 test)

### Priority 3: Low-Risk Nice-to-Have

- **Health RPCs**: Add basic tests for `get_health` and `get_health_details` to verify they return valid proto responses. (2 tests)
- **ScoringError::NoMatches**: Either use it (return NoMatches) or remove to prevent future confusion.
