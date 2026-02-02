# Implementation: Response Tab + Heuristics Tab

**Read `CLAUDE.md` first, then `claude_memory.md`, then this prompt.**

## Task

Implement the dashboard overhaul described in `docs/design/DASHBOARD_RESPONSE_DATA.md`. This covers issues #63 and #65.

**Branch**: Create `dashboard/response-heuristics-tabs` from `main`
**Logging standard**: `docs/design/LOGGING_STANDARD.md`

## Design Doc

**Read `docs/design/DASHBOARD_RESPONSE_DATA.md` completely before starting.** It contains the full specification: schema changes, executive changes, API changes, tab layouts, drill-down sections, cross-tab linking, and implementation scope.

## Architecture Rule

**The dashboard MUST NOT query PostgreSQL directly.** All data access goes through the Memory service gRPC API. This ensures query logic lives in one place — bug fixes apply everywhere. Do NOT add functions to `gladys_client/db.py` for this work. (Existing direct-DB access in the events router is tracked as tech debt in #66.)

## Implementation Order

Work in dependency order. Backend changes must land before frontend can consume the data.

### Phase 1: Schema + Proto (no code behavior changes yet)

**1. Migration `012_response_data.sql`** in `src/db/migrations/`:

```sql
-- Add decision chain columns to episodic_events
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS llm_prompt_text TEXT;
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS decision_path TEXT;
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS matched_heuristic_id UUID REFERENCES heuristics(id) ON DELETE SET NULL;

-- Episodes table (minimal — schema prep for future use)
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL;

-- Index for response tab queries
CREATE INDEX IF NOT EXISTS idx_episodic_decision_path ON episodic_events(decision_path);
CREATE INDEX IF NOT EXISTS idx_episodic_matched_heuristic ON episodic_events(matched_heuristic_id);
```

**2. Proto changes — `executive.proto`**

Add to `ProcessEventResponse`:
```protobuf
string prompt_text = N;           // Full LLM prompt (empty string for heuristic fast-path)
string decision_path = N;         // "heuristic" or "llm" (empty string if no decision)
string matched_heuristic_id = N;  // UUID string of involved heuristic (empty if none)
```

Find the next available field numbers.

**3. Proto changes — `memory.proto`**

Add new fields to the existing `EpisodicEvent` message:
```protobuf
string llm_prompt_text = 13;
string decision_path = 14;
string matched_heuristic_id = 15;
string episode_id = 16;
```

Add new RPCs to the `MemoryStorage` service:
```protobuf
// List events with decision chain data for Response tab
rpc ListResponses(ListResponsesRequest) returns (ListResponsesResponse);

// Get full detail for one event (drill-down)
rpc GetResponseDetail(GetResponseDetailRequest) returns (GetResponseDetailResponse);
```

Add new messages (see design doc for full message definitions):
- `ListResponsesRequest` — filters: decision_path, source, search, limit, offset
- `ResponseSummary` — parent row data including joined heuristic condition
- `ListResponsesResponse`
- `GetResponseDetailRequest`
- `ResponseDetail` — full drill-down data including joined heuristic + fire outcome
- `GetResponseDetailResponse`

Regenerate proto stubs: `make proto` (or equivalent — check `Makefile`).

### Phase 2: Executive + Orchestrator changes

**4. Executive: populate new response fields**

In `src/services/executive/gladys_executive/server.py`:

- **Heuristic fast-path** (~line 474-498): Set `decision_path = "heuristic"`, `matched_heuristic_id = <heuristic UUID>`, `prompt_text = ""` on the response.

- **LLM path** (~line 505-568): Set `decision_path = "llm"`, `matched_heuristic_id = <heuristic UUID if low-confidence match was included>`, `prompt_text = <the constructed prompt variable>`. The prompt variable already exists locally — just include it in the response instead of discarding it.

- Persist prompt even on LLM timeout — the prompt was sent.

**5. Orchestrator: persist new fields when storing event**

In `src/services/orchestrator/gladys_orchestrator/server.py` and `clients/memory_client.py`:

When the Orchestrator receives `ProcessEventResponse` and calls `memory_client.store_event()`, pass through the new fields. The `EpisodicEvent` proto message now has the new fields — populate them before sending to Memory service.

**6. Memory service: update storage + implement new RPCs**

In `src/services/memory/gladys_memory/storage.py`:

- Update `store_event()` INSERT to include `llm_prompt_text`, `decision_path`, `matched_heuristic_id` columns.

In `src/services/memory/gladys_memory/grpc_server.py`:

- Implement `ListResponses` RPC: query `episodic_events` LEFT JOIN `heuristics` ON `matched_heuristic_id` LEFT JOIN `heuristic_fires` ON `episodic_event_id`. Filter by decision_path, source, text search. ORDER BY timestamp DESC.
- Implement `GetResponseDetail` RPC: same joins, single event by ID. Include `llm_prompt_text`, fire outcome data.

**7. Fix `episodic_event_id` in `on_fire()`**

In `src/services/orchestrator/gladys_orchestrator/learning.py` (~line 125-130):

The `on_fire()` call to `record_heuristic_fire` doesn't pass `episodic_event_id`. Pass it. The value should be available from the event context.

**8. Remove derived path logic**

In `src/services/dashboard/backend/routers/events.py`, the `_make_event_dict()` function derives `path` from `matched_heuristic_id` / `response_id` (~line 68-73). Replace this with reading from the `decision_path` column. The derivation logic was a temporary fix from #52.

### Phase 3: Dashboard API routes

**9. New API routes** in `src/services/dashboard/backend/routers/`:

Create `responses.py`:
```
GET /api/responses?decision_path=...&source=...&search=...&limit=50&offset=0
GET /api/responses/{event_id}
```

These routes call Memory service gRPC (`ListResponses` / `GetResponseDetail`), NOT `gladys_client.db`. Follow the same gRPC client pattern used by the heuristics router.

Register the router in the dashboard app.

### Phase 4: Frontend

**10. Response tab** — `src/services/dashboard/frontend/components/response.html`

New file. Follow the design doc's Response Tab section exactly:
- Parent row: chevron, timestamp, source, event (truncated), path badge, heuristic (truncated condition, clickable), response (truncated)
- Filters: path, source, text search
- Drill-down: flat sequential sections (event → heuristic → LLM prompt → response → outcome)
- LLM prompt collapsed by default
- Alpine.js data component with `fetchResponses()`, filter state

**11. Heuristics tab** — `src/services/dashboard/frontend/components/heuristics.html`

Replace `knowledge.html`. Follow the design doc's Heuristics Tab section:
- Parent row: checkbox, chevron, origin badge, truncated ID, condition (click-to-edit), confidence (bar + inline slider), fires (clickable → Response tab), active toggle
- Multi-select with select-all-visible and bulk action bar
- Drill-down: metadata section (read-only), editable fields section, delete + save
- Dirty-state save (button appears/enables only when changed)
- Reuse existing `saveHeuristic()`, `deleteHeuristic()` functions — adapt as needed

**12. Update `index.html`**

- Replace the Knowledge tab button/panel with Heuristics tab
- Add Response tab button/panel
- Tab order suggestion: Lab | Response | Heuristics | (rest)

**13. Cross-tab linking**

- Heuristic condition/ID in Response tab → click switches to Heuristics tab, highlights heuristic
- Fire count in Heuristics tab → click switches to Response tab filtered to that heuristic's ID
- Implementation: Alpine.js custom events or shared state. The design doc leaves mechanism to the implementer.

**14. Inline click-to-edit**

Alpine.js pattern: `x-data="{ editing: false }"` toggles between truncated `<span>` and full `<textarea>`. Used in Heuristics tab for condition field, and confidence slider reveal. Make this reusable.

### Phase 5: Cleanup

**15. Remove `knowledge.html`** (replaced by `heuristics.html`)

**16. Update any references** to the Knowledge tab in `app.js`, `index.html`, or other files.

## What NOT to change

- Lab tab — unchanged
- LLM tab, Settings tab, Learning tab — unchanged
- Sensor code — unchanged
- No changes outside the dashboard, executive, orchestrator, memory, and gladys_client services
- Do NOT add query functions to `gladys_client/db.py` — response queries go through Memory gRPC

## Scope Note

This is a large change spanning proto, executive, orchestrator, memory, dashboard backend, and dashboard frontend. If you need to split into multiple commits, do so logically (e.g., backend in one commit, frontend in another). But all changes should be on the same branch.

## Testing

After changes:
1. `make proto` succeeds (proto stubs regenerated)
2. Services start without errors (`make start`)
3. Dashboard starts (`make dashboard`)
4. Submit an event via Lab tab — verify `decision_path` and `matched_heuristic_id` are populated in DB
5. Response tab shows the event with correct path badge
6. Expand event in Response tab — drill-down shows all sections
7. Give positive feedback — heuristic created, appears in Heuristics tab
8. Submit similar event — heuristic fires, Response tab shows HEURISTIC path
9. Heuristics tab: inline edit condition, save — persists
10. Heuristics tab: click fire count → switches to Response tab filtered
11. Response tab: click heuristic → switches to Heuristics tab
12. Heuristics tab: multi-select + bulk delete works

## Branch setup

```bash
git checkout main
git pull
git checkout -b dashboard/response-heuristics-tabs
```
