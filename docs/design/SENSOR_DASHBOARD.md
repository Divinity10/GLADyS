# Sensor Dashboard & Control Plane

**Status**: Approved design
**Date**: 2026-02-12
**Issue**: #62
**Parent**: [SENSOR_ARCHITECTURE.md](SENSOR_ARCHITECTURE.md)
**PoC Scope**: PoC 2 (Multi-Sensor Pipeline)

## Purpose

Define the dashboard interface for managing and testing the GLADyS sensor subsystem. The dashboard provides observability into sensor health, metrics, and testing capabilities for developers building and debugging sensors.

This design covers:

- Database schema for sensor registration and metrics
- Dashboard UI (new Sensors tab)
- Metrics strip updates (system-wide sensor health)
- Orchestrator gRPC extensions for sensor management

---

## 1. Overview

The sensor dashboard is **critical infrastructure** for PoC 2. Without it, there is no way to:

- Register and activate sensors
- Monitor sensor health and throughput
- Debug adapter queue backlogs
- Test sensors with synthetic messages
- Verify capture/replay functionality

### **Design Principles**

1. **Observability over control**: Visibility into sensor internals is primary; lifecycle commands are secondary
2. **Per-sensor context**: Testing tools (message queue, playback) are sensor-specific, shown in drill-down
3. **Accessibility**: Color + symbol + position encoding (colorblind-friendly)
4. **Conciseness**: Limited real estate in metrics strip requires dense information display
5. **Pattern A compliance**: Server-side rendering (Jinja) for all data tables, Alpine.js for interactivity only

---

## 2. Architecture Decisions

All decisions from design discussion (2026-02-12):

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Data persistence** | Hybrid: DB for state/metrics, gRPC for commands | DB survives restarts, efficient queries, decoupled from orchestrator memory |
| **Schema structure** | Separate tables: `sensors`, `sensor_status`, `sensor_metrics` | Clean separation: static config, runtime state, time-series data |
| **Skill pack components** | `sensors` table links to `skills` table via `skill_id` | One pack can have multiple sensors; sensor-specific fields don't belong in skills table |
| **Tab layout** | Single "Sensors" tab with drill-down pattern | Testing tools are per-sensor context; avoids tab proliferation |
| **Queue observability** | Show inbound (driver→adapter) + outbound (adapter→orchestrator) queues | Core pipeline visibility; debug backlog issues |
| **Multi-driver sources** | Sensor decides source string per event | Gmail: `source="scott@example.com"`, not `source="gmail"` |
| **Metrics granularity** | Aggregate (sensor-level) + per-source breakdown (drill-down) | Fast health scan + root cause analysis |
| **Consolidation ratio** | Key metric with per-sensor thresholds | Shows adapter health; different expectations per sensor type |
| **Orchestrator metrics** | Queue depth + avg wait in metrics strip | System-wide health; detects orchestrator falling behind |
| **Sensor count format** | `●2 / ○1 / ⚠1` (blue/gray/orange symbols) | Concise, colorblind-friendly, triple-encoded (position + symbol + color) |
| **Heartbeat** | Keep it (30-60s interval) | Dead sensor detection when idle; metrics delivery without events |
| **Metrics retention** | 30 days, rolling delete | Trend analysis, post-mortem debugging, low storage cost |

---

## 3. Database Schema

### 3.1 Skill Pack Architecture

**Component types within a skill pack:**

1. **Sensors** → `sensors` table
2. **Preprocessors** → `preprocessors` table (future)
3. **Domain skills** → `domain_skills` table (future)
4. **Heuristics** → `heuristics` table (existing, uses `origin='pack'` + `origin_id`)

### 3.2 Schema Design

```
skills (skill pack registration)
  ↓ (1:many)
sensors (sensor components)
  ↓ (1:1)
sensor_status (runtime state)
  ↓ (1:many)
sensor_metrics (time-series heartbeat data)
```

### 3.3 Table Definitions

#### **`sensors` table (new)**

Sensor component within a skill pack. One skill pack can have multiple sensors.

```sql
CREATE TABLE sensors (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id                    UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    sensor_name                 TEXT NOT NULL,
    sensor_type                 TEXT NOT NULL CHECK (sensor_type IN ('push', 'poll')),
    source_pattern              TEXT NOT NULL,

    -- Protocol config (from manifest)
    heartbeat_interval_s        INTEGER NOT NULL DEFAULT 30,
    adapter_language            TEXT,
    driver_count                INTEGER DEFAULT 1,

    -- Health monitoring thresholds (per-sensor consolidation expectations)
    expected_consolidation_min  FLOAT DEFAULT 0.8,
    expected_consolidation_max  FLOAT DEFAULT 1.2,

    -- Manifest data
    manifest                    JSONB NOT NULL,
    config                      JSONB DEFAULT '{}',

    created_at                  TIMESTAMPTZ DEFAULT now(),
    updated_at                  TIMESTAMPTZ DEFAULT now(),

    UNIQUE(skill_id, sensor_name)
);

ALTER TABLE sensors OWNER TO gladys;

CREATE INDEX idx_sensors_skill ON sensors(skill_id);
CREATE INDEX idx_sensors_source_pattern ON sensors(source_pattern);
CREATE INDEX idx_sensors_type ON sensors(sensor_type);

COMMENT ON TABLE sensors IS 'Sensor components registered via skill packs';
COMMENT ON COLUMN sensors.source_pattern IS 'Source identifier pattern (e.g., "melvor", "gmail:%", "%@example.com")';
COMMENT ON COLUMN sensors.expected_consolidation_min IS 'Lower bound for healthy consolidation ratio (messages:events)';
COMMENT ON COLUMN sensors.expected_consolidation_max IS 'Upper bound for healthy consolidation ratio (messages:events)';
```

**Example consolidation thresholds:**

- **RuneScape**: min=20, max=60 (expect 20:1 to 60:1 ratio)
- **Melvor**: min=10, max=40 (expect 10:1 to 40:1 ratio)
- **Email**: min=0.8, max=1.2 (expect ~1:1 ratio, ±20%)
- **Sudoku**: min=0.8, max=1.2 (expect ~1:1 ratio, ±20%)

#### **`sensor_status` table (new)**

Current runtime state for each sensor. Updated by orchestrator on heartbeat receipt.

```sql
CREATE TABLE sensor_status (
    sensor_id           UUID PRIMARY KEY REFERENCES sensors(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'inactive'
                        CHECK (status IN ('inactive', 'active', 'disconnected', 'error', 'recovering')),
    last_heartbeat      TIMESTAMPTZ,
    last_error          TEXT,
    error_count         INTEGER DEFAULT 0,
    active_sources      TEXT[] DEFAULT '{}',
    events_received     BIGINT DEFAULT 0,
    events_published    BIGINT DEFAULT 0,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE sensor_status OWNER TO gladys;

CREATE INDEX idx_sensor_status_status ON sensor_status(status);
CREATE INDEX idx_sensor_status_heartbeat ON sensor_status(last_heartbeat DESC NULLS LAST);

COMMENT ON TABLE sensor_status IS 'Runtime state for each sensor (updated by orchestrator on heartbeat)';
COMMENT ON COLUMN sensor_status.active_sources IS 'Current sources reported in latest heartbeat (for multi-driver sensors)';
COMMENT ON COLUMN sensor_status.events_received IS 'Lifetime counter: total driver messages received';
COMMENT ON COLUMN sensor_status.events_published IS 'Lifetime counter: total events published to orchestrator';
```

**Status values:**

- `inactive` - Sensor registered but not started
- `active` - Sensor running, heartbeats arriving
- `disconnected` - No heartbeat within 2x `heartbeat_interval_s`
- `error` - Error rate exceeded threshold
- `recovering` - `recover()` called, waiting for health confirmation

#### **`sensor_metrics` table (new)**

Time-series heartbeat data. One row per heartbeat. Rolling 30-day retention.

```sql
CREATE TABLE sensor_metrics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id               UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Event counters (incremental since last heartbeat)
    events_received         BIGINT NOT NULL,
    events_published        BIGINT NOT NULL,
    events_filtered         BIGINT DEFAULT 0,
    events_errored          BIGINT DEFAULT 0,

    -- Performance metrics
    avg_latency_ms          FLOAT,
    consolidation_ratio     FLOAT,

    -- Queue depths (snapshot at heartbeat time)
    inbound_queue_depth     INTEGER DEFAULT 0,
    outbound_queue_depth    INTEGER DEFAULT 0,

    -- Per-driver metrics (JSONB for multi-driver sensors)
    driver_metrics          JSONB DEFAULT '{}',

    created_at              TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE sensor_metrics OWNER TO gladys;

CREATE INDEX idx_sensor_metrics_sensor_time ON sensor_metrics(sensor_id, timestamp DESC);
CREATE INDEX idx_sensor_metrics_timestamp ON sensor_metrics(timestamp DESC);

COMMENT ON TABLE sensor_metrics IS 'Time-series heartbeat data (30-day rolling retention)';
COMMENT ON COLUMN sensor_metrics.consolidation_ratio IS 'events_received / events_published (adapter efficiency)';
COMMENT ON COLUMN sensor_metrics.inbound_queue_depth IS 'Driver→Adapter queue depth at heartbeat time';
COMMENT ON COLUMN sensor_metrics.outbound_queue_depth IS 'Adapter→Orchestrator queue depth at heartbeat time';
COMMENT ON COLUMN sensor_metrics.driver_metrics IS 'Per-driver stats for multi-driver sensors (e.g., Gmail per-account)';
```

**Retention policy** (run daily):

```sql
DELETE FROM sensor_metrics WHERE timestamp < NOW() - INTERVAL '30 days';
```

**Example `driver_metrics` JSONB** (Gmail sensor with 3 accounts):

```json
{
  "scott@example.com": {
    "events_handled": 23,
    "events_dropped": 0,
    "last_check": "2026-02-12T10:30:00Z"
  },
  "mike@example.com": {
    "events_handled": 15,
    "events_dropped": 1,
    "last_check": "2026-02-12T10:30:00Z"
  },
  "leah@example.com": {
    "events_handled": 0,
    "events_dropped": 0,
    "last_check": "2026-02-12T10:29:00Z"
  }
}
```

---

## 4. Dashboard Layout

### 4.1 Metrics Strip Update

**Current metrics strip:**

```
┌────────────────────────────────────────────────────────┐
│ Events: 1.2k | Heuristics: 45 | Responses: 38 | ...   │
└────────────────────────────────────────────────────────┘
```

**Updated metrics strip (PoC 2):**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Sensors: ●2/○1/⚠1 | Orch: 3 (0.2s) | Events: 1.2k | Heuristics: 45 | …│
└─────────────────────────────────────────────────────────────────────────┘
```

**New elements:**

1. **Sensor count**: `●2/○1/⚠1`
   - Format: `{live}/{idle}/{error}`
   - Symbols: `●` (filled circle), `○` (empty circle), `⚠` (warning triangle)
   - Colors: Blue (#3b82f6) / Gray (#6b7280) / Orange (#f59e0b)
   - Hover: "2 live, 1 idle, 1 error"

2. **Orchestrator queue**: `3 (0.2s)`
   - Format: `{queue_depth} ({avg_wait})`
   - Queue depth: Number of events in orchestrator's internal processing queue
   - Avg wait: Average time events spend in queue before processing starts
   - Color coding:
     - `0 (—)` → Green (healthy)
     - `3 (0.2s)` → White (normal)
     - `50 (2s)` → Yellow (elevated)
     - `150 (8s)` → Red (problem)

**Accessibility:**

- **Triple encoding**: Position + symbol + color (works for all colorblind types)
- **Hover tooltips**: Explicit text labels on hover
- **Colorblind palette**: Blue/orange (not red/green)

### 4.2 Sensors Tab (New)

Add new tab to dashboard navigation bar:

```html
<button @click="activeTab = 'sensors'"
        :class="activeTab === 'sensors' ? 'nav-tab-active' : 'nav-tab'"
        title="Sensor management and testing">
    Sensors
</button>
```

**Tab position**: After "Learning", before "LLM"

### 4.3 Sensors Tab Layout

```
┌─────────────────────────────────────────────────────────────┐
│ SENSORS TAB                                                  │
├─────────────────────────────────────────────────────────────┤
│ [Register New Sensor]                                   [▼] │ ← Collapsible form (Pattern A)
├─────────────────────────────────────────────────────────────┤
│ ACTIVE SENSORS                                               │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Sensor    Sources  Events/min  Ratio    Errors Queue │   │
│ │ melvor    1        83          52:1 ✓   0      0    ▼│   │
│ │ gmail     3        2           1:1 ✓    1      0    ▼│   │
│ │ sudoku    1        0           —        0      0    ▼│   │
│ │ runescape 1        247         8:1 ⚠    0      12   ▼│   │ ← Consolidation failing + queue backing up
│ └───────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│ MELVOR SENSOR DETAIL                            [Close X]   │ ← Drill-down panel (click row or ▼)
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Status: ● Active | Last heartbeat: 5s ago               │ │
│ │ [Deactivate] [Trigger Recovery] [Force Shutdown]        │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ PIPELINE QUEUES                                         │ │
│ │ Inbound (Driver→Adapter):  12 messages (oldest: 0.3s)  │ │
│ │                            [View Queue]                 │ │
│ │ Outbound (Adapter→Orch):   3 events (oldest: 0.1s)     │ │
│ │                            [View Queue]                 │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ METRICS (last hour)                                     │ │
│ │ Received: 6,483 | Published: 1,247 | Filtered: 0       │ │
│ │ Consolidation: 5.2:1 ✓ (expected: 10:1 to 40:1)        │ │
│ │ Error rate: 0% | Avg latency: 15ms                      │ │
│ │ [Chart: throughput over time]                           │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ TESTING TOOLS                                           │ │
│ │ [Create Test Message] [Playback Capture] [Backpressure] │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 4.4 Multi-Driver Sensor Drill-Down

**Gmail sensor** (3 email accounts):

```
┌─────────────────────────────────────────────────────────────┐
│ GMAIL SENSOR DETAIL                                 [Close] │
├─────────────────────────────────────────────────────────────┤
│ Status: ● Active | Last heartbeat: 8s ago                   │
│ Sources: 3 accounts (scott@, mike@, leah@)                  │
│ [Deactivate] [Trigger Recovery] [Force Shutdown]            │
├─────────────────────────────────────────────────────────────┤
│ AGGREGATE METRICS (last hour)                                │
│ Received: 38 | Published: 38 | Filtered: 0 | Errors: 1      │
│ Consolidation: 1:1 ✓ (expected: 0.9:1 to 1.1:1)            │
├─────────────────────────────────────────────────────────────┤
│ PER-SOURCE BREAKDOWN:                                        │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Source                Events  Errors  Last Check      │   │
│ │ scott@example.com     23      0       10:30 AM        │   │
│ │ mike@example.com      15      1       10:30 AM        │   │ ← Error here
│ │ leah@example.com      0       0       10:29 AM        │   │
│ └───────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│ PIPELINE QUEUES | TESTING TOOLS (same as single-driver)     │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 Queue View Drill-Down

Click **"View Queue"** on Inbound → Modal/panel shows raw driver messages:

```
┌─────────────────────────────────────────────────────────┐
│ INBOUND QUEUE (Driver→Adapter)                     [X]  │
├─────────────────────────────────────────────────────────┤
│ Age    | Type              | Preview                    │
│ 0.1s   | game.position     | {"x": 123, "y": 456}      │
│ 0.2s   | game.health       | {"current": 85, "max":100}│
│ 0.3s   | game.position     | {"x": 123, "y": 457}      │
│ ...    | ...               | ...                        │
└─────────────────────────────────────────────────────────┘
```

Click **"View Queue"** on Outbound → Shows normalized GLADyS events:

```
┌──────────────────────────────────────────────────────────┐
│ OUTBOUND QUEUE (Adapter→Orchestrator)              [X]  │
├──────────────────────────────────────────────────────────┤
│ Age    | Source  | Intent        | Text                 │
│ 0.05s  | melvor  | actionable    | Player moved to...   │
│ 0.08s  | melvor  | informational | Health at 85/100     │
│ 0.10s  | melvor  | actionable    | Combat started...    │
└──────────────────────────────────────────────────────────┘
```

### 4.6 Key Metrics Explained

| Metric | What it shows | Why it matters |
|--------|---------------|----------------|
| **Events/min** | Recent event throughput | Quick activity indicator |
| **Consolidation ratio** | `events_received / events_published` | Adapter efficiency; detects consolidation failures |
| **Errors** | Error count (last hour) | Health indicator |
| **Queue** | Inbound queue depth | Is adapter keeping up with driver? |
| **Orch queue** (metrics strip) | Orchestrator internal queue | Is orchestrator keeping up with all sensors? |

**Consolidation ratio symbols:**

- `52:1 ✓` (green) - Within expected range (e.g., RuneScape: 20-60)
- `8:1 ⚠` (yellow) - Outside expected range (consolidation failing)
- `—` (gray) - No data yet

---

## 5. Orchestrator gRPC API Extensions

### 5.1 Sensor Lifecycle RPCs

```protobuf
service Orchestrator {
    // Existing RPCs...

    // Sensor lifecycle management
    rpc ActivateSensor(ActivateSensorRequest) returns (ActivateSensorResponse);
    rpc DeactivateSensor(DeactivateSensorRequest) returns (DeactivateSensorResponse);
    rpc TriggerRecovery(TriggerRecoveryRequest) returns (TriggerRecoveryResponse);
    rpc ForceShutdownSensor(ForceShutdownSensorRequest) returns (ForceShutdownSensorResponse);

    // Sensor status query
    rpc GetQueueStats(GetQueueStatsRequest) returns (GetQueueStatsResponse);
}

message ActivateSensorRequest {
    string sensor_id = 1;  // UUID from sensors table
}

message ActivateSensorResponse {
    bool success = 1;
    string error_message = 2;
}

message DeactivateSensorRequest {
    string sensor_id = 1;
}

message DeactivateSensorResponse {
    bool success = 1;
    string error_message = 2;
}

message TriggerRecoveryRequest {
    string sensor_id = 1;
}

message TriggerRecoveryResponse {
    bool recovery_attempted = 1;
    bool recovered = 2;  // True if sensor healthy after recovery
    string error_message = 3;
}

message ForceShutdownSensorRequest {
    string sensor_id = 1;
}

message ForceShutdownSensorResponse {
    bool success = 1;
    string error_message = 2;
}

message GetQueueStatsRequest {
    // Empty - returns orchestrator-wide queue stats
}

message GetQueueStatsResponse {
    int32 queue_depth = 1;          // Events in internal processing queue
    float avg_wait_time_ms = 2;     // Average time events spend in queue
    float processing_rate_per_sec = 3;  // Events/second throughput
}
```

### 5.2 Heartbeat Processing

Sensors send heartbeat metrics via existing `PublishEvent` RPC with `source="system.metrics"`:

```protobuf
// Heartbeat event (sent every heartbeat_interval_s)
Event {
    id = "<uuid>"
    source = "system.metrics"
    structured = {
        "sensor_id": "<uuid>",
        "events_received": 1247,
        "events_published": 1247,
        "events_filtered": 0,
        "events_errored": 0,
        "avg_latency_ms": 15.3,
        "inbound_queue_depth": 12,
        "outbound_queue_depth": 3,
        "active_sources": ["melvor"],
        "driver_metrics": {}  // Per-driver stats (for multi-driver sensors)
    }
}
```

**Orchestrator processing:**

1. Route `source="system.metrics"` events to system handler (not salience pipeline)
2. Parse `structured.sensor_id`
3. Update `sensor_status` table (last_heartbeat, active_sources, counters)
4. Insert row into `sensor_metrics` table (time-series)
5. Check health: no heartbeat within 2x interval → update status to `disconnected`

---

## 6. Implementation Approach

### 6.1 Phase 1: Database & Metrics Strip (P0)

**Ready to implement immediately:**

1. **Schema migration**
   - Create `sensors`, `sensor_status`, `sensor_metrics` tables
   - Add indexes and comments
   - **Prompt**: [efforts/poc2/prompts/sensor-dashboard-schema.md](../../efforts/poc2/prompts/sensor-dashboard-schema.md)

2. **Metrics strip update**
   - Add sensor count `●2/○1/⚠1` (query `sensor_status` table)
   - Add orchestrator queue `3 (0.2s)` (new gRPC endpoint)
   - **Prompt**: [efforts/poc2/prompts/sensor-metrics-strip.md](../../efforts/poc2/prompts/sensor-metrics-strip.md)

### 6.2 Phase 2: Sensors Tab (P1)

**After Phase 1 complete:**

1. **Sensors tab implementation**
   - Router: `backend/routers/sensors.py` (Pattern A - server-side rendering)
   - Templates: `sensors.html`, `sensor_rows.html`, `sensor_detail.html`
   - Drill-down with queue views, metrics charts, testing tools
   - **Prompt**: TBD (after design doc review)

### 6.3 Phase 3: Orchestrator Extensions (P1)

**After Phase 1 complete:**

1. **Orchestrator gRPC implementation**
   - Add sensor lifecycle RPCs (Activate, Deactivate, TriggerRecovery, ForceShutdown)
   - Add GetQueueStats RPC
   - Implement heartbeat processing (system.metrics event handling)
   - **Prompt**: TBD (after design doc review)

### 6.4 Testing Strategy

**Unit tests:**

- Sensor registration (DB operations)
- Heartbeat processing (system.metrics event routing)
- Queue stats calculation
- Consolidation ratio computation

**Integration tests:**

- Register sensor → appears in dashboard
- Activate sensor → status changes to `active`
- Heartbeat arrives → `sensor_status` + `sensor_metrics` updated
- No heartbeat for 2x interval → status changes to `disconnected`

**Manual tests:**

- Metrics strip shows correct sensor count
- Sensors tab loads and displays sensor list
- Drill-down shows queue depths, metrics, per-source breakdown
- Lifecycle buttons work (activate, deactivate, recover, shutdown)

---

## 7. Out of Scope (Future Enhancements)

**System Health Tab** (PoC 3+):

- Deep dive into orchestrator performance
- Queue depth over time (charts)
- Processing rate trends
- Breakdown by decision path (heuristic vs LLM)
- Worker pool utilization

**Advanced testing tools** (PoC 3+):

- Capture controls (start/stop JSONL capture at runtime)
- Replay with speed multiplier (2x, 10x playback)
- Backpressure generator (synthetic load testing)

**Sensor registration UI** (PoC 3+):

- Dashboard form for manifest upload
- Validation and preview
- For PoC 2: sensors registered via CLI or manual DB insert

---

## 8. Success Criteria

✅ **Observability**: Developers can see sensor status, metrics, and queue depths at a glance
✅ **Control**: Developers can activate, deactivate, and recover sensors from dashboard
✅ **Debugging**: Developers can inspect adapter queues to diagnose backlog issues
✅ **Accessibility**: All visual indicators work for colorblind users
✅ **Performance**: Dashboard queries are fast (<500ms for sensor list)
✅ **Consistency**: Follows Pattern A (server-side rendering) like other dashboard tabs

---

## 9. References

- [SENSOR_ARCHITECTURE.md](SENSOR_ARCHITECTURE.md) - Sensor protocol, manifest, metrics
- [DASHBOARD_COMPONENT_ARCHITECTURE.md](DASHBOARD_COMPONENT_ARCHITECTURE.md) - Pattern A, rendering guidelines
- Issue #62 - Original sensor dashboard question
- PoC 2 State - Active work tracking
