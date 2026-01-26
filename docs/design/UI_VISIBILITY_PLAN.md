# UI Visibility Features Plan

**Created**: 2026-01-26
**Status**: Implemented
**File**: `src/ui/dashboard.py`

---

## Overview

Add three visibility features to the Streamlit dashboard to help developers understand system state during testing.

---

## Feature 1: Service Health Panel

**Location**: Sidebar, under "Connection Status"

**Purpose**: Show gRPC health status of all services at a glance.

**UI Mockup**:
```
## Service Health
memory-python    [OK] HEALTHY
memory-rust      [OK] HEALTHY
orchestrator     [OK] HEALTHY
executive-stub   [!!] UNREACHABLE
```

**Implementation**:
1. Add `get_service_health(service, addr)` function that calls `GetHealth` RPC
2. Add `render_service_health()` function in sidebar
3. Use existing `types_pb2.GetHealthRequest`
4. Color-code: green for HEALTHY, red for UNHEALTHY/unreachable, yellow for DEGRADED

**gRPC calls**:
- `MemoryStorageStub.GetHealth()` → memory-python
- `SalienceGatewayStub.GetHealth()` → memory-rust
- `OrchestratorServiceStub.GetHealth()` → orchestrator
- `ExecutiveServiceStub.GetHealth()` → executive-stub

**Effort**: Small (30 lines)

---

## Feature 2: Cache Inspector

**Location**: New tab "Cache" alongside "Laboratory" and "Event Log"

**Purpose**: View Rust salience gateway cache contents and stats.

**UI Mockup**:
```
## Cache Statistics
Size: 42 / 1000 (4.2%)
Hit Rate: 85.3%
Total Hits: 1,247
Total Misses: 215

[Flush Cache]

## Cached Heuristics
| ID (short) | Name | Hits | Last Hit |
|------------|------|------|----------|
| a1b2c3d4   | oven-safety | 47 | 2m ago |
| e5f6g7h8   | low-health  | 23 | 5m ago |
```

**Implementation**:
1. Add `get_salience_stub()` function for Rust gateway connection
2. Add `render_cache_tab()` function
3. Call `GetCacheStats` RPC for statistics
4. Call `ListCachedHeuristics` RPC for table
5. Add "Flush Cache" button calling `FlushCache` RPC

**gRPC calls**:
- `SalienceGatewayStub.GetCacheStats()`
- `SalienceGatewayStub.ListCachedHeuristics()`
- `SalienceGatewayStub.FlushCache()` (button action)

**Effort**: Medium (80 lines)

---

## Feature 3: Flight Recorder View

**Location**: New tab "Flight Recorder" or section in "Event Log" tab

**Purpose**: Show recent heuristic fires with outcomes for learning loop debugging.

**UI Mockup**:
```
## Recent Heuristic Fires
| Time | Heuristic | Event | Outcome | Feedback |
|------|-----------|-------|---------|----------|
| 14:32 | oven-safety | "oven left on" | success | explicit |
| 14:28 | low-health | "health at 10%" | pending | - |
| 14:15 | creeper-alert | "creeper nearby" | success | implicit |

Filter: [All] [Pending] [Success] [Failure]
```

**Implementation**:
1. Add `render_flight_recorder()` function
2. Query `heuristic_fires` table directly (already have DB connection)
3. Join with `heuristics` table for names
4. Add filter selectbox for outcome status

**SQL Query**:
```sql
SELECT
    hf.fired_at,
    h.name as heuristic_name,
    hf.event_text,
    hf.outcome,
    hf.feedback_source
FROM heuristic_fires hf
JOIN heuristics h ON hf.heuristic_id = h.id
ORDER BY hf.fired_at DESC
LIMIT 20
```

**Effort**: Medium (60 lines)

---

## Implementation Order

1. **Service Health Panel** - Simplest, immediate value, uses existing patterns
2. **Cache Inspector** - Requires new gRPC stub setup
3. **Flight Recorder** - SQL only, no new gRPC

---

## File Changes

| File | Changes |
|------|---------|
| `src/ui/dashboard.py` | Add 3 new functions, modify `main()` and `render_sidebar()` |

**No new files needed** - all changes in dashboard.py.

---

## Dependencies

All dependencies already exist:
- `types_pb2` for Health messages
- `memory_pb2_grpc` for SalienceGateway stub
- psycopg2 for DB queries (already used)

---

## Testing

Manual testing via:
```bash
python scripts/docker.py start all
cd src/ui && uv run streamlit run dashboard.py
```

Verify:
1. Health panel shows status for all 4 services
2. Cache tab shows stats and heuristic list
3. Flight recorder shows recent fires from DB
