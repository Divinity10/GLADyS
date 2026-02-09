# Audit: Orchestrator Service Test Coverage

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
| **Total** | **64** | |

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

## 3. Quality Assessment

- **Mock Accuracy**: High. Tests use `AsyncMock` and `MagicMock` effectively to simulate gRPC services and client responses.
- **Assertion Quality**: Very Good. Tests verify both return values and internal state changes (e.g., subscriber queue sizes, mock call counts).
- **Edge Case Coverage**: Moderate. Covers basic error paths (e.g., RPC failure) and threshold boundaries. However, complex event flows (streaming, batching) and implicit feedback loops (undo/ignore) are not fully exercised.
- **One Behavior per Test**: Strongly followed. Tests are well-isolated and focused.
- **Duplicate Coverage**: Low. The test suite is well-structured and efficient.

## 4. Recommendations

### Priority 1: Data Integrity & Event Flow
- **PublishEvent RPC**: Add tests for `PublishEvent` (unary) and `PublishEvents` (batch) in `test_server.py`. Verify that events are correctly routed and stored. (3 tests)
- **Implicit Feedback Loop**: Add tests for `check_event_for_outcomes` and `_check_undo_signal` in `test_learning_module.py`. Verify that undo keywords trigger negative feedback. (3 tests)
- **Ignore Logic**: Test `on_heuristic_ignored` to ensure the threshold-based negative feedback fires after N ignores. (2 tests)

### Priority 2: Contract Correctness
- **Streaming RPCs**: Add tests for `StreamEvents`, `SubscribeEvents`, and `SubscribeResponses`. Streaming is complex and currently untested. (4 tests)
- **Salience Evaluation Fallback**: Add tests for `_get_salience` in `test_router.py` to verify graceful degradation when the salience service is unavailable. (2 tests)

### Priority 3: Decision Logic & Monitoring
- **Queue Stats & Listing**: Add tests for `GetQueueStats` and `ListQueuedEvents` to verify monitoring data accuracy. (2 tests)
- **Health RPCs**: Add basic tests for `GetHealth` and `GetHealthDetails`. (2 tests)
- **Outcome Cleanup**: Test `cleanup_expired` in `LearningModule` to verify that timeouts are converted to positive implicit feedback. (2 tests)
