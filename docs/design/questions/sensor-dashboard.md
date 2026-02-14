# Sensor Dashboard & Control Plane

**Created**: 2026-02-01
**Status**: ✅ Resolved (2026-02-12)
**Resolution**: See [SENSOR_DASHBOARD.md](../SENSOR_DASHBOARD.md)

---

## Design Complete

Full specification: [docs/design/SENSOR_DASHBOARD.md](../SENSOR_DASHBOARD.md)

All design questions resolved:

- ✅ **Control plane + observation**: Both (lifecycle management + metrics/health observability)
- ✅ **Registration**: `sensors` table linked to `skills` table, manifest-driven, persisted in DB
- ✅ **gRPC changes**: Generic SendCommand for sensor lifecycle management (COMMAND_START/STOP/RECOVER) + GetQueueStats
- ✅ **Tab layout**: New "Sensors" tab with drill-down pattern (not extension of Lab tab)

## Key Decisions

- **Database**: Hybrid approach (DB for state/metrics, gRPC for commands)
- **Schema**: `sensors`, `sensor_status`, `sensor_metrics` tables (30-day retention)
- **Observability**: Queue visibility (driver→adapter, adapter→orchestrator), consolidation ratio, per-source metrics
- **Accessibility**: Colorblind-friendly palette (blue/gray/orange + symbols)
- **Heartbeat**: 30-60s interval for dead sensor detection when idle

## Implementation

Ready prompts:

- Schema migration: `efforts/poc2/prompts/sensor-dashboard-schema.md`
- Metrics strip: `efforts/poc2/prompts/sensor-metrics-strip.md`

Tracked in PoC 2 milestone.
