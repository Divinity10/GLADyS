# Dashboard Heuristics Tab Design

**Status**: Design complete, ready for implementation
**Date**: 2026-02-03
**Branch**: `dashboard/response-heuristics-tabs`
**Blocks**: PoC 1 assessment (#63, #65)

## Problem Statement

The Heuristics tab doesn't render data despite the API working. Root cause: the tab uses Alpine x-for for data rendering, which doesn't work reliably when content is loaded via htmx.

Previous fix attempts failed because they tried to debug x-for instead of recognizing the pattern mismatch.

## Current State Analysis

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| JSON API | `fun_api/routers/heuristics.py` | Working |
| Frontend template | `frontend/components/heuristics.html` | Broken (uses x-for) |
| gRPC for list | `QueryHeuristics(min_confidence=0, limit=200)` | Working |
| gRPC for create | `StoreHeuristic` | Working |
| gRPC for update | `StoreHeuristic` (upsert) | Working |
| gRPC for delete | **None** — uses direct DB | Tech debt #83 |
| HTML router | `backend/routers/heuristics.py` | **Does not exist** |

### Data Flow (Current)

```
heuristics.html
    │
    │  Alpine x-init: fetch('/api/heuristics')
    ▼
fun_api/routers/heuristics.py
    │
    │  stub.QueryHeuristics(min_confidence=0, limit=200)
    ▼
Memory gRPC (50051)
    │
    ▼
PostgreSQL → JSON response → Alpine x-for (BROKEN)
```

### Why x-for Fails

When htmx dynamically loads HTML containing `<template x-for="...">`, Alpine may initialize but x-for doesn't render DOM elements. This is a known htmx/Alpine integration issue — not a bug to fix, but a pattern to avoid.

**Evidence**: API returns 5 heuristics. Alpine console shows `heuristics` array with 5 items. But the DOM has 0 table rows.

## Target State

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  heuristics.html (htmx container)                               │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Toolbar (Alpine x-data for filter state)                  │ │
│  │ - Origin dropdown                                         │ │
│  │ - Active dropdown                                         │ │
│  │ - Search input                                            │ │
│  │ - Refresh button                                          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ #heuristics-list (htmx swap target)                       │ │
│  │                                                           │ │
│  │ hx-get="/api/heuristics/rows"                            │ │
│  │ hx-trigger="load"                                        │ │
│  │                                                           │ │
│  │ Server renders rows with Jinja {% for %}                 │ │
│  │ Each row has Alpine x-data for expansion/editing         │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow (Target)

```
heuristics.html
    │
    │  htmx: hx-get="/api/heuristics/rows?origin=...&active=..."
    ▼
backend/routers/heuristics.py (NEW)
    │
    │  stub.QueryHeuristics(min_confidence=0, limit=200)
    │  Server-side filtering by origin, active, search
    │  Jinja renders heuristics_rows.html
    ▼
Memory gRPC (50051)
    │
    ▼
PostgreSQL → Rendered HTML → htmx swaps into DOM
```

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/routers/heuristics.py` | CREATE | HTML endpoints for htmx |
| `frontend/components/heuristics_row.html` | CREATE | Single row template |
| `frontend/components/heuristics_rows.html` | CREATE | Loop wrapper |
| `frontend/components/heuristics.html` | REWRITE | htmx container, no x-for |
| `backend/main.py` | MODIFY | Import and mount new router |
| `tests/test_heuristics_rows.py` | CREATE | Endpoint tests |

## Detailed Specifications

### 1. Backend Router: `backend/routers/heuristics.py`

```python
"""Heuristics router — HTMX/HTML endpoints for Pattern A rendering."""

from typing import Optional
import grpc
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT, env, PROTOS_AVAILABLE

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api")
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


def _heuristic_match_to_dict(match) -> dict:
    """Convert HeuristicMatch proto to template-ready dict."""
    h = match.heuristic
    return {
        "id": h.id,
        "name": h.name,
        "condition_text": h.condition_text,
        "effects_json": h.effects_json,
        "confidence": h.confidence,
        "origin": h.origin,
        "origin_id": h.origin_id,
        # Proto doesn't have 'active' — use fallback
        "active": getattr(h, "active", True) if hasattr(h, "active") else True,
        "fire_count": h.fire_count,
        "success_count": h.success_count,
        "created_at_ms": h.created_at_ms,
        "updated_at_ms": h.updated_at_ms,
    }


@router.get("/heuristics/rows")
async def list_heuristics_rows(
    request: Request,
    origin: Optional[str] = None,
    active: Optional[str] = None,  # "all", "active", "inactive"
    search: Optional[str] = None,
):
    """Return rendered heuristic rows for htmx."""
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        # Use QueryHeuristics with permissive params to list all
        resp = await stub.QueryHeuristics(memory_pb2.QueryHeuristicsRequest(
            min_confidence=0.0,
            limit=200,
        ))

        heuristics = [_heuristic_match_to_dict(m) for m in resp.matches]

        # Server-side filtering
        if origin:
            heuristics = [h for h in heuristics if h["origin"] == origin]
        if active == "active":
            heuristics = [h for h in heuristics if h["active"]]
        elif active == "inactive":
            heuristics = [h for h in heuristics if not h["active"]]
        if search:
            q = search.lower()
            heuristics = [h for h in heuristics if
                q in h["id"].lower() or
                q in (h["name"] or "").lower() or
                q in (h["condition_text"] or "").lower()]

        return templates.TemplateResponse(request, "components/heuristics_rows.html", {
            "heuristics": heuristics
        })

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')
```

### 2. Template: `heuristics_rows.html`

```jinja2
{% for h in heuristics %}
    {% include 'components/heuristics_row.html' %}
{% endfor %}

{% if not heuristics %}
<div class="p-8 text-center text-gray-500">No heuristics found.</div>
{% endif %}
```

### 3. Template: `heuristics_row.html`

Each row has its own Alpine x-data for UI state (expansion, editing). Data values come from Jinja.

Key principle: **Jinja renders data, Alpine handles interactivity.**

```jinja2
<div class="border-b border-gray-700 hover:bg-gray-800/50"
     x-data="{ expanded: false, editing: false }">

    <!-- Row -->
    <div class="grid grid-cols-[30px_20px_80px_80px_1fr_100px_60px_50px] gap-4 px-4 py-3 items-center text-sm">

        <!-- Checkbox -->
        <div>
            <input type="checkbox" value="{{ h.id }}"
                   onchange="heuristicsSelection.toggle('{{ h.id }}')"
                   class="rounded bg-gray-700 border-gray-600">
        </div>

        <!-- Expand chevron -->
        <div @click="expanded = !expanded" class="cursor-pointer text-gray-500"
             :class="{ 'rotate-90': expanded }">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
            </svg>
        </div>

        <!-- Origin badge -->
        <div>
            <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold
                {% if h.origin == 'learned' %}bg-purple-900/50 text-purple-400 border border-purple-800
                {% elif h.origin == 'user' %}bg-blue-900/50 text-blue-400 border border-blue-800
                {% else %}bg-gray-700 text-gray-300{% endif %}">
                {{ h.origin }}
            </span>
        </div>

        <!-- ID (truncated) -->
        <div class="text-gray-500 font-mono text-xs truncate" title="{{ h.id }}">
            {{ h.id[:8] }}
        </div>

        <!-- Condition -->
        <div class="text-gray-300 font-mono text-xs truncate" title="{{ h.condition_text }}">
            {{ h.condition_text[:60] if h.condition_text else '(empty)' }}
        </div>

        <!-- Confidence bar -->
        <div>
            <div class="flex items-center gap-2">
                <div class="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div class="h-full bg-blue-500" style="width: {{ (h.confidence * 100)|int }}%"></div>
                </div>
                <span class="text-xs text-gray-400 w-8 text-right">{{ (h.confidence * 100)|int }}%</span>
            </div>
        </div>

        <!-- Fire count (links to Response tab) -->
        <div>
            <span class="text-blue-400 hover:text-blue-300 hover:underline cursor-pointer text-xs"
                  onclick="switchToResponseTab('{{ h.id }}')">
                {{ h.fire_count or 0 }}
            </span>
        </div>

        <!-- Active toggle -->
        <div>
            <button onclick="toggleHeuristicActive('{{ h.id }}', {{ 'true' if h.active else 'false' }})"
                    class="relative inline-flex h-5 w-9 items-center rounded-full
                           {% if h.active %}bg-green-600{% else %}bg-gray-700{% endif %}">
                <span class="inline-block h-3 w-3 rounded-full bg-white transition-transform
                             {% if h.active %}translate-x-5{% else %}translate-x-1{% endif %}"></span>
            </button>
        </div>
    </div>

    <!-- Drill-down -->
    <div x-show="expanded" x-collapse class="bg-gray-900/50 border-t border-gray-800 p-6 text-sm">
        <div class="grid grid-cols-2 gap-4 text-xs text-gray-500">
            <div><span class="font-bold">Full ID:</span> <span class="font-mono text-gray-400">{{ h.id }}</span></div>
            <div><span class="font-bold">Origin ID:</span> <span class="font-mono text-gray-400">{{ h.origin_id or 'N/A' }}</span></div>
            <div><span class="font-bold">Fires:</span> {{ h.fire_count or 0 }}</div>
            <div><span class="font-bold">Successes:</span> {{ h.success_count or 0 }}</div>
        </div>
        <div class="mt-4 flex justify-end">
            <button onclick="deleteHeuristic('{{ h.id }}')"
                    class="text-red-400 hover:text-red-300 text-xs">Delete</button>
        </div>
    </div>
</div>
```

### 4. Container: `heuristics.html` (rewrite)

Remove all Alpine x-for. Keep Alpine only for toolbar filter state.

```html
<div id="heuristics-tab" class="h-full flex flex-col">

    <!-- Toolbar -->
    <div x-data="heuristicsToolbar()" class="flex items-center gap-4 p-4 border-b border-gray-700 bg-gray-900">
        <select x-model="origin" @change="refresh()"
                class="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm">
            <option value="">All Origins</option>
            <option value="learned">Learned</option>
            <option value="user">User</option>
            <option value="built_in">Built-in</option>
        </select>

        <select x-model="active" @change="refresh()"
                class="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm">
            <option value="all">All Status</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
        </select>

        <input type="text" x-model="search" @input.debounce.300ms="refresh()"
               placeholder="Search..." class="flex-1 max-w-md bg-gray-800 border border-gray-600 rounded px-3 py-1 text-sm">

        <button @click="refresh()" class="text-gray-400 hover:text-white" title="Refresh">
            <svg class="w-4 h-4">...</svg>
        </button>
    </div>

    <!-- Bulk actions -->
    <div id="bulk-bar" style="display: none" class="bg-blue-900/30 border-b border-blue-800 px-4 py-2">
        <span id="selected-count">0</span> selected
        <button onclick="bulkDelete()" class="text-red-400 ml-4">Delete Selected</button>
    </div>

    <!-- Table header -->
    <div class="grid grid-cols-[30px_20px_80px_80px_1fr_100px_60px_50px] gap-4 px-4 py-2 bg-gray-800 text-xs font-medium text-gray-400 uppercase">
        <div><input type="checkbox" onclick="toggleSelectAll()"></div>
        <div></div>
        <div>Origin</div>
        <div>ID</div>
        <div>Condition</div>
        <div>Confidence</div>
        <div>Fires</div>
        <div>Active</div>
    </div>

    <!-- Rows (htmx loads server-rendered HTML) -->
    <div id="heuristics-list" class="flex-1 overflow-y-auto"
         hx-get="/api/heuristics/rows"
         hx-trigger="load"
         hx-swap="innerHTML">
        <div class="p-8 text-center text-gray-500">Loading...</div>
    </div>
</div>

<script>
function heuristicsToolbar() {
    return {
        origin: '',
        active: 'all',
        search: '',
        refresh() {
            const params = new URLSearchParams();
            if (this.origin) params.set('origin', this.origin);
            if (this.active !== 'all') params.set('active', this.active);
            if (this.search) params.set('search', this.search);
            const url = '/api/heuristics/rows' + (params.toString() ? '?' + params : '');
            htmx.ajax('GET', url, { target: '#heuristics-list' });
        }
    };
}

// Selection state (global)
const heuristicsSelection = {
    selected: new Set(),
    toggle(id) {
        if (this.selected.has(id)) this.selected.delete(id);
        else this.selected.add(id);
        this.updateUI();
    },
    updateUI() {
        document.getElementById('bulk-bar').style.display = this.selected.size > 0 ? '' : 'none';
        document.getElementById('selected-count').textContent = this.selected.size;
    }
};

// Actions (call existing JSON API)
async function deleteHeuristic(id) {
    if (!confirm('Delete this heuristic?')) return;
    await fetch(`/api/heuristics/${id}`, { method: 'DELETE' });
    htmx.ajax('GET', '/api/heuristics/rows', { target: '#heuristics-list' });
}

async function toggleHeuristicActive(id, current) {
    await fetch(`/api/heuristics/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: !current })
    });
    htmx.ajax('GET', '/api/heuristics/rows', { target: '#heuristics-list' });
}

async function bulkDelete() {
    const ids = [...heuristicsSelection.selected];
    if (!confirm(`Delete ${ids.length} heuristics?`)) return;
    await fetch('/api/heuristics', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids })
    });
    heuristicsSelection.selected.clear();
    heuristicsSelection.updateUI();
    htmx.ajax('GET', '/api/heuristics/rows', { target: '#heuristics-list' });
}

function switchToResponseTab(heuristicId) {
    // Dispatch event for tab switching (existing pattern)
    window.dispatchEvent(new CustomEvent('switch-tab', {
        detail: { tab: 'response', filter: 'matched_heuristic_id', value: heuristicId }
    }));
}
</script>
```

### 5. Update `backend/main.py`

```python
# Add import
from backend.routers import heuristics as backend_heuristics

# Add router (after other backend routers)
app.include_router(backend_heuristics.router)
```

## Known Limitations

### Proto Gaps (Accepted for PoC 1)

| Gap | Workaround |
|-----|------------|
| No `active` field in proto | Use `getattr(h, "active", True)` fallback |
| No `ListHeuristics` RPC | Use `QueryHeuristics(min_confidence=0, limit=200)` |
| No `DeleteHeuristic` RPC | Direct DB delete via JSON API (tech debt #83) |

### Rust Cache Bug

Deleting a heuristic does not notify Rust to evict from cache. Stale heuristic may continue matching until TTL expires or manual flush.

**Mitigation**: After delete, call cache flush or wait for TTL. Proper fix requires adding `NotifyHeuristicChange` call in delete path.

## Testing

### Unit Tests (TDD-viable)

See `docs/prompts/fix-heuristics-server-side-render.md` for complete test code.

| Test | Verifies |
|------|----------|
| `test_heuristics_rows_returns_html` | Endpoint returns TemplateResponse |
| `test_heuristics_rows_filters_by_origin` | Origin filter works |
| `test_heuristics_rows_filters_by_active` | Active filter works |
| `test_heuristics_rows_filters_by_search` | Search filter works |
| `test_heuristics_rows_no_stub_returns_error` | Graceful error on stub unavailable |
| `test_heuristics_rows_grpc_error_returns_error_html` | gRPC errors return HTML, not 500 |

### Manual Tests (Required)

| Test | Steps |
|------|-------|
| Initial load | Navigate to Heuristics tab, verify rows display |
| Origin filter | Select "Learned", verify only learned heuristics show |
| Active filter | Select "Inactive", verify only inactive show |
| Search | Type partial condition text, verify filtering |
| Row expansion | Click chevron, verify drill-down appears |
| Delete | Click delete in drill-down, confirm, verify row removed |
| Bulk delete | Select 2+, click Delete Selected, verify removed |
| Fire count link | Click fire count, verify switches to Response tab filtered |
| Active toggle | Click toggle, verify state changes |

## Implementation Checklist

- [ ] Create `backend/routers/heuristics.py`
- [ ] Create `frontend/components/heuristics_row.html`
- [ ] Create `frontend/components/heuristics_rows.html`
- [ ] Rewrite `frontend/components/heuristics.html`
- [ ] Update `backend/main.py` to mount router
- [ ] Create `tests/test_heuristics_rows.py`
- [ ] Run `make test` — all pass
- [ ] Manual test all items above
- [ ] Commit: `fix(dashboard): render heuristics server-side instead of Alpine x-for`

## References

- `docs/design/DASHBOARD_COMPONENT_ARCHITECTURE.md` — Pattern A specification
- `docs/design/DASHBOARD_V2.md` — Overall dashboard design
- `docs/codebase/DASHBOARD.md` — Dual-router architecture, rendering patterns
- `fun_api/routers/heuristics.py` — Existing JSON API (keep for programmatic access)
