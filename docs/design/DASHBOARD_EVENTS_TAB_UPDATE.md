# Dashboard Events Tab Update (PoC 2 Fields)

**Status**: Draft for review
**Date**: 2026-02-11
**Issue**: #161
**Related**: [DASHBOARD_COMPONENT_ARCHITECTURE.md](DASHBOARD_COMPONENT_ARCHITECTURE.md)

## Problem

Events tab currently shows limited field set. PoC 2 adds new fields that need to be visible in the dashboard:
- `intent` (actionable/informational/unknown)
- `evaluation_data` (JSON) — sensor evaluation metadata
- `structured` (JSON) — parsed event structure
- `entity_ids` (UUID[]) — linked entities
- `timestamp` — event origin time (distinct from processing time)

These fields now round-trip correctly through the pipeline (#160), but the dashboard doesn't display them.

## Design Decisions

### 1. Timestamp Display

**Decision**: Keep relative time in table, show absolute timestamp in drilldown + tooltip

**Rationale**:
- Relative time ("5m ago") is better for quick scanning and understanding event recency
- Absolute timestamp is important for correlation/debugging but doesn't need table real estate
- Tooltip on "Time" column shows absolute time for hover reference
- Drilldown shows both for detailed inspection

**Impact**: No new table column needed (keeps 7 columns)

### 2. Intent Column Promotion

**Decision**: Move `intent` from drilldown stats to table column

**Rationale**:
- Intent is a key classification dimension (actionable vs informational vs unknown)
- Users need to filter/scan by intent without expanding every row
- 3 possible values = compact display (icon + color coding)
- Critical for workflow: "show me all actionable events"

**Impact**: Table grows from 7 to 8 columns
- New column between "Source" and "Event"
- Uses icon + color: ⚡ actionable (blue), ℹ️ informational (gray), ❓ unknown (yellow)
- Width: 50px (icon + tooltip)

### 3. Complex Field Display (evaluation_data, structured, entity_ids)

**Decision**: Add to drilldown using collapsible JSON viewers

**Rationale**:
- All three are complex/nested data structures
- Not scannable in table format
- Used for deep inspection, not filtering
- Drilldown is the right UX location

**Display patterns**:
- `evaluation_data`: Collapsible JSON block with syntax highlighting (if present)
- `structured`: Collapsible JSON block with syntax highlighting (if present)
- `entity_ids`: List of UUID links (clickable to entity detail, future feature)

## New Table Layout

**Grid**: 8 columns (was 7)

| Column | Width | Content | Filterable |
|--------|-------|---------|------------|
| Checkbox | 30px | Selection | - |
| Time | 90px | Relative time (tooltip: absolute) | ✅ (range) |
| Source | 70px | Event source | ✅ (contains) |
| **Intent** | **50px** | **Icon + color** | **✅ (equals)** |
| Event | 1fr | Event text (truncated) | ✅ (contains) |
| Status | 80px | queued/processing/responded | ✅ (equals) |
| Path | 70px | heuristic/llm/fallback | ✅ (equals) |
| Response | 160px | Response text (truncated) | ✅ (contains) |

## Drilldown Updates

**Current structure**:
1. Event text (full)
2. IDs (Event ID, Response ID)
3. Stats row: Source, Intent, Path, Salience, Confidence
4. Salience breakdown (grid)
5. Response text (boxed)
6. Feedback actions

**New structure**:
1. Event text (full)
2. IDs (Event ID, Response ID)
3. **Timestamps row**: Received (processing time), Origin (event timestamp)
4. Stats row: Source, ~~Intent~~, Path, Salience, Confidence (Intent moved to table)
5. **Structured data** (if present): Collapsible JSON viewer
6. **Evaluation data** (if present): Collapsible JSON viewer
7. **Entity links** (if present): List of linked entity IDs with icons
8. Salience breakdown (grid)
9. Response text (boxed)
10. Feedback actions

## Implementation Strategy

### Files to Modify

| File | Change |
|------|--------|
| `frontend/components/lab.html` | Add Intent column header + filter, update grid-cols |
| `frontend/components/event_row.html` | Add Intent cell, add drilldown fields |
| `frontend/components/widgets/json_viewer.html` | **CREATE** - collapsible JSON display widget |
| `backend/routers/events.py` | Ensure `intent`, `evaluation_data`, `structured`, `entity_ids`, `timestamp` passed to templates |

### Widget: JSON Viewer

**New reusable widget** for displaying JSON data in drilldown:

```jinja2
{# json_viewer(title, data, default_collapsed=True) #}
{% macro json_viewer(title, data, default_collapsed=True) %}
{% if data %}
<div x-data="{ expanded: {{ 'false' if default_collapsed else 'true' }} }" class="border-t border-gray-700 pt-2">
    <div @click="expanded = !expanded" class="cursor-pointer flex items-center gap-2 text-gray-400 font-bold uppercase text-xs mb-1 hover:text-gray-300">
        <span x-text="expanded ? '▼' : '▶'" class="text-[10px]"></span>
        <span>{{ title }}</span>
    </div>
    <div x-show="expanded" x-collapse class="bg-gray-900 p-2 rounded overflow-auto max-h-64">
        <pre class="text-xs text-gray-300 select-text">{{ data | tojson(indent=2) }}</pre>
    </div>
</div>
{% endif %}
{% endmacro %}
```

**Usage**: `{{ json_viewer('Evaluation Data', event.evaluation_data) }}`

### Backend Changes

**Ensure these fields are passed to templates** (likely already done by #160):

```python
# backend/routers/events.py
event_dict = {
    "id": event.id,
    "text": event.text,
    "source": event.source,
    "intent": event.intent,  # ✅ Ensure this is passed
    "timestamp": event.timestamp,  # ✅ Add if missing
    "evaluation_data": event.evaluation_data,  # ✅ Add if missing
    "structured": event.structured,  # ✅ Add if missing
    "entity_ids": event.entity_ids,  # ✅ Add if missing
    # ... existing fields ...
}
```

## Pattern Compliance

✅ **Pattern A (Server-Side Rendering)**: All data rendered via Jinja templates
✅ **Alpine.js for interactivity only**: Expansion state, not data loops
✅ **Follows existing widget patterns**: Uses drilldown macros, creates reusable JSON viewer

## Testing

### Manual Verification

1. **Table display**:
   - Intent column shows correct icon/color for each intent value
   - Filtering by intent works (dropdown: All/Actionable/Informational/Unknown)
   - Time column tooltip shows absolute timestamp

2. **Drilldown display**:
   - Timestamps row shows both received and origin times
   - evaluation_data expands/collapses correctly (if present)
   - structured expands/collapses correctly (if present)
   - entity_ids displays as list with UUIDs (if present)
   - Fields that are null/absent don't show empty sections

3. **Responsive behavior**:
   - 8-column grid doesn't overflow on typical screen widths
   - Horizontal scroll works if needed

### Test Data Requirements

Create test events with:
- All intent values (actionable, informational, unknown)
- Present vs absent evaluation_data/structured/entity_ids
- Various timestamp values

## Open Questions

1. **Entity ID links**: Should entity IDs be clickable now, or wait for entity detail view?
   - **Recommendation**: Make them styled as links but not clickable yet (future feature gate)

2. **JSON syntax highlighting**: Use syntax highlighting library, or plain text?
   - **Recommendation**: Start with plain text (Jinja `tojson` filter), add highlighting later if needed

3. **Intent filter placement**: Add to filter row, or separate toolbar?
   - **Recommendation**: Add to filter row (consistent with Source, Status, Path filters)

## Dependencies

- **Blocked by**: #160 (event field storage) — must be merged first ✅ DONE
- **Coordinates with**: #110-#113 (dashboard extensibility) — use same widget patterns

## Rollout Plan

1. **Phase 1**: Backend verification (ensure all fields passed to templates)
2. **Phase 2**: Create JSON viewer widget
3. **Phase 3**: Update event_row.html drilldown (add new fields)
4. **Phase 4**: Update lab.html table (add Intent column)
5. **Phase 5**: Manual testing with diverse test data

## Success Criteria

- [ ] Intent visible in table column with correct icons/colors
- [ ] Intent filterable via dropdown
- [ ] Time column tooltip shows absolute timestamp
- [ ] Drilldown shows timestamps row (received + origin)
- [ ] evaluation_data displays in collapsible JSON viewer (when present)
- [ ] structured displays in collapsible JSON viewer (when present)
- [ ] entity_ids displays as list (when present)
- [ ] Absent fields don't create empty UI sections
- [ ] No layout breaks on typical screen widths
- [ ] Pattern A compliance (server-side rendering, Alpine for interactivity only)
