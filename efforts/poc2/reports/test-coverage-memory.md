# Audit: Memory Service Test Coverage

**Report Date**: 2026-02-09
**Validated**: 2026-02-12
**Status**: No gaps closed since Feb 9. New critical gaps identified in fire recording and heuristic updates.

## 1. Test Inventory

| Test file | Test count | Test type (unit/integration) |
|-----------|------------|------------------------------|
| `test_embeddings.py` | 6 | Unit |
| `test_grpc.py` | 12 | Unit/Integration (requires Postgres) |
| `test_grpc_events.py` | 15 | Unit (Mocked Storage) |
| `test_storage.py` | 23 | Integration (requires Postgres) |
| `test_storage_events.py` | 32 | Unit (Mocked asyncpg Pool) |
| **Total** | **88** | |

## 2. Coverage Map

### gRPC Handlers (grpc_server.py)

- [x] `StoreEvent` -- proto conversion, storage call
  - `test_store_event`
- [x] `ListEvents` -- pagination, source filter, salience dict->proto
  - `test_returns_events`
  - `test_timestamp_ms_conversion`
  - `test_salience_vector_populated`
- [x] `GetEvent` -- single fetch, not found
  - `test_found`
  - `test_not_found`
- [ ] `ListResponses` -- decision_path/source/search filters (Untested)
- [ ] `GetResponseDetail` -- fire data, prompt text (Untested)
- [ ] `DeleteResponses` -- bulk deletion, UUID conversion (Untested)
- [x] `GenerateEmbedding` -- text->embedding, empty text validation
  - `test_generate_embedding`
  - `test_generate_embedding_empty_text`
- [x] `StoreHeuristic` -- condition embedding generation, cache notification
  - `test_store_heuristic`
- [x] `QueryHeuristics` -- confidence threshold filter
  - `test_query_heuristics`
  - `test_query_heuristics_confidence_filter`
- [ ] `QueryMatchingHeuristics` -- embedding similarity search (Untested)
- [ ] `GetHeuristic` -- single fetch (Untested)
- [ ] `UpdateHeuristicConfidence` -- Bayesian update with magnitude, TD error (Untested)
- [ ] `RecordHeuristicFire` -- fire record insertion (Untested)
- [ ] `UpdateFireOutcome` -- outcome/feedback update (Untested)
- [ ] `GetPendingFires` -- outcome='unknown' filter, max_age (Untested)
- [ ] `ListFires` -- pagination, outcome filter (Untested)
- [ ] Entity RPCs (`StoreEntity`, `QueryEntities`, `GetRelationships`, `ExpandContext`) (Untested)
- [ ] `GetHealth` / `GetHealthDetails` (Untested)

### Storage Layer (storage.py)

- [x] `store_event()` -- all fields including embedding, salience, prediction
  - `test_store_event_basic`
  - `test_store_event_with_embedding`
- [ ] `delete_events()` -- cascade to heuristic_fires (Untested)
- [x] `query_by_time()` -- timestamp range, source filter, archived exclusion
  - `test_query_by_time_returns_events`
  - `test_query_by_time_respects_source_filter`
- [x] `query_by_similarity()` -- pgvector cosine distance, time window
  - `test_query_by_similarity_finds_similar`
  - `test_query_by_similarity_returns_scores`
- [x] `list_events()` -- DISTINCT ON, LEFT JOIN fires, pagination
  - `test_basic_query`
  - `test_left_join_heuristic_fires`
- [x] `get_event()` -- single fetch with fire data
  - `test_found`
  - `test_uuid_conversion`
- [x] `list_responses()` -- filter combinations, ILIKE escaping
  - `test_decision_path_filter`
  - `test_source_filter`
  - `test_search_filter`
- [x] `get_response_detail()` -- joined fire/heuristic data
  - `test_found`
  - `test_includes_fire_data`
- [x] `store_heuristic()` -- UPSERT with condition_embedding
  - `test_store_heuristic`
- [ ] `query_matching_heuristics()` -- embedding similarity, source filter, text fallback (Untested)
- [x] `update_heuristic_confidence()` -- Bayesian Beta alpha/beta update, magnitude weighting
  - `test_bayesian_confidence_calculation`
  - `test_alpha_beta_default_confidence`
  - `test_alpha_beta_full_weight_positive`
  - `test_alpha_beta_fractional_magnitude`
  - `test_alpha_beta_zero_magnitude_backward_compat`
  - `test_alpha_beta_confidence_bounds`
- [ ] `record_heuristic_fire()` / `update_fire_outcome()` / `get_pending_fires()` / `list_fires()` (Untested)
- [ ] Entity/relationship storage and queries (Untested)

### Proto Conversion (grpc_server.py helpers)

- [x] `_event_to_proto()` -- salience dict, structured_json, UUID, timestamp
  - `test_salience_vector_populated`
- [x] `_proto_to_event()` -- reverse conversion, missing fields
  - `test_store_event` (Integration)
- [x] `_embedding_to_bytes()` / `_bytes_to_embedding()` -- round-trip
  - `test_embedding_to_bytes_and_back`
- [x] Salience vector population (all 9 dimensions, zero preservation)
  - `test_salience_vector_populated`
  - `test_zero_salience_preserved`
- [x] NULL field handling (matched_heuristic_id, prediction fields, response fields)
  - `test_null_matched_heuristic_id`
  - `test_null_prediction_fields`
  - `test_null_response_fields`

### Embeddings (embeddings.py)

- [x] `generate()` -- shape, dtype
  - `test_generate_returns_correct_shape`
- [x] `generate_batch()` -- batch shape
  - `test_generate_batch_returns_correct_shape`
- [x] `cosine_similarity()` -- known vectors, zero norms
  - `test_cosine_similarity_identical_vectors`
  - `test_cosine_similarity_orthogonal_vectors`

## 3. Quality Assessment

- **Mock Accuracy**: High. Tests use both `AsyncMock` for top-level services and mocked database pools for storage unit tests, allowing for isolation of logic from database state.
- **Assertion Quality**: Excellent. Tests assert exact values for confidence updates (Bayesian math), verify SQL query strings for correct filters/joins, and ensure proto field mapping is precise.
- **Edge Case Coverage**: Very Good for storage queries (NULL handling, empty results, archived filters) and Bayesian updates (zero magnitude, fractional magnitude, bounds).
- **One Behavior per Test**: Strongly followed.
- **Duplicate Coverage**: Low. Integration tests in `test_storage.py` and `test_grpc.py` complement unit tests in `test_storage_events.py` and `test_grpc_events.py`.

## 4. New Gaps (Since Feb 9)

- **RecordHeuristicFire** (gRPC RPC) - fire_id generation, episodic_event_id handling - UNTESTED
- **UpdateFireOutcome** (gRPC RPC) - outcome/feedback_source updates - UNTESTED
- **GetPendingFires** (gRPC RPC) - max_age_seconds filtering, outcome='unknown' filter - UNTESTED
- **ListFires** (gRPC RPC) - outcome filter, heuristic_fires/heuristics LEFT JOIN, total_count calc - UNTESTED
- **ExpandContext** (gRPC RPC) - BFS traversal, max_hops capping, entity/relationship graph expansion - UNTESTED

## 5. Recommendations

### Priority 1: Data Integrity & Reliability (CRITICAL - recommend Gemini trace)

- **Heuristic Fire Recording & Updates** (RecordHeuristicFire, UpdateFireOutcome, GetPendingFires):
  - Risk: Flight Recorder is the entire learning feedback loop. Without tests, fire records may not persist correctly, outcome updates fail silently, learning system cannot verify fires are recorded
  - Cross-references between fires and events may break during concurrent updates
  - Add 4-5 tests covering fire creation, episodic_event_id FK handling, outcome updates, pending fires filtering

- **UpdateHeuristicConfidence gRPC layer** (Bayesian update integration):
  - Risk: magnitude parameter may not reach storage, confidence update applied to wrong heuristic if ID conversion fails, TD error calculation bypassed
  - Add 2 tests ensuring magnitude and feedback_source correctly passed from proto to storage

- **QueryMatchingHeuristics** (semantic matching - core learning feature):
  - Risk: condition_embedding may not be returned to client (breaks Rust cache optimization), min_similarity threshold not applied at gRPC layer, source_filter lost
  - Add 2 tests for embedding bytes return + source filtering

### Priority 2: Contract Correctness (IMPORTANT)

- **GetPendingFires & ListFires** (learning feedback collection):
  - Risk: max_age_seconds filter not working, outcome='unknown' filter broken, total_count mismatch, NULL heuristic names from LEFT JOIN
  - Add 4-5 tests for filtering logic, JOIN correctness, pagination

- **ExpandContext** (LLM prompt context):
  - Risk: BFS traversal bugs (infinite loops on cycles), max_entities limit not enforced (memory explosion), confidence threshold not applied
  - Add 2-3 tests for BFS logic, entity limits, confidence filtering

- **DeleteResponses** (response cleanup):
  - Risk: UUID parsing failures cause partial deletes, cascade to heuristic_fires untested (orphaned fire records)
  - Add 2 tests for UUID parsing, cascade behavior

- **Entity & Relationship Storage**: The entire semantic memory layer (entities, relationships, context expansion) is currently untested. Add tests for `StoreEntity`, `QueryEntities`. (5-6 tests)

### Priority 3: Lower-Risk Gaps

- **Response Tab RPCs**: Add gRPC-level tests for `ListResponses` and `GetResponseDetail`. (2 tests)
- **Health & Status**: Add tests for `GetHealth` and `GetHealthDetails`. (1-2 tests)
- **ILIKE Escaping**: Verify that the ILIKE escaping logic in `list_responses` correctly handles backslashes and underscores. (1 test)
