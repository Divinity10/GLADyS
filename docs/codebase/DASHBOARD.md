# Dashboard (UI)

**Location**: `src/services/dashboard/`
**Framework**: FastAPI + htmx + Alpine.js
**Port**: 8502
**Design docs**:

- `docs/design/DASHBOARD_V2.md` -- overall design
- `docs/design/DASHBOARD_COMPONENT_ARCHITECTURE.md` -- rendering patterns

The dashboard provides a dev/debug interface for GLADyS with tabs for event simulation (Lab), response history (Response), heuristic management (Heuristics), fire history (Learning), LLM testing (LLM), log viewing (Logs), and configuration (Settings). Uses Server-Sent Events (SSE) for real-time event updates.

## Dual-Router Architecture (CRITICAL)

The dashboard has **two router layers** mounted in the same FastAPI app:

| Layer | Location | Returns | Purpose |
|-------|----------|---------|---------|
| **HTMX routers** | `src/services/dashboard/backend/routers/` | HTML | Server-side rendered partials for htmx |
| **JSON routers** | `src/services/fun_api/routers/` | JSON | REST API for programmatic access |

**IMPORTANT**: `fun_api/` is a **separate directory** at `src/services/fun_api/` (sibling to `dashboard/`). The dashboard imports it via `from fun_api.routers import ...`.

**main.py imports and mounts BOTH** (`src/services/dashboard/backend/main.py`):

```python
# HTMX routers (HTML) - from dashboard/backend/
from backend.routers import events, fires, heuristics, logs, ...
app.include_router(events.router)  # HTML

# JSON routers - from sibling fun_api/ directory
from fun_api.routers import heuristics, cache, fires, logs, ...
app.include_router(heuristics.router)  # JSON
```

## Rendering Patterns

See `docs/design/DASHBOARD_COMPONENT_ARCHITECTURE.md` for full details.

**Pattern A (server-side rendering)** -- for data lists:

- Backend renders HTML with Jinja `{% for %}` loops
- htmx fetches pre-rendered HTML
- Alpine.js only for row-level interactivity (expansion, editing)
- **Used by**: All tabs (Lab, Response, Heuristics, Learning, Logs, LLM, Settings)

**Pattern B (Alpine-only)** -- for UI controls:

- Static HTML with Alpine.js reactivity
- No data rendering, only toggles/modals/dropdowns
- **Used by**: Toolbar filters, sidebar controls

**Anti-pattern (DO NOT USE)**:

- Alpine x-for for server data in htmx-loaded content
- htmx + x-for doesn't work reliably (x-for may not render DOM)

## Data Access Paths

**JSON path** (for REST API consumers):

```
Dashboard UI -> fun_api/routers/heuristics.py -> gRPC QueryHeuristics -> Memory -> DB
                                              -> Direct DB delete (tech debt #83)
```

**HTML path** (for htmx -- Pattern A):

```
Dashboard UI -> backend/routers/heuristics.py -> gRPC QueryHeuristics -> Memory -> DB
               (returns rendered HTML via Jinja templates)

Dashboard UI -> backend/routers/fires.py -> gRPC ListFires -> Memory -> DB
Dashboard UI -> backend/routers/logs.py -> file read (no gRPC)
```

## Key Files

**Dashboard (HTML routers)** -- `src/services/dashboard/`:

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, mounts both router layers |
| `backend/env.py` | Environment singleton, gRPC channel management |
| `backend/routers/events.py` | Event CRUD, SSE stream, feedback, delete (HTML) |
| `backend/routers/responses.py` | Response history (HTML) |
| `backend/routers/heuristics.py` | Heuristic rows (HTML) |
| `backend/routers/fires.py` | Fire history rows (HTML) |
| `backend/routers/logs.py` | Log lines (HTML) |
| `frontend/index.html` | Layout shell with static sidebar |
| `frontend/components/*.html` | Jinja2 partials for tabs |

**FUN API (JSON routers)** -- `src/services/fun_api/`:

| File | Purpose |
|------|---------|
| `routers/heuristics.py` | Heuristic CRUD (JSON) |
| `routers/fires.py` | Fire history (JSON) |
| `routers/logs.py` | Log retrieval (JSON) |
| `routers/cache.py` | Rust cache stats/flush |
| `routers/llm.py` | Ollama status/test |

**Shared** -- `src/lib/gladys_client/`:

| File | Purpose |
|------|---------|
| `db.py` | All DB queries (events, heuristics, fires, metrics) |
