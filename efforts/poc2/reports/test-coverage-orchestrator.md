# Audit: Orchestrator Service Test Coverage

**Report Date**: 2026-02-09
**Validated**: 2026-02-12
**Status**: Architectural changes since Feb 9. Heuristic shortcut removed, SalienceResult migration, +17 new tests added. Major gaps remain in streaming RPCs and OutcomeWatcher.

## 1. Test Inventory

| Test file | Test count | Test type (unit/integration) |
|-----------|------------|------------------------------|
| `test_candidates.py` | 12 | Unit/Integration (Client mocks) |
| `test_event_flow.py` | 7 | Integration (Callback mocks) |
| `test_event_queue.py` | 4 | Unit/Integration |
| `test_learning_module.py` | 2 | Unit |
| `test_learning_strategy.py` | 14 | Unit |
| `test_registry.py` | 7 | Unit |
| `test_router.py` | 11 | Unit |
| `test_server.py` | 7 | Unit (Servicer tests) |
| **Total** | **64** | (+17 since Feb 9) |

## 2. Coverage Map

### RPC Handlers (server.py)

- [ ] `PublishEvent` -- single event acceptance and routing (Untested directly)
- [ ] `PublishEvents` -- batch processing, per-event error handling (Untested)
- [ ] `StreamEvents` -- streaming RPC (Untested)
- [ ] `SubscribeEvents` -- subscriber registration, source filtering, delivery (Untested)
- [ ] `SubscribeResponses` -- response subscription with include_immediate flag (Untested)
- [x] `RegisterComponent` / `UnregisterComponent`
  - `test_register_component`
  - `test_unregister_component`
- [x] `Heartbeat` -- timestamp update, pending commands
  - `test_heartbeat`
- [x] `GetSystemStatus` / `GetQueueStats` / `ListQueuedEvents`
  - `test_get_system_status`
  - `GetQueueStats` and `ListQueuedEvents` are Untested
- [x] `ResolveComponent` -- by ID, by type, not found
  - `test_resolve_component_by_id`
  - `test_resolve_component_not_found`
- [ ] `GetHealth` / `GetHealthDetails` (Untested)

### Event Router (router.py)

- [x] `route_event()` -- salience evaluation, heuristic matching, candidate population
  - `test_route_event_returns_queued`
  - `test_router_populates_candidates`
- [x] `route_event()` -- emergency fast-path (high confidence + high threat)
  - `test_emergency_both_thresholds`
- [ ] `route_event()` -- outcome checking (implicit feedback) (Untested)
- [x] Candidate population -- query, filter above-threshold, limit to max
  - `test_router_limits_candidates_to_max`
  - `test_router_filters_above_threshold_candidates`
- [x] Subscriber broadcast with source filtering
  - `test_broadcast_to_subscribers`
- [ ] Response subscriber broadcast with include_immediate filtering (Untested)
- [ ] Salience fallback when service unavailable (Untested)

### Event Queue (event_queue.py)

- [x] Enqueue with salience-based priority ordering
  - `test_route_high_salience_queued_with_priority` (Indirectly tests prioritization)
- [x] Dequeue and process (callback invocation)
  - `test_event_processed_and_stored`
- [x] Timeout scanner -- expiry detection, storage, broadcast
  - `test_timeout_calls_store_callback`
  - `test_timeout_broadcasts_after_store`
- [x] Store callback -- event + response persisted
  - `test_successful_process_calls_store`
- [x] Candidate passthrough in callback signature
  - `test_event_queue_carries_candidates`

### Component Registry (registry.py)

- [x] Register, unregister, re-register
  - `test_register_component`
  - `test_unregister_component`
- [x] Heartbeat update
  - `test_heartbeat_updates_timestamp`
- [x] Command queue and retrieval
  - `test_queue_and_get_pending_commands`
- [x] Service discovery (by ID, by type with ACTIVE preference)
  - `test_get_by_id`
  - `test_get_by_type`

### Learning Module (learning.py)

- [x] `on_feedback()` -- strategy interpretation, signal application
  - `test_on_feedback_delegates_to_strategy`
- [x] `on_fire()` -- flight recorder, outcome watcher registration
  - `test_on_fire_records_correctly`
- [ ] `check_event_for_outcomes()` -- outcome resolution, undo detection, ignore detection (Untested)
- [ ] `on_heuristic_ignored()` -- ignore counting, threshold-based negative feedback (Untested)
- [ ] `cleanup_expired()` -- timeout as positive implicit feedback (Untested)

### Learning Strategy

- [x] `interpret_explicit_feedback()` -- positive/negative with magnitude
  - `test_explicit_positive`
  - `test_explicit_negative`
- [x] `interpret_timeout()` -- timeout as positive signal
  - `test_timeout_returns_positive`
- [x] `interpret_event_for_undo()` -- keyword matching
  - `test_undo_detected`
- [x] `interpret_ignore()` -- threshold behavior
  - `test_ignore_at_threshold`

### Client Classes

- [x] `ExecutiveClient.send_event_immediate()` -- proto construction, candidate passing
  - `test_executive_client_sends_candidates`
- [ ] `SalienceMemoryClient.evaluate_salience()` -- request/response, fallback (Untested directly)
- [x] `MemoryStorageClient.store_event()` / `record_heuristic_fire()` / `update_heuristic_confidence()`
  - `test_memory_client_weighted_confidence_update` (In Executive tests)
  - `test_on_fire_records_correctly` (Orchestrator test)
- [x] `MemoryStorageClient.query_matching_heuristics()` -- graceful failure
  - `test_memory_client_query_matching_heuristics`
  - `test_memory_client_query_matching_heuristics_failure`
- [x] Client error handling (gRPC unavailable)
  - `test_memory_client_query_matching_heuristics_not_connected`

## 3. Obsolete Items (Architectural Changes Since Feb 9)

- **SalienceVector (9 fields)** - REPLACED by SalienceResult (3 scalars + vector map). Tests updated in commit 5ea56c7 (Feb 12)
- **High-confidence heuristic shortcut** - REMOVED (commit 568cd58). Orchestrator no longer decides heuristic-vs-LLM. ALL non-emergency events forward to Executive. Exception: Emergency fast-path (confidence ≥0.95 AND threat ≥0.9) still exists
- **on_heuristic_ignored()** - Referenced in report but NOT FOUND in current code (may be deferred)

## 4. New Gaps (Since Feb 9)

- **OutcomeWatcher** (outcome_watcher.py) - 250 lines, ZERO unit tests. Entire implicit feedback system untested: register_fire, check_event, cleanup_expired
- **SalienceResult migration integration** (commit 5ea56c7) - New vector map iteration logic (router.py:412-429). Edge case: non-dict vector not fully tested
- **cleanup_expired() background loop** (server.py:146-158) - Background task calls learning_module.cleanup_expired() but no test of loop startup, interval timing, or graceful stop

## 5. Completed (Since Feb 9)

- EventQueue timeout scanner + persistence (4 tests added)
- Heuristic fire recording with episodic_event_id (test added)
- Candidate population and filtering (12 tests added)
- SalienceResult vector migration (68 lines of test updates)

## 6. Quality Assessment

- **Mock Accuracy**: High. Tests use `AsyncMock` and `MagicMock` effectively to simulate gRPC services and client responses.
- **Assertion Quality**: Very Good. Tests verify both return values and internal state changes (e.g., subscriber queue sizes, mock call counts).
- **Edge Case Coverage**: Moderate. Covers basic error paths (e.g., RPC failure) and threshold boundaries. However, complex event flows (streaming, batching) and implicit feedback loops (undo/ignore) are not fully exercised.
- **One Behavior per Test**: Strongly followed. Tests are well-isolated and focused.
- **Duplicate Coverage**: Low. The test suite is well-structured and efficient.

## 7. Recommendations

### Priority 1: Data Integrity & Event Flow (CRITICAL - recommend Gemini trace)

- **OutcomeWatcher unit tests** (outcome_watcher.py):
  - Risk: Implicit feedback entire stack untested. OutcomeWatcher manages PendingOutcome list, pattern matching, callback invocation. Bugs silently degrade learning
  - Code path: router:102 calls check_event_for_outcomes → learning:102 → outcome_watcher
  - Add 8-10 tests for pattern matching, timeout management, success/failure classification

- **check_event_for_outcomes integration** (learning.py:102):
  - Risk: Undo/implicit feedback flow not validated. If LearningModule returns resolved outcomes, router logs but doesn't verify signal was applied
  - Add 3 tests: undo detection, outcome match, timeout-as-positive

- **Streaming RPCs contract correctness** (PublishEvent via streaming, SubscribeEvents, SubscribeResponses):
  - Risk: Async iterator protocol fragile. Missing tests for early disconnect, queue full backpressure, proto format on wire
  - Add 6 tests: stream startup, event yield, disconnect, queue full, context cleanup, error propagation

### Priority 2: Contract Correctness (IMPORTANT)

- **Salience client fallback contract** (router.py:354-374):
  - Risk: Graceful degradation documented but untested. If salience service changes proto, no test catches it
  - Add 3 tests: missing field, type mismatch, exception handling

- **EventQueue candidate passing to Executive** (event_queue.py:237):
  - Risk: Introspection-based callback signature detection is fragile
  - Add 2 tests: accepts candidates, rejects candidates

- **Learning strategy configuration** (learning.py:178-193):
  - Risk: Configuration parsing from OrchestratorConfig not tested
  - Add 3 tests: valid config, missing keys, unknown strategy

- **Response subscriber filtering** (router.py:581-584):
  - Risk: Response source filter and include_immediate flag not tested
  - Add 2 tests for filtering logic

### Priority 3: Lower-Risk Gaps

- **GetQueueStats/GetHealth**: Add tests for monitoring RPCs. (3 tests)
- **cleanup_expired background loop**: Test loop startup and interval timing. (2 tests)
