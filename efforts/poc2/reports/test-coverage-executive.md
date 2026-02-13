# Audit: Executive Service Test Coverage

**Report Date**: 2026-02-09
**Validated**: 2026-02-12
**Status**: Salience extraction tests added (+5 tests). Critical gaps remain in ProcessEvent integration, negative feedback path, quality gate.

## 1. Test Inventory

| Test file | Test count | Test type (unit/integration) |
|-----------|------------|------------------------------|
| `test_bootstrapping.py` | 16 | Unit/Integration (RPC Mocks) |
| `test_decision_strategy.py` | 13 | Unit |
| `test_llm_provider.py` | 10 | Unit |
| `test_provide_feedback.py` | 4 | Unit/Integration |
| `test_salience_extraction.py` | 5 | Unit |
| **Total** | **48** | (+5 since Feb 9) |

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

## 3. Obsolete Items (Since Feb 9)

- **Separate decision_strategy.py and llm_provider.py files** - Report assumes standalone modules. Current code refactored into single `server.py` (commits 0128dee, 724e367)
- **format_event_for_llm() untested** - Function exists but unclear if actively used in current codebase flow

## 4. New Gaps (Since Feb 9)

- **Salience extraction edge cases** - NEW test file `test_salience_extraction.py` (commit 84297a0) covers basic extraction but missing: integration with ProcessEvent, vector dimension handling in prompts/LLM context
- **HeuristicStore file-based persistence** (lines 961-998) - Load/save failure recovery, concurrent access - UNTESTED
- **Format event for LLM** - Defined but not imported/used anywhere in codebase

## 5. Completed (Since Feb 9)

- **Salience extraction** - Test file `test_salience_extraction.py` added (commit 84297a0, Feb 12). 5 test cases cover all 8 salience fields, missing dimensions defaulting to 0.0, zero values, boundary values, empty/None proto
- **Bootstrapping flow** - Tests added Feb 9 for cosine similarity, confidence update via endorsement, cache invalidation, below-threshold suppression, background task error handling

## 6. Quality Assessment

- **Mock Accuracy**: High. Tests use `unittest.mock.AsyncMock` for RPC clients and LLM providers, correctly simulating async behavior and gRPC response structures.
- **Assertion Quality**: Good. Tests assert specific fields in responses (e.g., `decision_path`, `predicted_success`) and verify mock calls with expected arguments (e.g., `update_heuristic_confidence_weighted`).
- **Edge Case Coverage**: Moderate. Cosine similarity and personality bias have good edge case coverage (zero vectors, clamping). However, RPC error paths and malformed LLM responses (invalid JSON) are only partially covered.
- **One Behavior per Test**: Strongly followed. Tests are granular and focused on specific features (e.g., goals injection, metadata leaks).
- **Duplicate Coverage**: Low. The test suite is efficient with minimal redundancy.

## 7. Recommendations

### Priority 1: Data Integrity & Feedback Loop (CRITICAL - recommend Gemini trace)

- **ProcessEvent full integration** (server.py lines 1085-1143):
  - Risk: Entry point for all decisions. Candidate deduplication, salience extraction, strategy invocation need integration test. Silent failures in candidate merging, salience not flowing to LLM prompts. Complete decision pipeline could be broken
  - Add integration test covering full flow: candidates merged, salience extracted, strategy invoked, trace setup

- **ProvideFeedback negative feedback path** (lines 1160-1177):
  - Risk: Confidence decrement is the only mechanism to penalize failed actions. If untested, failed feedback doesn't update heuristic confidence at all. Heuristics never improve from negative feedback
  - Add 2 tests for negative=False path, verify confidence decrement via MemoryClient

- **Quality gate validation** (lines 1061-1083):
  - Risk: Malformed heuristics stored to Memory, breaking downstream matching. Garbage heuristics pollute knowledge base
  - Add 4-5 tests for word count limits (10/50 words), action structure validation, edge cases

- **Client RPC error handling** (lines 745-750, 796-798, 813-815):
  - Risk: MemoryClient/SalienceGatewayClient swallow RPC errors. Silently fails, returns False/empty, caller doesn't know why. Decision path changes unexpectedly when services down
  - Add tests for connection failures, malformed proto responses

### Priority 2: Feedback Robustness (IMPORTANT)

- **Trace expiry handling**: ProvideFeedback should reject expired traces. Risk: feedback applied to wrong event if response_id collides (1 test)
- **Pattern extraction robustness** (lines 1202-1219): JSON parsing with triple-backtick stripping. Risk: non-JSON responses fail. Add tests for malformed responses (2 tests)
- **Salience in LLM prompts**: format_event_for_llm() not tested. Risk: salience dimensions not included in LLM context (1 test)
- **Heuristic storage persistence**: HeuristicStore load/save can fail silently. Risk: learned patterns lost (2 tests)

### Priority 3: Lower-Risk Gaps

- **GetHealth/GetHealthDetails**: Diagnostic RPCs, not core flow (1-2 tests)
