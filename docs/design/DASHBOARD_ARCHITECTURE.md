# Dashboard Architecture Vision

**Status**: Planning (deferred to future phase)
**Date**: 2026-02-12
**Authors**: Scott Mulcahy, Claude (Architect)
**Related**: DASHBOARD_COMPONENT_ARCHITECTURE.md (current patterns)

---

## Problem Statement

The dashboard is GLADyS's primary observability and development tool, but it's being built ad-hoc without proper architectural foundation. Current issues:

1. **No component abstraction** - Each tab is custom HTML, duplicating filter/table/form patterns
2. **Tight coupling** - Form fields directly map to proto structure; proto changes cascade through UI
3. **Limited testability** - Mostly manual browser testing; no automated UI tests
4. **Weak observability** - Hard to debug issues; no built-in performance metrics or state inspection
5. **Unclear design patterns** - Pattern A exists but isn't comprehensive; widget APIs not documented

**The dashboard deserves first-class architecture.** It's not just a debug tool - it's how developers validate GLADyS works.

---

## Current Stack Assessment

**Technology:**
- **Backend**: FastAPI (Python) with Jinja2 templates
- **Frontend**: htmx (HTML-over-the-wire) + Alpine.js (client-side state)
- **Styling**: TailwindCSS
- **Pattern**: Server-side rendering (Pattern A) with progressive enhancement

**Strengths:**
- ✅ Simple, fast to develop
- ✅ Python-native (fits GLADyS stack)
- ✅ Server-driven (good for observability at backend)
- ✅ Low JS complexity
- ✅ Cross-platform (web-based)

**Weaknesses:**
- ❌ Weak component abstraction (Jinja macros are limited)
- ❌ Hard to test (no E2E framework, no component tests)
- ❌ Tight coupling between layers (form → backend → proto)
- ❌ Limited ecosystem (htmx + Alpine.js community smaller than React/Vue)
- ❌ Doesn't scale well for complex UIs

**Verdict:** Current stack can meet Phase 2-3 needs IF properly architected with widget library, service layer, and testing. Beyond Phase 3, evaluate migration to React/Svelte with REST API.

---

## Architectural Recommendations

### 1. Widget Library (Reusable Components)

**Goal:** Eliminate duplicated HTML, make widgets configurable and testable.

**Key widgets:**
- **FilterPanel** - Configurable filtering (source, date range, salience, etc.)
- **ExpandableRow** - Parent-row drill-down with visual shading to differentiate parent/child
- **DataGrid** - Sortable, pageable table with configurable columns
- **FormBuilder** - Schema-driven forms (reduces form → proto coupling)
- **MetricCard** - Observability widget (query time, result count, errors)

**Pattern: Configuration-driven**
```python
# Backend passes config, widget renders itself
filter_config = {
    "fields": [
        {"name": "source", "type": "select", "options": ["minecraft", "kitchen"]},
        {"name": "salience_min", "type": "range", "min": 0, "max": 1}
    ]
}
```

### 2. Service Layer (Separation of Concerns)

**Goal:** Decouple business logic from presentation, make services testable.

**Architecture:**
```
Services (business logic, no HTTP/templates)
  ↓
Controllers (routing, template rendering)
  ↓
Widgets (UI components)
```

**Example:**
```python
# services/event_service.py - testable without HTTP
class EventService:
    def list_events(filters: EventFilters) -> list[Event]: ...
    def create_event(data: EventData) -> Event: ...

# routers/events.py - thin routing layer
@router.get("/events")
async def list_events(request):
    events = event_service.list_events(EventFilters.from_request(request))
    return templates.render("events.html", events=events)
```

### 3. Testing Strategy (Confidence in Changes)

**Goal:** Automated testing at multiple layers so devs can validate changes quickly.

| Layer | Tool | What to test |
|-------|------|------------|
| Unit | pytest | Services, data conversion, proto mapping |
| Integration | pytest + TestClient | API endpoints, gRPC calls |
| E2E | Playwright | Full workflows (submit event, verify display) |
| Component | pytest + template tests | Widget rendering with different configs |

**Example E2E test:**
```python
def test_submit_event_with_salience(page):
    page.goto("/dashboard")
    page.click("#show-advanced")
    page.fill("#threat", "0.8")
    page.click("#submit")
    assert page.locator(".event-row").count() > 0
```

### 4. Observability Built-In

**Goal:** Dashboard helps devs understand what's happening without external tools.

**Features to add:**
- **Debug panel** (collapsible): Show filters, query time, result count, gRPC status
- **Error boundary**: Graceful degradation when services fail
- **Performance metrics**: Client-side timing, backend latency
- **State inspector**: View Alpine.js state (dev mode only)

---

## High-Level Next Steps

**This work deserves a dedicated phase/milestone:**

### Phase: Dashboard Architecture Hardening

**Milestone:** Dashboard as First-Class App

**Issues to create:**
1. **Widget library** - Design and implement reusable components (FilterPanel, ExpandableRow, DataGrid, FormBuilder)
2. **Service layer refactor** - Extract business logic from routers into testable services
3. **E2E testing framework** - Set up Playwright, write tests for critical workflows
4. **Widget API documentation** - Document each widget's configuration schema
5. **Observability widgets** - Add debug panel, metrics, state inspector
6. **Component architecture doc** - Update DASHBOARD_COMPONENT_ARCHITECTURE.md with widget patterns

**Success criteria:**
- New dashboard features can be added without touching existing HTML (configure, don't code)
- Backend services testable without HTTP/templates
- E2E tests cover critical user workflows
- Developers can debug issues via built-in observability widgets

---

## Deferred Decisions

**These require more investigation and will be addressed in the dedicated phase:**

1. **Should we migrate to React/Svelte?** Current stack works for Phase 2-3, but may not scale beyond. Evaluate after Phase 3 completion.
2. **REST API design** - If we decouple frontend, what does the API look like? JSON-based? GraphQL?
3. **Widget state management** - Alpine.js for simple state, but complex widgets may need more structure.
4. **Performance budget** - What are acceptable load times? How do we measure and enforce?

---

## References

- [DASHBOARD_COMPONENT_ARCHITECTURE.md](DASHBOARD_COMPONENT_ARCHITECTURE.md) - Current Pattern A specification
- [ITERATIVE_DESIGN.md](ITERATIVE_DESIGN.md) - Phase framework
- [Phase 7: Design Evaluation & Tech Debt](phases/phase7.md) - Potential location for dashboard hardening work

---

**Note:** This document captures the architectural vision. Implementation is deferred to a dedicated session/phase. For now, continue using current stack with Pattern A, accepting tight coupling as technical debt to be addressed later.
