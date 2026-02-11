# Dashboard Event Creation Form

**Status**: Draft
**Owner**: Scott + Architect
**Related**: #161 (Dashboard Events tab)

## Problem

The current event submission bar in the Lab tab is a single-row form with only 4 fields (source, text, intent, salience_override). Phase 2 adds additional event fields (structured, evaluation_data, entity_ids, timestamp) that cannot fit in a single row. Developers need a way to manually create events with all supported fields for testing and debugging.

## Solution

Replace the single-row submission bar with a **collapsible form** that supports all Event proto fields. The form has two modes:

- **Simple Mode** (default, collapsed): Source + Text + Intent + Submit (quick path for common cases)
- **Advanced Mode** (expanded): All Phase 2 fields visible in organized sections

### Form Structure

#### Simple Mode (Always Visible)

```
┌─ Event Submission ──────────────────────────────────────┐
│ [Source ▼] [Event text...........................] │
│ [Intent ▼] [Submit]  ⚙️ Show Advanced Fields           │
└─────────────────────────────────────────────────────────┘
```

- **Source**: Dropdown (sudoku, melvor, minecraft, kitchen, smart_home, work, health, custom)
- **Event Text**: Textarea (multi-line, flex-1)
- **Intent**: Dropdown (actionable, informational, unknown)
- **Submit**: Button
- **Toggle**: "⚙️ Show Advanced Fields" button expands to advanced mode

#### Advanced Mode (Expanded)

All additional sections visible below simple mode fields:

**1. Origin Timestamp**
- Datetime-local input
- Defaults to current time
- Converts to `google.protobuf.Timestamp` on submit

**2. Salience Override** (collapsible subsection)
- Collapsed by default
- When expanded, shows 9 range inputs (0.0-1.0):
  - Threat
  - Opportunity
  - Humor
  - Novelty
  - Goal Relevance
  - Social
  - Emotional (-1.0 to 1.0)
  - Actionability
  - Habituation
- If all fields empty/default, backend uses auto-calculation

**3. Structured Data** (collapsible subsection)
- Collapsed by default
- Dynamic key-value pair builder
- "➕ Add Field" button adds a row
- Each row: `[key input] [value input] [❌ remove]`
- Backend constructs `google.protobuf.Struct` from pairs

**4. Evaluation Data** (collapsible subsection)
- Collapsed by default
- Same key-value builder as Structured Data
- Backend constructs `google.protobuf.Struct` from pairs

**5. Entity IDs** (collapsible subsection)
- Collapsed by default
- Text input for comma-separated UUIDs
- Placeholder: "uuid1, uuid2, uuid3"
- Backend splits on comma, trims whitespace, validates UUIDs

### Backend Changes

**POST /api/events endpoint** (`backend/routers/events.py`):

Current fields accepted:
- `source` (string)
- `text` (string, maps to `raw_text`)
- `intent` (string)
- `salience_override` (string: "high"/"low"/"")

New fields to accept:
- `timestamp` (ISO 8601 string) → `google.protobuf.Timestamp`
- `salience_*` (individual floats: `salience_threat`, `salience_novelty`, etc.) → `gladys.types.SalienceVector`
- `structured_keys[]` + `structured_values[]` (arrays) → `google.protobuf.Struct`
- `evaluation_keys[]` + `evaluation_values[]` (arrays) → `google.protobuf.Struct`
- `entity_ids` (comma-separated string) → `repeated string`

**Conversion logic:**

```python
# Timestamp
if timestamp_str:
    dt = datetime.fromisoformat(timestamp_str)
    event.timestamp.FromDatetime(dt)

# Salience (prioritize individual fields over override)
if any(form.get(f"salience_{dim}") for dim in SALIENCE_DIMS):
    salience = types_pb2.SalienceVector(
        threat=float(form.get("salience_threat", 0.0)),
        opportunity=float(form.get("salience_opportunity", 0.0)),
        # ... all 9 dimensions
    )
    event.salience.CopyFrom(salience)
elif salience_override:
    # Existing high/low logic

# Structured (key-value pairs → Struct)
if "structured_keys[]" in form:
    keys = form.getlist("structured_keys[]")
    values = form.getlist("structured_values[]")
    struct_dict = {k: v for k, v in zip(keys, values) if k}
    event.structured.update(struct_dict)

# Evaluation Data (key-value pairs → Struct)
if "evaluation_keys[]" in form:
    keys = form.getlist("evaluation_keys[]")
    values = form.getlist("evaluation_values[]")
    eval_dict = {k: v for k, v in zip(keys, values) if k}
    event.evaluation_data.update(eval_dict)

# Entity IDs (comma-separated → list)
if entity_ids_str := form.get("entity_ids"):
    ids = [eid.strip() for eid in entity_ids_str.split(",") if eid.strip()]
    event.entity_ids.extend(ids)
```

### UI Implementation Notes

- Use Alpine.js for toggle state (`x-data`, `x-show`)
- Each collapsible subsection uses the same expand/collapse pattern
- Key-value builder uses Alpine.js array for dynamic add/remove
- All data rendered server-side on success (Pattern A)
- Form clears on successful submit (keep simple mode collapsed)

## Non-Goals

- Advanced validation (e.g., JSON schema for structured data) — accept any key-value pairs
- Preset templates for structured/evaluation data — freeform entry only
- Tokenization fields (tokens/tokenizer_id) — not needed for manual entry
- Metadata override — system-populated only

## Files to Modify

| File | Change |
|------|--------|
| `src/services/dashboard/frontend/components/lab.html` | Replace single-row submission bar with collapsible form |
| `src/services/dashboard/backend/routers/events.py` | Expand `submit_event()` to accept and process all new fields |

## Testing

Manual verification (no automated tests for UI):

1. **Simple mode submission**:
   - Source + Text + Intent → event created with defaults
   - Form clears after submit

2. **Advanced mode - Timestamp**:
   - Set origin time → event shows correct timestamp in drilldown

3. **Advanced mode - Salience**:
   - Set individual dimensions → event shows correct salience breakdown
   - Leave empty → auto-calculation works

4. **Advanced mode - Structured Data**:
   - Add 3 key-value pairs → JSON viewer shows correct object
   - Remove middle pair → updates correctly
   - Submit with empty keys → ignored

5. **Advanced mode - Evaluation Data**:
   - Same tests as Structured Data

6. **Advanced mode - Entity IDs**:
   - Enter "uuid1, uuid2, uuid3" → drilldown shows 3 entity chips
   - Enter malformed UUIDs → error or graceful handling

7. **All fields together**:
   - Fill every field → event created with all data
   - Verify in drilldown display

## Follow-Up Work

- Add preset templates for common structured data patterns (future)
- Add JSON syntax validation for key-value builders (future)
- Add UUID validation for entity_ids input (future)

## Decision Log

- **Why collapsible instead of modal?** Keeps quick submit path visible, no extra clicks for common cases
- **Why key-value builders instead of raw JSON?** User requested: "Don't make the dev enter json: provide fields and then you create the json"
- **Why datetime-local for timestamp?** Native browser control, good UX for timestamp selection
- **Why range inputs for salience?** Clearer constraints (0-1 range) than freeform numbers
