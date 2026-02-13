# Audit: Dashboard Service Test Coverage

**Report Date**: 2026-02-09
**Validated**: 2026-02-12
**Status**: +13 tests added (router registration). Major gaps remain in Fun API CRUD, SSE streams, service control. Dashboard is CRITICAL INFRASTRUCTURE.

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
| `test_router_registration.py` | 13 | Unit (Router precedence) |
| **Total** | **108** | (+13 since Feb 9) |

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

## 3. Obsolete Items (Since Feb 9)

- **"list_response_rows is Untested"** - NOW TESTED. Added in commit dacc371 (Feb 12), `test_responses.py` now has extensive coverage of list_responses, get_response_detail, bulk_delete (lines 12-191)

## 4. New Gaps (Since Feb 9)

1. **Heuristics Fun API (Full CRUD)** - `fun_api/routers/heuristics.py` lines 42-147:
   - GET/POST/PUT/DELETE for heuristics - all 5 endpoints UNTESTED
   - Create/update use gRPC + embedding generation (can fail silently)

2. **Event Stream (SSE) Enhanced** - Commit 84297a0 (Feb 12) added complex retry logic (4 attempts, exponential backoff), thread-safe asyncio integration. Still UNTESTED despite increased complexity

3. **Memory Probe Router** - `fun_api/routers/memory.py` - Similarity search in vector DB - UNTESTED

4. **Fires API** - `fun_api/routers/fires.py` - List heuristic fires with outcome filtering - UNTESTED

5. **Router Registration Tests** - NEW in commit 84297a0. `test_router_registration.py` (13 tests) now protects against router collision bugs

## 5. Completed (Since Feb 9)

- Router registration test suite (13 tests) - protects against batch endpoint shadowing bug
- Response router full coverage (9 tests total now)

## 6. Quality Assessment

- **Mock Accuracy**: High. Tests use `unittest.mock` effectively to simulate gRPC stubs and environment variables. The integration tests use Playwright to verify real browser behavior.
- **Assertion Quality**: Good. HTMX tests verify template names and context data. JSON API tests verify response bodies and status codes.
- **Edge Case Coverage**: Moderate. NULL handling and zero-value preservation in data conversion are well-covered. However, error paths for many API endpoints (especially Fun API) are untested.
- **One Behavior per Test**: Strictly followed.
- **Duplicate Coverage**: Minimal. Integration tests complement unit tests without excessive overlap.

## 7. Recommendations

### Priority 1: CRITICAL INFRASTRUCTURE (recommend Gemini trace)

**Dashboard is critical infrastructure per CLAUDE.md. Without a working dashboard, there is no way to troubleshoot, tune, or validate the system.**

- **SSE Event Stream** (`backend/routers/events.py` lines 456-542):
  - Risk: Real-time event updates are core dashboard feature. Stream has complex retry logic, async/sync bridge, cross-service fetching. Failure modes: silent stream death, incomplete data, memory leaks, connection timeouts
  - Add 2-3 end-to-end tests: happy path (event arrives, renders HTML), error paths (memory timeout, orchestrator down)

- **Heuristics CRUD API** (`fun_api/routers/heuristics.py` lines 42-147):
  - Risk: Programmatic interface for external systems + learning automation. All 5 endpoints untested. Failure modes: partial creation (proto succeeds, embedding fails), orphaned DB records, inconsistent state
  - Add 4-5 tests: successful CRUD cycle, gRPC errors, DB failures, validation errors, state consistency

- **Service Control API** (`fun_api/routers/services.py` lines 60-80):
  - Risk: System state modification. No verification backend methods actually succeed. Failure modes: service doesn't restart, process hung, dashboard shows "success" but service dead
  - Add 3 tests with mocked backend: successful start/stop/restart, backend exception handling, subprocess timeout

### Priority 2: Important Operational Features

- **Queue API** - 3 endpoints (`fun_api/routers/events.py`): proto stub unavailability, gRPC error handling, DB deletion verification (2-3 tests)
- **Logs API** - Missing file handling, large file tail, encoding errors (2-3 tests)
- **Memory Probe** - Query validation, proto stub availability, gRPC errors (2 tests)
- **Fires API** - Outcome filtering, DB query errors (2 tests)
- **Metrics Router** - Aggregation from 3 sources, graceful degradation when source fails (2 tests)

### Priority 3: Nice-to-Have

- Backend batch endpoint explicit test (1 test)
- Response stream alias verification (documentation only)
