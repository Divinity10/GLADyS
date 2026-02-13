# Dashboard Component Architecture

**Status**: Approved design
**Date**: 2026-02-03
**Parent**: [DASHBOARD_V2.md](DASHBOARD_V2.md)
**Related**: [DASHBOARD_WIDGET_SPEC.md](DASHBOARD_WIDGET_SPEC.md) — testable widget contract
**Purpose**: Clarify rendering patterns to prevent htmx/Alpine integration bugs
**Background**: [widget_discussion.md](../reviews/widget_discussion.md) — 2+ hours lost to debugging, established widget pattern

## The Problem

The dashboard uses htmx for dynamic content loading and Alpine.js for client-side interactivity. These libraries have a subtle but critical integration issue:

**When htmx dynamically loads HTML containing Alpine x-for templates, the x-for directives may not render DOM elements** — even if Alpine initializes correctly and the data is present.

This happened with the Heuristics tab: API returns data, Alpine has it in reactive state, but no rows render.

## The Solution: Server-Side Rendering for Data Lists

**Rule**: All data tables and lists MUST use **server-side rendering** with Jinja loops. Alpine.js is for **interactivity only** (toggles, modals, local UI state).

## Rendering Patterns

### Pattern A: Server-Rendered Table (REQUIRED for data lists)

Use for: Event tables, heuristics lists, response lists, queue display, any list of database records.

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                     │
│                                                             │
│  1. htmx requests /api/something/rows                       │
│  2. Server renders HTML with Jinja {% for item in items %}  │
│  3. htmx swaps rendered HTML into DOM                       │
│  4. Alpine.js initializes for row-level interactivity       │
└─────────────────────────────────────────────────────────────┘
```

**Backend** (FastAPI):

```python
@router.get("/api/heuristics/rows")
async def list_heuristics_rows(request: Request, ...):
    heuristics = await fetch_heuristics(...)
    return templates.TemplateResponse(request, "components/heuristics_rows.html", {
        "heuristics": heuristics
    })
```

**Template** (heuristics_rows.html):

```jinja2
{% for h in heuristics %}
<tr x-data="{ expanded: false, editing: false }" class="...">
    <td>{{ h.id[:8] }}</td>
    <td @click="expanded = !expanded">{{ h.condition_text[:60] }}</td>
    <!-- Alpine for row-level interactivity, NOT for rendering the row -->
</tr>
{% endfor %}
```

**Container** (heuristics.html):

```html
<div id="heuristics-tab">
    <!-- Toolbar with Alpine for filter state -->
    <div x-data="{ filterOrigin: '', searchQuery: '' }">
        <select x-model="filterOrigin" @change="htmx.trigger('#heuristics-list', 'refresh')">
            ...
        </select>
    </div>

    <!-- Table body loaded via htmx -->
    <tbody id="heuristics-list"
           hx-get="/api/heuristics/rows"
           hx-trigger="load, refresh from:body"
           hx-swap="innerHTML">
        <!-- Server renders rows here -->
    </tbody>
</div>
```

### Pattern B: Alpine-Only Component (for non-list UI)

Use for: Modals, dropdowns, tab state, form validation, local UI toggles.

```html
<div x-data="{ open: false, selected: null }">
    <button @click="open = !open">Toggle</button>
    <div x-show="open">...</div>
</div>
```

This is safe because the HTML structure is static — Alpine only toggles visibility/state.

### Pattern C: SSE for Real-Time Updates (supplement to Pattern A)

Use for: Live event streaming, response arrivals.

```html
<tbody id="event-table-body"
       hx-ext="sse"
       sse-connect="/api/events/stream"
       sse-swap="message"
       hx-swap="afterbegin">
    {% for event in initial_events %}
        {% include 'components/event_row.html' %}
    {% endfor %}
</tbody>
```

Server sends pre-rendered HTML rows via SSE. htmx inserts them.

## Anti-Patterns (DO NOT USE)

### Anti-Pattern: Alpine x-for for Server Data

```html
<!-- BROKEN: x-for doesn't render when content is htmx-loaded -->
<div x-data="{ items: [] }" x-init="items = await fetch('/api/items').then(r => r.json())">
    <template x-for="item in items">
        <tr>...</tr>  <!-- This may not render! -->
    </template>
</div>
```

### Anti-Pattern: Mixing htmx Swap Target with Alpine Reactive State

```html
<!-- BROKEN: htmx swap destroys Alpine state -->
<div x-data="{ count: 0 }">
    <div id="swap-target" hx-get="/api/data" hx-swap="innerHTML">
        <!-- Alpine state lost on swap -->
    </div>
    <button @click="count++">Count: <span x-text="count"></span></button>
</div>
```

## Component Specifications

### Status Summary

| Component | Pattern | Status | Priority |
|-----------|---------|--------|----------|
| Lab (events) | A + C | ✅ Working | P0 |
| Response | A | ✅ Working | P0 |
| Heuristics | A | ✅ Fixed (2026-02-03) | P0 |
| Sidebar | A | ✅ Working | P0 |
| Metrics Strip | A | ✅ Working | P1 |
| **Learning** | **x-for (broken)** | ❌ NEEDS MIGRATION | P1 |
| **Logs** | **x-for (broken)** | ❌ NEEDS MIGRATION | P2 |
| **LLM** | **x-for (broken)** | ❌ NEEDS AUDIT | P2 |
| **Settings** | **x-for (broken)** | ❌ NEEDS AUDIT | P3 |

### Lab Tab (events)

- **Data source**: SSE stream + initial server render
- **Rendering**: Pattern A + Pattern C
- **Files**: `lab.html`, `event_row.html`, `events.py`
- **Alpine uses**: Row expansion, filter state (client-side filtering of rendered rows)
- **Status**: ✅ Working

### Response Tab

- **Data source**: gRPC → Memory service → PostgreSQL
- **Rendering**: Pattern A
- **Files**: `response.html`, `response_rows.html`, `response_detail.html`, `responses.py`
- **Alpine uses**: Row expansion, filter dropdowns, drill-down state
- **Status**: ✅ Working

### Heuristics Tab

- **Data source**: gRPC → Memory service → PostgreSQL
- **Rendering**: Pattern A
- **Files**: `heuristics.html`, `heuristics_rows.html`, `heuristics_row.html`, `backend/routers/heuristics.py`
- **Alpine uses**:
  - Toolbar: filter dropdowns, search input state
  - Per-row: expanded state, editing state, dirty flag
  - Bulk actions: selected IDs array
- **Status**: ✅ Fixed (2026-02-03)

### Learning Tab (NEEDS MIGRATION)

- **Data source**: REST `/api/fires` → JSON
- **Rendering**: ❌ BROKEN — uses Alpine x-for (`x-for="f in fires"`)
- **Files**: `learning.html`, `fun_api/routers/fires.py`
- **Alpine uses**: Fetches JSON, renders with x-for (ANTI-PATTERN)
- **Status**: ❌ Needs Pattern A migration
- **Migration needed**:
  1. Create `backend/routers/fires.py` (HTML)
  2. Create `learning_rows.html` with Jinja loop
  3. Rewrite `learning.html` to use htmx

### Logs Tab (NEEDS MIGRATION)

- **Data source**: REST `/api/logs/{service}` → JSON
- **Rendering**: ❌ BROKEN — uses Alpine x-for (`x-for="line in logs"`)
- **Files**: `logs.html`, `fun_api/routers/logs.py`
- **Alpine uses**: Fetches JSON, renders with x-for (ANTI-PATTERN)
- **Status**: ❌ Needs Pattern A migration

### LLM Tab (NEEDS AUDIT)

- **Data source**: REST `/api/llm/status` → JSON
- **Rendering**: ❌ Uses Alpine x-for for model lists
- **Files**: `llm.html`, `fun_api/routers/llm.py`
- **Alpine uses**: Fetches JSON, renders with x-for
- **Status**: ❌ May work (small lists) but uses anti-pattern — needs audit

### Settings Tab (NEEDS AUDIT)

- **Data source**: REST `/api/config`, `/api/cache/entries` → JSON
- **Rendering**: ❌ Uses Alpine x-for for config and cache entries
- **Files**: `settings.html`, `fun_api/routers/config.py`, `fun_api/routers/cache.py`
- **Alpine uses**: Fetches JSON, renders with x-for
- **Status**: ❌ Lower priority — needs audit

### Sidebar (services health)

- **Data source**: gRPC health checks
- **Rendering**: Pattern A (htmx polls, server renders)
- **Files**: `sidebar.html`, `services.py`
- **Alpine uses**: Service action buttons (start/stop pending state)
- **Status**: ✅ Working

### Metrics Strip

- **Data source**: DB queries + cache stats
- **Rendering**: Pattern A (htmx polls, server renders numbers)
- **Files**: `metrics.html`, `metrics.py`
- **Alpine uses**: None (pure display)
- **Status**: ✅ Working

## File Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Tab container | `{tab}.html` | `heuristics.html` |
| Table rows partial | `{tab}_rows.html` | `heuristics_rows.html` |
| Single row partial | `{tab}_row.html` | `heuristic_row.html` |
| Detail/drill-down | `{tab}_detail.html` | `heuristics_detail.html` |
| Router | `routers/{tab}.py` | `routers/heuristics.py` |

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                Browser                                       │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   Tab Content   │    │  Alpine State   │    │   htmx Swap     │         │
│  │  (HTML shell)   │    │  (UI toggles)   │    │  (HTML replace) │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           │              Does NOT hold                  │                   │
│           │              server data                    │                   │
└───────────┼──────────────────────┼──────────────────────┼───────────────────┘
            │                                             │
            │ GET /api/{tab}                              │ GET /api/{tab}/rows
            │ (initial load)                              │ (filter/paginate)
            ▼                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  templates.TemplateResponse("components/{tab}_rows.html", {data})   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ Jinja renders {% for item in items %}  │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Pre-rendered HTML string with all rows                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────┬─────────────────────────────────────────────────────────────────┘
            │
            │ gRPC
            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Memory Service (Python) → PostgreSQL                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Testing Requirements

Each table component must pass these tests:

1. **Initial load**: Tab displays data on first visit
2. **Filter**: Changing filter updates displayed rows
3. **Pagination**: "Load more" appends additional rows
4. **Refresh**: Explicit refresh updates data
5. **Alpine interactivity**: Row expansion, inline editing work
6. **Cross-tab navigation**: Links to other tabs work

## Implementation Checklist for New Tables

- [ ] Create `{tab}_rows.html` with Jinja `{% for %}` loop
- [ ] Create `{tab}_row.html` for single row template (include in loop)
- [ ] Add `@router.get("/api/{tab}/rows")` endpoint returning TemplateResponse
- [ ] Add `@router.get("/api/{tab}")` endpoint returning full tab (initial load)
- [ ] Container has `hx-get` pointing to rows endpoint
- [ ] Alpine x-data on container handles only: toolbar state, bulk selection
- [ ] Alpine x-data on rows handles only: expanded, editing states
- [ ] No Alpine x-for for data rendering

## Migration Guide

### Completed Migrations

**Heuristics Tab** (2026-02-03): See `docs/prompts/fix-heuristics-server-side-render.md`

### Pending Migrations

Each broken tab needs the same pattern applied:

1. Create `backend/routers/{tab}.py` with HTML endpoint returning `TemplateResponse`
2. Create `{tab}_rows.html` with Jinja `{% for %}` loop
3. Create `{tab}_row.html` for single row (with Alpine x-data for expansion)
4. Rewrite `{tab}.html` to use htmx fetch instead of Alpine fetch + x-for
5. Keep Alpine only for: toolbar state, per-row expansion, local UI toggles

**Priority order**:

1. **Learning** — Needed for feedback loop validation (P1)
2. **Logs** — Useful for troubleshooting (P2)
3. **LLM** — May work as-is, audit first (P2)
4. **Settings** — Lowest priority (P3)
