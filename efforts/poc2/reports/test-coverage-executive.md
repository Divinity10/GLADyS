# Audit: Executive Service Test Coverage

## 1. Test Inventory

| Test file | Test count | Test type (unit/integration) |
|-----------|------------|------------------------------|
| `test_bootstrapping.py` | 16 | Unit/Integration (RPC Mocks) |
| `test_decision_strategy.py` | 13 | Unit |
| `test_llm_provider.py` | 10 | Unit |
| `test_provide_feedback.py` | 4 | Unit/Integration |
| **Total** | **43** | |

## 2. Coverage Map

### RPC Handlers
- [ ] `ProcessEvent` -- candidate dedup, salience extraction, trace setup (Untested)
- [x] `ProvideFeedback` -- positive path (pattern extraction, quality gate, merge-or-reinforce)
  - `test_provide_feedback_reinforces_similar_heuristic`
  - `test_provide_feedback_creates_new_when_no_similar`
- [ ] `ProvideFeedback` -- negative path (confidence decrement) (Untested)
- [ ] `ProvideFeedback` -- rejection paths (trace not found, quality gate failure) (Untested)
- [ ] `GetHealth` / `GetHealthDetails` (Untested)

### Decision Strategy (HeuristicFirstStrategy)
- [x] `decide()` -- heuristic fast-path (confidence >= threshold)
  - `test_heuristic_path`
- [x] `decide()` -- LLM path (below threshold, immediate)
  - `test_llm_path`
- [x] `decide()` -- rejected path (LLM unavailable or not immediate)
  - `test_rejected_path_no_llm`
  - `test_rejected_path_not_immediate`
- [x] `decide()` -- fallback path (LLM returns None)
  - `test_fallback_path`
- [x] `_build_evaluation_prompt()` -- candidate formatting, shuffle, metadata leak prevention
  - `test_evaluation_prompt_includes_candidates`
  - `test_evaluation_prompt_no_metadata_leaks`
- [x] `_build_prompt()` -- no-candidates path
  - `test_prompt_no_candidates_no_context_section`
- [x] `_get_prediction()` -- JSON parsing, malformed input, ceiling cap
  - `test_llm_path`
  - `test_llm_confidence_ceiling`
- [x] `_process_llm_endorsements()` -- similarity above threshold (update + cache invalidation)
  - `test_endorsement_updates_confidence`
  - `test_cache_invalidation_after_endorsement`
- [x] `_process_llm_endorsements()` -- similarity below threshold (no update)
  - `test_below_threshold_no_update`
- [x] `_process_llm_endorsements()` -- error handling (embedding failure, RPC failure)
  - `test_background_task_handles_errors_gracefully`
- [x] `_schedule_endorsement_task()` -- non-blocking response path
  - `test_response_returned_before_comparison`
- [x] Semaphore concurrency limiting
  - `test_semaphore_limits_concurrency`
- [x] Personality bias threshold adjustment and clamping
  - `test_personality_bias_lowers_threshold`
  - `test_personality_bias_clamped`
- [x] Goals injection into prompts
  - `test_goals_in_prompt`

### Client Classes
- [x] `MemoryClient.generate_embedding()`
  - `test_memory_client_generate_embedding`
- [x] `MemoryClient.update_heuristic_confidence_weighted()`
  - `test_memory_client_weighted_confidence_update`
- [ ] `MemoryClient.store_heuristic()` (Untested directly)
- [ ] `MemoryClient.query_matching_heuristics()` (Untested directly)
- [ ] `MemoryClient.update_heuristic_confidence()` (Untested directly)
- [x] `SalienceGatewayClient.notify_heuristic_change()`
  - `test_salience_client_notify_change`
- [ ] Client error handling (connection failure, RPC error) (Untested)

### Helpers
- [x] `cosine_similarity()` -- known vectors, zero vectors, edge cases
  - `test_cosine_similarity_known_vectors`
  - `test_cosine_similarity_zero_vector`
  - `test_cosine_similarity_computation`
- [ ] `format_event_for_llm()` -- salience inclusion (Untested)
- [ ] `_check_heuristic_quality()` -- word count, action structure validation (Untested directly)
- [x] Trace store operations (store, get, delete, cleanup)
  - `test_get_trace`

## 3. Quality Assessment

- **Mock Accuracy**: High. Tests use `unittest.mock.AsyncMock` for RPC clients and LLM providers, correctly simulating async behavior and gRPC response structures.
- **Assertion Quality**: Good. Tests assert specific fields in responses (e.g., `decision_path`, `predicted_success`) and verify mock calls with expected arguments (e.g., `update_heuristic_confidence_weighted`).
- **Edge Case Coverage**: Moderate. Cosine similarity and personality bias have good edge case coverage (zero vectors, clamping). However, RPC error paths and malformed LLM responses (invalid JSON) are only partially covered.
- **One Behavior per Test**: Strongly followed. Tests are granular and focused on specific features (e.g., goals injection, metadata leaks).
- **Duplicate Coverage**: Low. The test suite is efficient with minimal redundancy.

## 4. Recommendations

### Priority 1: Data Integrity & Feedback Loop
- **Negative Feedback Path**: Add tests for `ProvideFeedback` where `positive=False`. Verify it decrements confidence via `MemoryClient.update_heuristic_confidence` when a trace exists. (2 tests)
- **Feedback Rejection Paths**: Add tests for `ProvideFeedback` when a trace is missing, LLM is unavailable, or pattern extraction fails. (3-4 tests)
- **Trace Expiry**: Verify that expired traces are correctly handled/rejected in `ProvideFeedback`. (1 test)

### Priority 2: Contract Correctness
- **ProcessEvent Integration**: Add direct tests for `ExecutiveServicer.ProcessEvent`. Verify candidate deduplication (merging `suggestion` and `candidates`), salience extraction, and trace setup. (3 tests)
- **MemoryClient Completeness**: Add unit tests for `store_heuristic`, `query_matching_heuristics`, and `update_heuristic_confidence` to ensure they handle RPC errors and unexpected response formats. (3 tests)

### Priority 3: Decision Logic & Helpers
- **Quality Gate Boundaries**: Add unit tests for `_check_heuristic_quality`. Test word count limits (10/50 words) and action structure validation. (4-5 tests)
- **Health RPCs**: Add basic tests for `GetHealth` and `GetHealthDetails`. (1-2 tests)
- **Event Formatting**: Add tests for `format_event_for_llm` to ensure salience dimensions are correctly included in the string context. (1 test)
