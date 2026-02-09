# Audit: Dashboard Service Test Coverage

## 1. Test Inventory

| Test file | Test count | Test type (unit/integration) |
|-----------|------------|------------------------------|
| `test_batch_events.py` | 6 | Unit (JSON API) |
| `test_events_converter.py` | 34 | Unit (Data processing) |
| `test_feedback.py` | 1 | Unit (HTML/HTMX) |
| `test_heuristics_rows.py` | 14 | Unit (HTML/HTMX) |
| `test_integration.py` | 8 | Browser Integration (Playwright) |
| `test_learning_rows.py` | 7 | Unit (HTML/HTMX) |
| `test_llm_api.py` | 7 | Unit (JSON API) |
| `test_logs_rows.py` | 6 | Unit (HTML/HTMX) |
| `test_responses.py` | 7 | Unit (HTML/HTMX) |
| `test_settings_api.py` | 5 | Unit (JSON API) |
| **Total** | **95** | |

## 2. Coverage Map

### Backend Routers (HTML rendering -- Pattern A)
- [x] Events: submit, list rows, queue rows, SSE streams
  - `test_integration.py`: `test_lab_tab_has_event_form`
  - SSE streams (`event_stream`) are **Untested**.
- [x] Responses: list rows, detail, bulk delete
  - `test_responses.py`: `test_list_responses`, `test_get_response_detail`, `test_bulk_delete_responses_success`
  - `list_response_rows` is **Untested**.
- [x] Feedback: positive/negative forwarding to executive
  - `test_feedback.py`: `test_feedback_forwards_response_id`
- [x] Heuristics: list rows, create, filtering (origin, search, active)
  - `test_heuristics_rows.py`: `test_heuristics_rows_returns_html`, `test_heuristics_rows_filters_by_origin`, `test_heuristics_rows_filters_by_search`, `test_heuristics_rows_filters_by_active`, `test_create_heuristic_success`
- [x] Fires/Learning: list rows, filtering (outcome, search)
  - `test_learning_rows.py`: `test_fires_rows_returns_html`, `test_fires_rows_filters_by_outcome`, `test_fires_rows_filters_by_search`
- [x] Logs: log lines with level classification
  - `test_logs_rows.py`: `test_logs_lines_returns_html`, `test_logs_lines_classifies_levels`
- [x] Services health
  - `test_integration.py`: `test_sidebar_shows_services`
- [ ] Metrics (Untested)

### Fun API Routers (JSON REST)
- [x] Batch events: submit, validation, max size
  - `test_batch_events.py`: `test_batch_returns_success_immediately`, `test_validation_error_returns_400`, `test_exceeds_max_batch_size_returns_400`
- [ ] Queue: list, delete event, delete all (Untested)
- [ ] Heuristics CRUD: list, create, update, delete, bulk delete (Untested)
- [x] LLM: status, test prompt, warm
  - `test_llm_api.py`: `test_status_connected_with_models`, `test_test_prompt_success`, `test_warm_success`
- [x] Cache: stats, entries, flush
  - `test_settings_api.py`: `test_cache_stats_returns_metrics`, `test_cache_entries_returns_heuristics`, `test_cache_flush_returns_count`
- [x] Config: get/set environment
  - `test_settings_api.py`: `test_get_config_returns_environment_info`, `test_set_environment_valid_mode`
- [ ] Logs: get logs by service (Untested)
- [ ] Services: start/stop/restart (Untested)

### Cross-Cutting
- [x] gRPC unavailable graceful degradation (error HTML, not HTTP 500)
  - `test_heuristics_rows.py`: `test_heuristics_rows_grpc_error_returns_error_html`
  - `test_learning_rows.py`: `test_fires_rows_grpc_error_returns_error_html`
- [x] Proto stubs unavailable (503 response)
  - `test_batch_events.py`: `test_proto_stubs_unavailable_returns_503`
  - `test_heuristics_rows.py`: `test_heuristics_rows_no_stub_returns_error`
- [x] Proto-to-dict conversion (events, salience, prediction fields)
  - `test_events_converter.py`: `TestProtoEventToDict`
- [x] Tab rendering (all tabs load without error)
  - `test_integration.py`: `TestTabRendering`
- [x] Sidebar service status
  - `test_integration.py`: `test_sidebar_shows_services`

## 3. Quality Assessment

- **Mock Accuracy**: High. Tests use `unittest.mock` effectively to simulate gRPC stubs and environment variables. The integration tests use Playwright to verify real browser behavior.
- **Assertion Quality**: Good. HTMX tests verify template names and context data. JSON API tests verify response bodies and status codes.
- **Edge Case Coverage**: Moderate. NULL handling and zero-value preservation in data conversion are well-covered. However, error paths for many API endpoints (especially Fun API) are untested.
- **One Behavior per Test**: Strictly followed.
- **Duplicate Coverage**: Minimal. Integration tests complement unit tests without excessive overlap.

## 4. Recommendations

### Priority 1 (Medium): Routing and Data Display
- **Fun API CRUD Coverage**: Add tests for Heuristics and Events CRUD in `fun_api`. These are programmatic entry points that should be as reliable as the UI. (5-6 tests)
- **Service Control API**: Test the service start/stop/restart endpoints in `fun_api/routers/services.py`. These modify system state and need validation. (3 tests)
- **Metrics Router**: Add tests for `backend/routers/metrics.py` to ensure the metrics strip on the dashboard correctly aggregates data from DB and cache. (2 tests)

### Priority 2 (Low): Edge Cases and Reliability
- **SSE Streams**: Add unit or integration tests for `event_stream` in `backend/routers/events.py`. Real-time updates are a core feature of the dashboard. (2 tests)
- **Log Retrieval (JSON)**: Add tests for `fun_api/routers/logs.py`. (1 test)
- **Queue API**: Add tests for `fun_api/routers/events.py` queue endpoints. (2 tests)
