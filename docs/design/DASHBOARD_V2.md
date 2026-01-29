# Dashboard V2 Design

**Status**: Approved design
**Date**: 2026-01-28
**Authors**: Scott Mulcahy, Claude (design collaboration)

## Purpose

The GLADyS dashboard is a **developer tool** for troubleshooting, tuning, and evaluating the GLADyS event processing pipeline. It is not an end-user UI.

The V1 dashboard (Streamlit) has fundamental limitations:
- Rerun-on-interaction model breaks async response display
- Workarounds (polling fragments, pseudo-response objects, queue draining) fight the framework
- Information density constrained by opinionated layout
- gRPC channel leaks, unrecoverable subscription thread, sync/async mismatch

V2 replaces it entirely.

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | **FastAPI** (Python) | Bridges gRPC services to HTTP/SSE. Reuses existing Python gRPC client code. |
| Frontend | **Vanilla HTML/CSS/JS + htmx + Alpine.js** | No build toolchain. LLM-generated and LLM-maintainable. |
| Real-time | **Server-Sent Events (SSE)** | Native browser support, no WebSocket complexity. One-way push for event lifecycle updates, response arrivals. |
| State | **localStorage** | UI preferences persist across sessions. |

### Why this stack

- **FastAPI**: All gRPC clients are already Python. FastAPI is async-native, handles SSE natively, serves static files.
- **htmx**: Async updates with HTML attributes, almost no JavaScript. Server renders HTML fragments, htmx swaps them in.
- **Alpine.js**: Lightweight client-side reactivity for tabs, dropdowns, filters. No build step.
- **No React/Vue**: Overkill for a single-user dev tool. Adds build complexity that makes LLM modifications less reliable.
- **No Streamlit/Panel**: Framework-imposed layout and execution model conflicts with async data flow.

### Implementation approach

Gemini generates the frontend from this spec. Claude builds the FastAPI backend. Frontend talks to backend via REST + SSE. Backend talks to GLADyS services via gRPC.

## Features (ranked by troubleshooting value)

| Rank | Feature | Description |
|------|---------|-------------|
| 1 | Submit events | Single event (sticky bar) or batch (JSON file load). Optional salience override: system-evaluated (default), force HIGH, force LOW. |
| 2 | End-to-end event trace | Unified event table showing lifecycle: queued → processing → responded. Expandable rows with full routing detail. |
| 3 | Responses with feedback | See response text, give positive/negative feedback. Core validation workflow. |
| 4 | System connectivity & health | Service status, IP:Port, DB health, subscription stream status. Always visible in sidebar. |
| 5 | LLM/Ollama management | Endpoint/model display, health check, loaded models, test prompt, keep-warm button. |
| 6 | Event queue visibility | Pending events with salience, age, text preview. Merged into the unified event table (status=queued). |
| 7 | Heuristic management | View, add, edit, delete heuristics. Sortable, expandable, multi-select. |
| 8 | Flight recorder + implicit feedback | Heuristic fires, outcomes, OutcomeWatcher correlation, attribution window, confidence changes. |
| 9 | Logs | Service log viewer with search, tail control, auto-refresh. |
| 10 | Memory query | Similarity search probe — "does the system remember this?" |
| 11 | Metrics | Event counts, active heuristics, LLM calls, fast-path rate, cache hit rate. Always visible. |
| 12 | Cache inspection | Rust salience gateway cache contents, hit/miss stats, flush control. |
| 13 | Historical activity | Past events and responses from DB (not just current session). |
| 14 | Service management | Start/stop/restart services from the UI. |
| 15 | Environment switching | Docker/Local toggle. Both instances run simultaneously. |
| 16 | App instance settings | Read-only view of running config (ports, thresholds, DB connection). |
| 17 | UI settings | Display preferences persisted in localStorage. |

## Layout

### Three zones

```
┌──────────────────────────────────────────────────────────┐
│  [Metrics Strip - always visible]                        │
│  Events: 142  |  Heuristics: 8  |  LLM Calls: 34  |   │
│  Fast Path: 76%  |  Cache Hit: 89%                      │
├──────────┬───────────────────────────────────────────────┤
│ Sidebar  │  [Tab Bar]                                    │
│          │  Lab | Knowledge | Learning | LLM | Logs | ⚙ │
│ ENV      │                                               │
│ [Docker] │  ┌───────────────────────────────────────┐   │
│ [Local]  │  │                                       │   │
│          │  │          Tab Content Area              │   │
│ SERVICES │  │                                       │   │
│ ● orch   │  │                                       │   │
│   :50050 │  │                                       │   │
│ ● memory │  │                                       │   │
│   :50051 │  │                                       │   │
│ ● rust   │  │                                       │   │
│   :50052 │  │                                       │   │
│ ● exec   │  │                                       │   │
│   :50053 │  │                                       │   │
│ ● db     │  │                                       │   │
│   :5432  │  │                                       │   │
│ ● llm    │  │                                       │   │
│   qwen   │  │                                       │   │
│ ● stream │  │                                       │   │
│   connected│ │                                       │   │
│          │  │                                       │   │
│ CONTROLS │  │                                       │   │
│ [Start]  │  │                                       │   │
│ [Restart]│  │                                       │   │
│ [Stop]   │  └───────────────────────────────────────┘   │
└──────────┴───────────────────────────────────────────────┘
```

### Sidebar (always visible)

**Environment switcher**: Radio toggle between Docker and Local. Switching closes all connections and reconnects to the other instance's ports.

**Service health list**: Each service displayed as:
```
● service-name
  host:port
```
Status dot colors:
- Green: healthy
- Yellow: degraded
- Red: error/unreachable
- Gray: unknown/not checked

Services displayed:
- Orchestrator (gRPC health check)
- Memory Python (gRPC health check)
- Salience Rust (gRPC health check)
- Executive (gRPC health check)
- Database (connection test)
- LLM (Ollama `/api/tags` + model name from config)
- Subscription stream (SSE connection status)

**Service controls**: Start/Stop/Restart buttons. Scoped to a selected service or "all." Stop-all requires confirmation.

### Metrics strip (always visible, top)

Single row of small-font labeled numbers. Updated periodically (every 10-30s) or on-demand.

| Metric | Source |
|--------|--------|
| Total Events | `SELECT COUNT(*) FROM episodic_events` |
| Active Heuristics | `SELECT COUNT(*) FROM heuristics WHERE frozen = false` |
| LLM Calls | `SELECT COUNT(*) FROM episodic_events WHERE response_id IS NOT NULL` |
| Fast Path Rate | `(total - llm_calls) / total * 100` |
| Cache Hit Rate | `GetCacheStats` RPC → `hit_rate` |

### Tab: Lab

The primary workspace. Where events are submitted and their lifecycle is observed.

#### Event submission

**Sticky single-event bar** (always visible at top of Lab tab):
```
[source ▾]  [event text___________________________]  [salience ▾]  [Submit]
```

- Source: dropdown with presets (minecraft, kitchen, smart_home, work, health) + custom text option
- Event text: single-line input
- Salience: "System" (default, no override), "Force HIGH", "Force LOW"
- Submit: sends event, row appears in table below

**Batch submission** (collapsible section below sticky bar):
- File picker for JSON test fixtures
- Preview of loaded events before submission
- "Submit All" button

JSON fixture format:
```json
[
  {
    "source": "minecraft",
    "text": "Creeper approaching from behind",
    "salience_override": null
  },
  {
    "source": "kitchen",
    "text": "Oven timer expired 5 minutes ago",
    "salience_override": "high"
  }
]
```

Test fixtures stored in project (e.g., `tests/fixtures/events/`).

#### Unified event table

All events — queued, processing, and responded — in one chronological table. This replaces the V1 pattern of separate queue panel, latest response, and response history.

**Columns**:

| Column | Content | Notes |
|--------|---------|-------|
| Time | Relative + absolute: "3m ago (16:42:15)" | Monospace |
| Source | Event source (sensor name) | Filterable |
| Event | Text preview (first ~60 chars) | Filterable (text search) |
| Status | `queued` / `processing` / `responded` / `error` | Color-coded, filterable |
| Path | `HEURISTIC (name)` or `LLM` or `—` | Filterable |
| Response | Preview of response text (first ~80 chars) | Appears when status=responded |

**Lifecycle updates via SSE**:
- Event submitted → row appears with status `queued` (if queued) or `responded` (if immediate)
- Event dequeued for processing → status changes to `processing`
- Response arrives → status changes to `responded`, response preview fills in, path updates
- No polling, no manual refresh

**Expandable rows** (click to expand):

Level 1 expansion:
- Full response text
- Feedback buttons: [Good] [Bad] (calls ProvideFeedback RPC)
- Feedback result: "Heuristic created: {id}" or "Confidence updated"
- Routing detail: heuristic ID, confidence, salience scores
- Timing: submitted at, routed at, response at, total latency
- Persistence: event ID, response ID, "stored in episodic_events: yes/no"

Level 2 expansion (or detail pane):
- If heuristic path: condition text, fire record ID, outcome status
- If LLM path: whether suggestion was included, suggestion text, what prompt the LLM saw
- Raw salience breakdown: threat, opportunity, novelty, humor, goal_relevance, social, emotional, actionability, habituation

**Filtering**:
- Column-based filters (dropdowns or text input per column)
- Source, status, path: dropdown filter
- Event text: text search (substring match)
- Time: relative range (last 5m, 15m, 1h, 24h, all)
- Filters persist across tab switches (stored in URL params or localStorage)

**Pagination**: Scroll-based with "Load more" button. Load 25-50 events at a time. Configurable in UI settings.

### Tab: Knowledge

Three sections on one page.

#### Heuristics table

| Column | Content |
|--------|---------|
| Name | Human-readable rule name |
| Condition | Condition text (truncated, full in expansion) |
| Confidence | 0.0-1.0 with visual bar |
| Fired | fire_count |
| Succeeded | success_count |
| Origin | learned / user / pack / built_in |
| Frozen | yes/no |

- Sortable by any column (default: confidence DESC)
- Multi-row selection for bulk delete
- Expandable rows: full condition text, full action JSON, edit form
- Edit: modify condition text (regenerates embedding), action JSON, confidence (dev override)
- Add: collapsible form for creating heuristics manually

#### Memory similarity probe

```
[query text_______________________________]  [Probe]
```

Returns matching heuristics with similarity scores. Shows: heuristic name, score, condition text, action preview.

#### Cache inspector

Stats row: size / capacity, hit rate, total hits, total misses.

Table of cached heuristics: ID (truncated), name, hit count, last hit time.

[Flush Cache] button.

### Tab: Learning

#### Flight recorder

Table of heuristic fires with learning detail.

| Column | Content |
|--------|---------|
| Time | When fired |
| Heuristic | Name (linked to Knowledge tab entry) |
| Event | Event text preview |
| Outcome | success / failure / pending |
| Feedback | explicit / implicit / — |
| Confidence | Before → After (e.g., "0.65 → 0.72") |

Expandable rows:
- Full event text
- If implicit feedback: which OutcomeWatcher pattern matched, triggering event, attribution window duration
- If explicit feedback: who gave it, timestamp
- Heuristic detail: condition text, action, current confidence, total fires

Filter by outcome (all / pending / success / failure).

#### Historical events + responses

Reuses the same event table component as Lab tab, but data source is DB queries instead of SSE.

- Shows events from `episodic_events` table with joined response data
- Same columns, same expandable row format, same filtering
- Time range filter (last hour, 24h, 7d, all)
- "Load more" pagination

### Tab: LLM

Ollama management interface.

**Status section**:
- Active endpoint name (from `.env` `OLLAMA_ENDPOINT`)
- URL being used
- Model configured
- Connection status (reachable / unreachable / error)

**Loaded models** (from `GET /api/ps`):
- Model name, size, quantization, time since last use
- If configured model is NOT loaded: yellow warning

**Available models** (from `GET /api/tags`):
- List of all models on the Ollama instance

**Test prompt**:
```
[prompt text_________________________________]  [Send]
```
- Sends directly to Ollama (bypasses GLADyS pipeline)
- Shows: raw response text, token count, latency
- Useful for verifying LLM is responsive

**Keep warm**:
- [Keep Warm] button: sends trivial prompt with `keep_alive: "60m"`
- Shows current keep_alive status if model is loaded

### Tab: Logs

**Service selector**: Dropdown or horizontal tabs for each service (orchestrator, memory-python, memory-rust, executive).

**Log viewer**:
- Monospace scrollable output area
- Tail line count selector: 50 / 100 / 200 / 500
- [Fetch] button for manual load
- Auto-refresh toggle (SSE stream if available, otherwise periodic poll)
- Text search/filter within displayed logs (client-side filtering)

**Sources**:
| Environment | Source |
|-------------|--------|
| Local | `~/.gladys/logs/<service>.log` |
| Docker | `docker-compose logs --tail N <service>` |

### Tab: Settings (gear icon)

**App instance config (read-only)**:

| Setting | Source |
|---------|--------|
| Service ports | ENV_CONFIGS (hardcoded per environment) |
| DB connection | Environment variables |
| Confidence threshold | Orchestrator config |
| Similarity threshold | Memory config |
| LLM endpoint | `.env` file |
| Outcome watcher enabled | Orchestrator config |

**UI preferences** (persisted in localStorage):
- Events per page (25 / 50 / 100)
- Default time range
- Auto-refresh interval for metrics
- Theme (if implemented — low priority)

## UI Guidelines

These apply to all tabs and components.

1. **Information density over aesthetics**. No large fonts. No decorative whitespace. No hero sections. Every pixel is data or controls.

2. **Monospace for technical data**. IDs, timestamps, log output, event text, JSON — all monospace.

3. **Muted color palette with semantic highlights**. Dark background. Color only signals state:
   - Green: healthy, success, connected
   - Red: error, failure, unreachable
   - Yellow: warning, degraded, pending
   - Blue: links, interactive elements
   - Gray: disabled, unknown, secondary text

4. **Tables over cards**. Cards waste space. Tables are scannable. Expandable rows for detail when needed.

5. **Timestamps: relative + absolute**. Always show both: "3m ago (16:42:15)". Relative for scanning, absolute for log correlation.

6. **No pagination — scroll with "load more"**. Pagination breaks flow. Load N items, scroll, click "load more" for next batch.

7. **Keyboard shortcuts** for frequent actions:
   - `Ctrl+Enter`: Submit event
   - `Tab` / `Shift+Tab`: Navigate between tabs
   - `Esc`: Collapse expanded rows
   - `R`: Refresh current view

8. **Persistent filters**. Filters survive tab switches. Stored in URL query params or localStorage.

9. **Consistent action placement**. Destructive actions (delete, stop) require confirmation. Always in the same position relative to the data they act on.

10. **Reusable components**. The event table component is used in Lab (SSE data source) and Learning (DB query data source). Same columns, same expandable rows, different data feed.

## Extensibility

As the PoC grows, new features will be added (sensors, personality config, response model tuning, domain pack management).

**Adding a new tab**: Core tabs are always present. New features add tabs to the tab bar. Plugin/pack-specific UI can register tabs dynamically.

**Adding features to existing tabs**: Each tab is a section of the page with independent components. New sections can be added without restructuring existing ones.

**API pattern**: Every UI feature maps to a REST endpoint on the FastAPI backend. Adding a feature means: add endpoint, add HTML section/component. No framework-level changes.

## Backend API Surface

The FastAPI backend bridges HTTP/SSE to gRPC. These are the endpoints the frontend will call.

### Events

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| POST | `/api/events` | `OrchestratorService.PublishEvents` | Single event submission |
| POST | `/api/events/batch` | `OrchestratorService.PublishEvents` | Batch from JSON |
| GET | `/api/events` | DB query on `episodic_events` | Historical events with pagination |
| GET | `/api/events/stream` | SSE | Live event lifecycle updates |
| GET | `/api/queue` | `OrchestratorService.ListQueuedEvents` | Current queue contents |
| GET | `/api/queue/stats` | `OrchestratorService.GetQueueStats` | Queue statistics |

### Responses

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/responses/stream` | `OrchestratorService.SubscribeResponses` | SSE for response arrivals |
| POST | `/api/feedback` | `ExecutiveService.ProvideFeedback` | Submit feedback |

### Heuristics

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/heuristics` | DB query on `heuristics` | List with sorting/filtering |
| POST | `/api/heuristics` | `MemoryStorage.StoreHeuristic` | Create |
| PUT | `/api/heuristics/{id}` | Update + re-embed | Edit (condition, action, confidence) |
| DELETE | `/api/heuristics/{id}` | DB delete | Single delete |
| DELETE | `/api/heuristics` | DB delete | Bulk delete (IDs in body) |

### Memory

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| POST | `/api/memory/probe` | `MemoryStorage.QueryMatchingHeuristics` | Similarity search |

### Cache

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/cache/stats` | `SalienceGateway.GetCacheStats` | Hit rate, size |
| GET | `/api/cache/entries` | `SalienceGateway.ListCachedHeuristics` | Cached items |
| POST | `/api/cache/flush` | `SalienceGateway.FlushCache` | Clear cache |

### Flight Recorder

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/fires` | DB query on `heuristic_fires` | With outcome filter, pagination |

### Services

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/services/health` | gRPC `GetHealth` on all services | Aggregated health |
| POST | `/api/services/{name}/start` | `scripts/local.py start {name}` | Service control |
| POST | `/api/services/{name}/stop` | `scripts/local.py stop {name}` | Service control |
| POST | `/api/services/{name}/restart` | `scripts/local.py restart {name}` | Service control |

### Logs

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/logs/{service}` | File read or docker-compose logs | With tail param |

### LLM / Ollama

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/llm/status` | Ollama `/api/tags` + `/api/ps` + config | Combined status |
| POST | `/api/llm/test` | Ollama `/api/generate` | Direct test prompt |
| POST | `/api/llm/warm` | Ollama `/api/generate` with long keep_alive | Keep model loaded |

### Metrics

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/metrics` | DB queries + cache stats | Aggregated numbers for metrics strip |

### Config

| Method | Path | Maps to | Notes |
|--------|------|---------|-------|
| GET | `/api/config` | Read from env/config files | Active instance configuration |
| GET | `/api/config/environment` | Current env mode | Docker or Local |
| PUT | `/api/config/environment` | Switch environment | Changes all gRPC targets |

## File Structure

```
src/dashboard/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, CORS, static files
│   ├── routers/
│   │   ├── events.py        # Event submission, listing, SSE
│   │   ├── heuristics.py    # CRUD operations
│   │   ├── memory.py        # Similarity probe
│   │   ├── cache.py         # Cache stats and management
│   │   ├── fires.py         # Flight recorder
│   │   ├── services.py      # Health, start/stop/restart
│   │   ├── logs.py          # Log retrieval
│   │   ├── llm.py           # Ollama management
│   │   ├── metrics.py       # Aggregated metrics
│   │   └── config.py        # Environment and settings
│   └── grpc_bridge.py       # gRPC client management (channel lifecycle)
│
├── frontend/
│   ├── index.html           # Main page (layout shell, tab structure)
│   ├── css/
│   │   └── style.css        # Dark theme, dense layout, monospace
│   ├── js/
│   │   ├── app.js           # Alpine.js app state, tab management
│   │   ├── events.js        # SSE handling, event table logic
│   │   └── utils.js         # Timestamp formatting, filters
│   └── components/
│       ├── sidebar.html     # Sidebar partial (htmx)
│       ├── metrics.html     # Metrics strip partial
│       ├── lab.html         # Lab tab content
│       ├── knowledge.html   # Knowledge tab content
│       ├── learning.html    # Learning tab content
│       ├── llm.html         # LLM tab content
│       ├── logs.html        # Logs tab content
│       └── settings.html    # Settings tab content
│
└── pyproject.toml           # Backend dependencies
```

V1 Streamlit dashboard remains at `src/ui/dashboard.py` until V2 is ready.

## Existing Code to Reuse

The backend reuses existing Python gRPC client patterns from the V1 dashboard and admin scripts:

| Existing Code | Reuse In |
|---------------|----------|
| `dashboard.py` gRPC stub functions | `grpc_bridge.py` — channel lifecycle management |
| `dashboard.py` `send_event_to_orchestrator()` | `routers/events.py` — event submission |
| `dashboard.py` `fetch_data()` | `routers/events.py`, `routers/fires.py` — DB queries |
| `dashboard.py` `send_feedback()` | `routers/events.py` — feedback endpoint |
| `dashboard.py` `fetch_service_logs()` | `routers/logs.py` — log retrieval |
| `dashboard.py` `run_service_command()` | `routers/services.py` — service management |
| `dashboard.py` `get_llm_config()` | `routers/llm.py` — Ollama config |
| `scripts/_queue_client.py` | `routers/events.py` — queue listing |
| `scripts/_cache_client.py` | `routers/cache.py` — cache management |
| `scripts/_health_client.py` | `routers/services.py` — health checks |

## Port

Dashboard V2 backend: **8502** (avoids conflict with V1 on 8501 during transition).

Frontend served as static files by FastAPI.

## Dependencies

Backend (Python):
- `fastapi`
- `uvicorn`
- `sse-starlette` (SSE support)
- `grpcio` (existing)
- `psycopg2` (existing)
- `jinja2` (HTML template rendering for htmx partials)

Frontend (CDN, no npm):
- htmx (CDN link)
- Alpine.js (CDN link)
