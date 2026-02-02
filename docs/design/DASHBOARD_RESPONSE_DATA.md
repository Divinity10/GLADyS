# Design: Response Tab + Heuristics Tab

**Issue**: #63
**Status**: Approved design
**Author**: Scott / Claude
**Date**: 2026-02-01

---

## Problem

PoC 1 assessment requires three analysis capabilities:

1. **Spot-checking**: "I see heuristic X has low confidence — why?"
2. **Pattern analysis**: "Are learned heuristics generally working?"
3. **Debugging**: "This event got a bad response — was it a heuristic or LLM? What was the prompt?"

The current Knowledge tab is a basic editor with no history, no prompt visibility, and no event linking. The original #63 scope (drill-down within Knowledge tab) tried to serve both heuristic management and decision-chain inspection in one view. These are better as separate concerns.

## Solution

Replace the current Knowledge tab with two new tabs:

1. **Heuristics tab** — Heuristic management: edit, delete, bulk operations, summary stats
2. **Response tab** — Read-only chronological analysis: event → decision chain → response → outcome

Cross-tab linking connects them bidirectionally. The Lab tab remains unchanged (interactive event submission).

---

## Schema Changes

### New columns on `episodic_events`

```sql
ALTER TABLE episodic_events ADD COLUMN llm_prompt_text TEXT;
ALTER TABLE episodic_events ADD COLUMN decision_path TEXT;
ALTER TABLE episodic_events ADD COLUMN matched_heuristic_id UUID REFERENCES heuristics(id) ON DELETE SET NULL;
```

- `llm_prompt_text`: Full prompt sent to LLM. NULL for heuristic fast-path and events that never reached Executive. Persisted even on LLM timeout (the prompt was sent).
- `decision_path`: `'heuristic'`, `'llm'`, `'heuristic_fallback'` (reserved — see note below), or NULL (no decision made). Timeout is inferred: `decision_path = 'llm' AND response_text IS NULL`.
- `matched_heuristic_id`: FK to heuristic that was **involved** in processing this event — either fired directly (heuristic fast-path) OR included as context in the LLM prompt (low-confidence match). NULL if no heuristic matched.

#### `matched_heuristic_id` vs `heuristic_fires` — distinct concepts

These track different things and both are needed:

| | `matched_heuristic_id` (on `episodic_events`) | `heuristic_fires` (separate table) |
|---|---|---|
| **Means** | Heuristic was **involved in processing** (matched or included as context) | Heuristic **fired as the response** (was used directly) |
| **Populated when** | Any heuristic match, including low-confidence ones passed to LLM | Only when heuristic is used as the actual response |
| **Example** | Confidence 0.3 heuristic included in LLM prompt → `matched_heuristic_id` set, no fire record | Confidence 0.8 heuristic used directly → `matched_heuristic_id` set AND fire record created |

The Response tab uses `matched_heuristic_id` to show "this heuristic was part of the decision." The Outcome drill-down section uses `heuristic_fires` to show feedback/outcome when the heuristic actually fired.

#### `heuristic_fallback` — reserved, not yet implemented

The `heuristic_fallback` value is forward-compatible schema prep for when the system falls back to a low-confidence heuristic on LLM timeout. This behavior does not exist yet. The value will not be populated until fallback behavior is implemented (potentially PoC 2). The Response tab filter includes it for completeness — it will simply return no results until the behavior exists.

### New `episodes` table

```sql
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE episodic_events ADD COLUMN episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL;
```

Minimal for now. Groups related events into episodes. Not used by the dashboard tabs in this design — schema-only prep for future use. Episodes are single-source (`source NOT NULL`). Multi-source grouping (e.g., "Tuesday evening session" spanning sudoku + melvor) is a higher-level concept (sessions/meta-episodes) deferred to PoC 3+.

### Data note

All existing data is test/simulated and will be cleared. No migration of existing values needed.

---

## Executive Changes

### Persist prompt text, decision path, matched heuristic

Add three new fields to `ProcessEventResponse` in `executive.proto`:

```protobuf
message ProcessEventResponse {
    // ... existing fields ...
    string prompt_text = N;           // Full LLM prompt (empty for heuristic fast-path)
    string decision_path = N;         // "heuristic" or "llm"
    string matched_heuristic_id = N;  // UUID of involved heuristic (empty if none)
}
```

The Executive already knows all three values at response time. The Orchestrator receives them in the response and persists them when storing the event to `episodic_events`. This keeps the existing data flow (Executive → Orchestrator → DB) unchanged.

In `ProcessEvent` ([server.py:510-528](src/services/executive/gladys_executive/server.py#L510-L528)), the prompt is currently constructed as a local variable and discarded after the LLM call. Change: include it in the response.

The system prompt (`EXECUTIVE_SYSTEM_PROMPT`) is static and NOT stored — only the user prompt varies per event.

### Remove `_make_event_dict` derivation logic

The `decision_path` column replaces the derived path logic currently in `events.py` (from #52). Once the stored column exists, the derivation logic must be removed to avoid divergence between the stored value and the derived value.

### Fix `episodic_event_id` in `on_fire()`

Currently NULL. One-line fix to pass the event's episodic ID when recording a heuristic fire. Required for the Response tab's Outcome section to link fires to events.

---

## Response Tab

### Purpose

Read-only chronological view of the decision chain for every event. Answers: "What happened when this event was processed?"

### Parent Row

| Column | Width | Source | Notes |
|--------|-------|--------|-------|
| ▸ | narrow | — | Chevron expand |
| Timestamp | ~120px | `episodic_events.timestamp` | Relative time, full on hover |
| Source | ~80px | `episodic_events.source` | Badge |
| Event | flex | `episodic_events.raw_text` | Truncated 4-6 words |
| Path | ~90px | `decision_path` | Badge: HEURISTIC / LLM / FALLBACK / — |
| Heuristic | ~150px | `matched_heuristic_id` → `heuristics.condition_text` | Truncated condition, clickable → Heuristics tab. Blank if none |
| Response | flex | `response_text` | Truncated 4-6 words. Blank if timeout/no response |

Parent rows use a distinct shade from drill-down rows for clear visual boundaries.

### Filters

| Filter | Options |
|--------|---------|
| Path | All / Heuristic / LLM / Heuristic Fallback / No Response / Timed Out |
| Source | All / sudoku / melvor / ... (dynamic from data) |
| Text search | Searches across event text and response text |

"Timed Out" filter maps to: `WHERE decision_path = 'llm' AND response_text IS NULL`.
"No Response" filter maps to: `WHERE decision_path IS NULL`.

### Drill-Down

Flat sequential sections (not two-column). Matches the chronological decision chain flow: event happened → heuristic matched → prompt sent → response returned → feedback given.

**1. Event**
- Full `raw_text`

**2. Heuristic** (omit section if `matched_heuristic_id` is NULL)
- Full condition text
- Current confidence (not at-time-of-fire — historical analysis deferred)
- Clickable heuristic ID → Heuristics tab

**3. LLM Prompt** (omit section if `llm_prompt_text` is NULL)
- Collapsed by default (prompts can be long)
- Section header indicates if heuristic context is included: "LLM Prompt (includes heuristic context)" vs "LLM Prompt"
- Monospace block when expanded

**4. Response**
- Full `response_text`, or "(no response)" if NULL

**5. Outcome** (omit section if no `heuristic_fires` record exists for this event)
- Feedback type (explicit / implicit / —)
- Outcome (success / fail / unknown)

### Pagination

The API supports `limit` and `offset` parameters. Frontend pagination (or infinite scroll) is deferred for PoC — the volume from assessment sessions is manageable. The API is ready when it's needed.

---

## Heuristics Tab

### Purpose

Heuristic management: inspect, edit, delete, bulk operations. Replaces the current Knowledge tab.

### Parent Row

| Column | Width | Notes |
|--------|-------|-------|
| ☐ | narrow | Checkbox for multi-select |
| ▸ | narrow | Chevron expand |
| Origin | ~80px | Badge: learned / user / built_in |
| ID | ~80px | Truncated UUID |
| Condition | flex | Truncated 4-6 words, click-to-edit (expands to textarea showing full text) |
| Confidence | ~100px | Bar + percentage. Click to show inline slider |
| Fires | ~60px | Count. Clickable → Response tab filtered to this heuristic |
| Active | ~50px | Toggle (inline editable) |

Parent rows use a distinct shade from drill-down rows.

### Inline Editing

- **Click-to-edit on condition**: Truncated `<span>` swaps to full `<textarea>` on click. Alpine.js toggle: `x-data="{ editing: false }"`.
- **Confidence slider**: Click the confidence bar/percentage to reveal inline range slider.
- **Active toggle**: Direct inline toggle, no expansion needed.
- **Dirty-state save**: Save button appears (or enables) only when a field has been modified. Vertical button stack in the row.

### Filters

| Filter | Options |
|--------|---------|
| Origin | All / Learned / User / Built-in |
| Active | All / Active Only / Inactive Only |
| Text search | Searches name and condition text |

### Multi-Select + Bulk Delete

- Checkboxes per row
- "Select all visible" checkbox in table header
- Bulk action bar appears when any row is selected (positioned above or below table)
- Bulk delete with confirmation
- Uses existing `DELETE /api/heuristics` endpoint which accepts `{ ids: [...] }` body ([heuristics.py:130](src/services/fun_api/routers/heuristics.py#L130))

### Drill-Down

**Section 1 — Metadata (read-only)**
- Full UUID
- Origin + Origin ID
- Created / Updated timestamps
- Fires / Successes / Success Rate

**Section 2 — Editable Fields**
- Name (text input)
- Condition (textarea, full text)
- Action type (dropdown: suggest / remind / warn)
- Action message (textarea)
- "Raw JSON" toggle that swaps to raw JSON textarea for edge cases
- Delete button + dirty-state Save button

**No fire history sub-table.** Fire count in the parent row is clickable and links to the Response tab filtered to `matched_heuristic_id = this_heuristic`. Individual fire inspection happens in the Response tab.

---

## Cross-Tab Linking

| From | To | Mechanism |
|------|----|-----------|
| Response tab → Heuristics tab | Heuristic column (parent row) or Heuristic section (drill-down) | Click heuristic ID/condition → switch to Heuristics tab, scroll to / highlight heuristic |
| Heuristics tab → Response tab | Fire count (parent row) | Click fire count → switch to Response tab, filtered to `matched_heuristic_id` |
| Response tab → Lab tab | Event timestamp or ID | Click → switch to Lab tab, scroll to event (if it exists) |

Implementation: Alpine.js custom events or URL hash parameters to communicate between tabs. Exact mechanism left to implementation session.

---

## API Changes

### New endpoints

```
GET /api/responses?decision_path=...&source=...&search=...&limit=50&offset=0
```
Returns `episodic_events` joined with `heuristics` (for condition text) and `heuristic_fires` (for outcome). Filtered by `decision_path`, `source`, text search.

```
GET /api/responses/{event_id}
```
Returns full detail for one event: all fields including `llm_prompt_text`, joined heuristic data, fire outcome.

### Modified endpoints

```
GET /api/heuristics
```
Already exists. Needs to return `fire_count`, `success_count`, timestamps (should already per #54 work).

```
PUT /api/heuristics/{id}
```
Already exists. Needs to support updating `name` field.

### Existing endpoints (no change needed)

```
DELETE /api/heuristics/{id}         — single delete
DELETE /api/heuristics (body: {ids}) — bulk delete (already exists at heuristics.py:130)
```

---

## Implementation Scope

### Backend (service changes)
1. Migration: add `llm_prompt_text`, `decision_path`, `matched_heuristic_id` to `episodic_events`
2. Migration: create `episodes` table, add `episode_id` to `episodic_events`
3. Proto: add `prompt_text`, `decision_path`, `matched_heuristic_id` to `ProcessEventResponse`
4. Executive: populate new response fields in both heuristic fast-path and LLM path
5. Orchestrator: persist new fields when storing event
6. Remove `_make_event_dict` decision path derivation logic (replaced by stored column)
7. Fix `episodic_event_id` in `on_fire()` (one-line)
8. New DB functions in `gladys_client/db.py` for response queries
9. New API routes for response listing/detail

### Frontend (dashboard changes)
10. New Response tab component (`response.html`)
11. Replace Knowledge tab with Heuristics tab component (`heuristics.html`)
12. Cross-tab linking mechanism
13. Inline click-to-edit pattern (reusable across both tabs)
14. Multi-select + bulk action bar pattern
