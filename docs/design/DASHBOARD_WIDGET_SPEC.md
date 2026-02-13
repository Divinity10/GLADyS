# Dashboard Widget Specification

**Status**: Approved design
**Date**: 2026-02-03 (revised)
**Parent**: [DASHBOARD_V2.md](DASHBOARD_V2.md), [DASHBOARD_COMPONENT_ARCHITECTURE.md](DASHBOARD_COMPONENT_ARCHITECTURE.md)
**Purpose**: Define testable, self-contained widget patterns for reliable dashboard development

## Context

The dashboard is **critical infrastructure** for GLADyS development. Without it, there is no way to verify the pipeline works, troubleshoot issues, or tune the system.

**Problem solved**: 2+ days lost to dashboard debugging. Components broke in non-obvious ways. No tests to catch issues before manual testing.

**Solution**: Testable widget patterns with clear requirements. When tests pass, the widget works.

---

## Design Principles

1. **Tabs are stable, components are volatile** — Tab structure rarely changes, but components within tabs change as backend evolves.

2. **Components don't share templates** — Each component (e.g., Lab events vs Response events) is separate. They share CSS classes and conventions, not templates.

3. **Canonical example over specification** — Heuristics tab is the reference implementation. New DataTables copy this pattern.

4. **Tests prove correctness** — Unit tests (every commit) + integration tests (pre-merge). If tests pass and browser shows rows, it works.

---

## Responsibility Separation

| Layer | Responsibility | Does NOT do |
|-------|----------------|-------------|
| **Server (Jinja)** | Renders HTML with data via `{% for %}` | Client-side filtering |
| **htmx** | Fetches HTML, swaps into DOM | Data transformation |
| **Alpine.js** | UI state (expand, edit mode, filter selections) | Data rendering |

**Critical constraint:** Alpine x-for MUST NOT be used with server data. It fails when htmx loads content dynamically.

---

## DataTable Pattern

**Canonical example**: Heuristics tab (`backend/routers/heuristics.py`, `heuristics.html`, `heuristics_rows.html`, `heuristics_row.html`)

### Files Required

```
backend/routers/{entity}.py           # /api/{entity}/rows endpoint
frontend/components/{entity}.html     # Container: toolbar + htmx target
frontend/components/{entity}_rows.html # Jinja {% for %} loop
frontend/components/{entity}_row.html  # Single row with Alpine expand
tests/test_{entity}_rows.py           # Required tests
```

### Endpoint Contract

```
GET /api/{entity}/rows?filter1=value&filter2=value&search=text
Returns: HTML (TemplateResponse)
Errors: HTML with error message (not HTTP 500)
```

### Required Tests

#### Unit Tests (run every commit)

| # | Test | What it catches |
|---|------|-----------------|
| 1 | Endpoint returns 200 + HTML | Backend crashes, import errors |
| 2 | HTML contains expected row count | Template bugs, empty results |
| 3 | Each filter param reduces results | Server-side filtering broken |
| 4 | Missing service → error HTML | Blank screen on stub unavailable |
| 5 | gRPC error → error HTML | Unhandled exceptions |
| 6 | Link href/dispatch is correct | Cross-tab navigation broken |
| 7 | Button posts to correct endpoint | Action buttons do nothing |

#### Integration Tests (run pre-merge)

| # | Test | What it catches |
|---|------|-----------------|
| 1 | Tab loads → rows visible in DOM | htmx/Alpine rendering failures |
| 2 | Click cross-tab link → other tab loads | Navigation broken in browser |
| 3 | Click action button → feedback appears | UI gives no feedback |

### Implementation Checklist

When adding a new DataTable, follow this checklist:

```
□ Backend
  □ Create backend/routers/{entity}.py
  □ Add GET /api/{entity}/rows endpoint
  □ Return TemplateResponse (not JSON)
  □ Handle filters via query params
  □ Return error HTML on service failure (stub unavailable, gRPC error)

□ Frontend
  □ Create {entity}.html (container + toolbar)
  □ Create {entity}_rows.html (Jinja {% for %} loop)
  □ Create {entity}_row.html (single row + expand)
  □ Use hx-get pointing to /api/{entity}/rows
  □ NO Alpine x-for for data rendering

□ Tests (unit)
  □ Create tests/test_{entity}_rows.py
  □ Test: returns HTML with rows
  □ Test: each filter works
  □ Test: stub unavailable → error HTML
  □ Test: gRPC error → error HTML
  □ Test: cross-tab links correct (if any)
  □ Test: action buttons post correctly (if any)

□ Tests (integration)
  □ Add to integration suite
  □ Test: rows visible after load
  □ Test: cross-tab links work (if any)
  □ Test: action buttons show feedback (if any)

□ Wire up
  □ Register router in backend/main.py
  □ Add tab to index.html (if new tab)

□ Verify
  □ All unit tests pass
  □ All integration tests pass
  □ Rows render in browser
```

---

## Current Tab Status

| Tab | Pattern | Status | Tests |
|-----|---------|--------|-------|
| Lab | DataTable + SSE | ✅ Working | Partial |
| Response | DataTable | ✅ Working | Partial |
| Heuristics | DataTable | ✅ Working (canonical) | 6/7 unit, 0 integration |
| Learning | x-for (broken) | ❌ Needs migration | None |
| Logs | DataTable | ✅ Working | 3 unit |
| LLM | Alpine JSON fetch | ✅ Working | 7 unit |
| Settings | Alpine JSON fetch | ✅ Working | 11 unit |

### Pattern Notes

**DataTable (Pattern A)**: htmx fetches server-rendered HTML rows. Jinja `{% for %}` on server.

**Alpine JSON fetch**: htmx loads template once, Alpine fetches JSON via JavaScript `fetch()`, x-for renders from Alpine reactive state. This is a valid pattern because x-for renders from client-side state, not htmx-loaded content.

**x-for (broken)**: htmx loads HTML containing x-for directives that try to render server data. This pattern fails because Alpine may not initialize correctly on htmx-injected content.

---

## Other Widget Types (Future)

These patterns are documented for reference but not yet proven with working implementations.

### ProbeForm

**Purpose**: Input form that queries a service and displays results.
**Use cases**: Memory similarity probe, LLM test prompt
**Status**: Not yet implemented with Pattern A

### StatusDisplay

**Purpose**: Read-only display of status information, optionally auto-refreshing.
**Use cases**: Service health, LLM status, config display
**Status**: Sidebar health uses this pattern

### ActionForm

**Purpose**: Form that performs an action (create, submit, trigger).
**Use cases**: Event submission (Lab tab sticky bar)
**Status**: Lab tab event submission works, not formally tested

---

## Dashboard Completion Plan

| Phase | Work | Checkpoint |
|-------|------|-----------|
| 1 | Document pattern | This spec updated ✅ |
| 2 | Heuristics tests complete | All 7 unit tests pass |
| 3 | Learning tab migrated | Pattern A, tests pass, rows render |
| 4 | Logs tab migrated | Pattern A, tests pass, logs display ✅ |
| 5 | LLM/Settings audited | Audit complete, uses valid pattern ✅ |
| 6 | Integration tests | Suite exists, runs pre-merge |

**Rules**:

- Each phase ends with "tests pass" + "works in browser"
- No phase is complete until both verified
- Phase N must complete before Phase N+1 starts

---

## Reference: Heuristics Implementation

The heuristics tab is the canonical example. Key files:

### Backend (`backend/routers/heuristics.py`)

```python
@router.get("/heuristics/rows")
async def list_heuristics_rows(
    request: Request,
    origin: Optional[str] = None,
    active: Optional[str] = None,
    search: Optional[str] = None,
):
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        resp = await stub.QueryHeuristics(memory_pb2.QueryHeuristicsRequest(
            min_confidence=0.0, limit=200
        ))
        heuristics = [_heuristic_match_to_dict(m) for m in resp.matches]

        # Server-side filtering
        if origin:
            heuristics = [h for h in heuristics if h["origin"] == origin]
        # ... more filters

        return templates.TemplateResponse(request, "components/heuristics_rows.html", {
            "heuristics": heuristics
        })

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')
```

### Frontend container (`heuristics.html`)

- Alpine `x-data` for toolbar state (filter values, search query)
- `refresh()` function builds URL with query params, triggers htmx
- `hx-get="/api/heuristics/rows"` on the rows container
- NO Alpine x-for

### Rows template (`heuristics_rows.html`)

```jinja2
{% for h in heuristics %}
    {% include 'components/heuristics_row.html' %}
{% endfor %}

{% if not heuristics %}
<div class="p-8 text-center text-gray-500">No heuristics found.</div>
{% endif %}
```

### Single row (`heuristics_row.html`)

- `x-data="{ expanded: false, editingCondition: false, ... }"` for row UI state
- Jinja renders all data fields
- Alpine handles expand/collapse, inline editing

### Tests (`tests/test_heuristics_rows.py`)

See the actual file for complete test patterns. Key pattern: mock the gRPC stub, call the endpoint, assert response contains expected data.
