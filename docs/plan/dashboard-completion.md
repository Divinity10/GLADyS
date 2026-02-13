# Dashboard Completion Plan

**Status**: Active (BLOCKING PROJECT)
**Created**: 2026-02-03
**Branch**: `dashboard/response-heuristics-tabs`

## Coordination Pattern

- **Design sessions**: Define patterns, create specs, write plans, make architectural decisions
- **Implementation sessions**: Execute phases using prompts in `docs/prompts/`
- **Scott (coordinator)**: Reviews output, passes work between sessions, makes final decisions

**Handoff flow:**

1. Design session creates/updates spec and prompts
2. Scott reviews and approves
3. Implementation session executes prompt
4. Scott verifies checkpoint (tests pass + works in browser)
5. Next phase begins

**Escalation**: If implementation hits unexpected design questions, escalate back to design session via Scott.

## Context

Project paused until dashboard is fully working and testable. 2+ days lost to debugging. Dashboard is critical infrastructure — without it, no way to verify the pipeline works.

## GitHub Tracking

**Milestone**: [Dashboard Completion](https://github.com/Divinity10/GLADyS/milestone/6)

| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #86 | API Gap: ListFires RPC | P0-critical | ✅ Closed |
| #87 | API Gap: GetMetrics RPC | P2-medium | Deferred |
| #88 | Phase 2: Heuristics tests | P1-high | ✅ Closed |
| #89 | Phase 3: Learning tab (rework) | P1-high | ✅ Closed |
| #90 | Phase 4: Logs tab | P2-medium | ✅ Closed |
| #91 | Phase 5: LLM/Settings audit | P2-medium | ✅ Closed |
| #92 | Phase 6: Integration tests | P2-medium | Ready (Playwright) |

## Phases

| Phase | Work | Checkpoint | Status |
|-------|------|-----------|--------|
| 1 | Document pattern | `DASHBOARD_WIDGET_SPEC.md` updated | ✅ Complete |
| 2 | Heuristics tests complete | All 7 unit tests pass | ✅ Complete |
| 3 | Learning tab migrated | Pattern A, tests pass, rows render | ✅ Complete |
| 4 | Logs tab migrated | Pattern A, tests pass, logs display | ✅ Complete |
| 5 | LLM/Settings fixed | Audit complete, Pattern A if needed | ✅ Complete |
| 6 | Integration tests | Suite exists, runs pre-merge | Pending |

## Rules

- Each phase ends with "tests pass" + "works in browser"
- No phase is complete until both verified
- Phase N must complete before Phase N+1 starts
- Dashboard isn't done until ALL 6 phases complete

## Implementation Prompts

| Phase | Prompt | Notes |
|-------|--------|-------|
| 2 | [`dashboard-phase2-heuristics-tests.md`](../prompts/dashboard-phase2-heuristics-tests.md) | Ready |
| 3 | [`impl-listfires-rpc-and-phase3-rework.md`](../prompts/impl-listfires-rpc-and-phase3-rework.md) | Combined #86 + #89 |
| 4 | [`dashboard-phase4-logs-tab.md`](../prompts/dashboard-phase4-logs-tab.md) | Ready |
| 5 | [`dashboard-phase5-llm-settings-audit.md`](../prompts/dashboard-phase5-llm-settings-audit.md) | Ready |
| 6 | [`dashboard-phase6-integration-tests.md`](../prompts/dashboard-phase6-integration-tests.md) | **NEEDS DESIGN SESSION** |

## Phase Details

### Phase 1: Document Pattern ✅

- Updated `docs/design/DASHBOARD_WIDGET_SPEC.md`
- Heuristics tab is canonical example
- DataTable pattern with checklist
- Required tests defined (unit + integration)
- Implementation prompts created for Phases 2-6

### Phase 2: Heuristics Tests Complete

**Current state**: 6 of 7 unit tests exist, 0 integration tests

**Missing tests**:

- Unit: Link href/dispatch is correct (cross-tab navigation)
- Unit: Button posts to correct endpoint
- Integration: All 3 tests

**Files to modify**:

- `tests/test_heuristics_rows.py` — add missing unit tests

### Phase 3: Learning Tab Migration

**Issue**: #89 (blocked by #86)
**Current state**: Mostly implemented, but uses direct DB access. **Needs rework.**
**Blocker**: #86 (ListFires RPC) must be done first.

**Combined prompt**: [`impl-listfires-rpc-and-phase3-rework.md`](../prompts/impl-listfires-rpc-and-phase3-rework.md)

**Work required**:

1. Add `ListFires` RPC to Memory service (#86)
2. Rework `backend/routers/fires.py` to use gRPC
3. Rework tests to mock gRPC stub
4. Verify in browser

### Phase 4: Logs Tab Migration

**Current state**: Uses Alpine x-for (broken)
**Target**: Pattern A

**Files to create/modify**:

- `backend/routers/logs.py` — may need HTML variant
- `frontend/components/logs.html` — REWRITE
- `frontend/components/logs_rows.html` — NEW
- `tests/test_logs_rows.py` — NEW

### Phase 5: LLM/Settings Audit

**Current state**: Unknown — needs audit
**Target**: Determine if broken, fix if needed

**Steps**:

1. Manual test LLM tab — do rows render?
2. Manual test Settings tab — do rows render?
3. If broken, migrate to Pattern A
4. Add tests

### Phase 6: Integration Tests

**Goal**: Browser-based tests that catch htmx/Alpine rendering failures

**Tests needed** (per DataTable):

1. Tab loads → rows visible in DOM
2. Click cross-tab link → other tab loads
3. Click action button → feedback appears

**Framework**: Playwright (pytest-playwright)

## Related Docs

- [DASHBOARD_WIDGET_SPEC.md](../design/DASHBOARD_WIDGET_SPEC.md) — Pattern definition
- [DASHBOARD_COMPONENT_ARCHITECTURE.md](../design/DASHBOARD_COMPONENT_ARCHITECTURE.md) — Pattern A vs B
- [DASHBOARD_V2.md](../design/DASHBOARD_V2.md) — Overall dashboard design
