# Sensor Architecture

**Status**: Proposed
**Date**: 2026-02-07
**Issue**: #143
**PoC Scope**: PoC 2 (Multi-Sensor Pipeline)
**Informed by**: PoC 1 findings F-14, F-15, F-16, F-18, F-19, F-20, F-21

## Purpose

Define the architecture for GLADyS sensors — components that capture events from external applications and deliver them to the orchestrator as normalized GLADyS events. This doc covers the sensor pipeline, base class contract, event contract extensions, and PoC 2 sensor profiles.

Sensors are one component of a **skill pack** (sensor + domain skill + heuristics). This doc covers the sensor layer only. Domain skills are a separate concern (PoC 3).

---

## 1. Architecture: Driver / Sensor / Orchestrator

Three-layer pipeline with clear boundaries.

```
┌──────────┐     native      ┌──────────┐     gRPC        ┌──────────────┐
│  Driver  │ ──────────────► │  Sensor  │ ─────────────► │ Orchestrator │
│ (polyglot)│   transport    │ (Python)  │  PublishEvents  │              │
└──────────┘                 └──────────┘                 └──────────────┘
 App-specific                 Normalizes                   Routes, stores,
 event capture                to GLADyS                    processes
                              event contract
```

### 1.1 Driver (polyglot, lightweight)

- Runs inside or alongside the target application
- Language = whatever the app requires (Java for RuneLite, browser extension for web apps, etc.)
- Responsibilities: capture app events, send to sensor via native transport (HTTP, WebSocket, file, etc.)
- Does NOT normalize, classify, or filter — that's the sensor's job
- Reports driver-level metrics to sensor (events handled, dropped, errors)
- **Drivers are a sensor concern, not a GLADyS concern.** Each sensor decides the best way to collect data from its target. The base class does not manage driver lifecycle.

### 1.2 Sensor (Python, standardized)

- Receives raw driver data, normalizes to GLADyS event contract
- All sensors are Python — base class provides capture/replay, metrics, flow control for free
- Manages its own emit schedule (rate control independent of driver event rate)
- Publishes normalized events to orchestrator via gRPC `PublishEvents`
- How the sensor manages its driver(s) is an internal implementation detail. A game sensor may have one driver; an email sensor may manage multiple driver instances (one per account). The base class doesn't know or care.

### 1.3 Orchestrator interface

- Existing `PublishEvents` gRPC (bidirectional streaming)
- `RegisterComponent` for sensor registration
- `system.metrics` events routed to system handlers, not salience pipeline
- Orchestrator sees one sensor, not individual drivers — the sensor abstracts its driver topology

---

## 2. Event Contract

The GLADyS event contract defines what a sensor produces. The current `Event` message in `proto/common.proto` (fields 1-10, 15) is the base. PoC 2 adds three new fields.

### 2.1 Current base fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique event identifier |
| `timestamp` | Timestamp | When the event occurred |
| `source` | string | Sensor identifier |
| `raw_text` | string | Natural language description of the event |
| `structured` | Struct | Domain-specific fields (JSON) |
| `salience` | SalienceVector | Populated by salience service (not by sensor) |
| `entity_ids` | repeated string | Populated by entity extractor (not by sensor) |
| `matched_heuristic_id` | string | Populated downstream (not by sensor) |
| `metadata` | RequestMetadata | Trace/request context |

### 2.2 New fields (PoC 2)

| Field | Proto field # | Type | Default | Source |
|-------|--------------|------|---------|--------|
| `intent` | 11 | enum: `actionable`, `informational`, `unknown` | `unknown` | F-20 |
| `backfill` | 12 | bool | `false` | F-21 |
| `evaluation_data` | 13 | Struct | empty | F-19 |

**`intent`** — Routing hint from the sensor. `actionable` = may need a response, routes through full pipeline. `informational` = context only, stored but not routed through salience/executive. `unknown` = sensor doesn't know, let salience decide. The sensor knows best whether an event expects a response.

**`backfill`** — Marks events as pre-existing state dumped on connect (e.g., game buffers events during startup). Backfill events are stored for context but not routed through the pipeline. Learning system does not treat them as missed opportunities. Timestamps may be inaccurate.

**`evaluation_data`** — Optional second data bucket for solution/cheat data. Stored for learning and evaluation, stripped by orchestrator before executive sees it. Example: Sudoku solution visible in DOM — useful for evaluating response quality but must not appear in responses.

### 2.3 Delivery patterns

Two patterns for PoC 2 (streaming deferred):

| Pattern | How it works | Examples | Volume profile |
|---------|-------------|----------|---------------|
| Push (`event`) | Driver sends events when things happen | Game combat, game state changes | Bursty — zero to hundreds/sec |
| Poll | Sensor periodically checks state | Email check, system monitor | Steady — configurable interval |

Each pattern has different volume management characteristics. The `structured` field carries delivery-pattern-specific attributes when needed (e.g., `poll_interval` for poll sensors).

### 2.4 Domain interfaces

- Domain-specific payload lives in the `structured` field (JSON)
- Interfaces are defined by the skill pack, not by GLADyS core
- Sub-interfaces conditional on domain field values (e.g., `damage_type: "fire"` implies `damage_per_tick`, `duration` fields)
- `raw_text` best practice: natural-language sentences describing the event, not key-value dumps (F-02). "The player took 15 fire damage" not "damage_type=fire damage=15"

### 2.5 Source semantics

- Sensor decides the source string per event
- Flat string sufficient for PoC 2
- Used as hard filter in heuristic matching (F-01) — prevents cross-domain false matches
- Multi-driver sensors may differentiate source per driver instance or use a shared source — sensor's decision

---

## 3. Sensor Base Class

Python abstract base class that all PoC 2 sensors extend. Provides infrastructure for free; sensors implement domain-specific logic only.

### 3.1 Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class SensorBase(ABC):
    """Base class for all GLADyS sensors."""

    # --- Lifecycle (sensor implements) ---

    @abstractmethod
    async def start(self) -> None:
        """Start sensing. Connect to driver(s), begin event collection."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop sensing. Disconnect from driver(s), flush buffers."""
        ...

    @abstractmethod
    async def health(self) -> SensorHealth:
        """Report sensor health status."""
        ...

    @abstractmethod
    async def recover(self) -> bool:
        """Orchestrator requests self-healing.

        Called when the orchestrator detects the sensor is unhealthy
        (error rate above threshold, missed heartbeats, etc.).
        Sensor decides what to do: restart driver, clear buffers,
        reset state, etc.

        Returns True if recovery succeeded, False if sensor
        should be shut down.
        """
        ...

    # --- Event production (sensor implements) ---

    @abstractmethod
    async def emit_events(self) -> AsyncIterator[Event]:
        """Yield normalized GLADyS events.

        The sensor controls its own emit cadence — it may buffer
        driver events and consolidate them before yielding.
        """
        ...

    # --- Provided by base class (sensor does NOT override) ---

    # Capture/replay (§3.2)
    # Metrics collection (§3.3)
    # Flow control enforcement (§3.4)
    # Event buffering during orchestrator outage (§3.5)
    # Publish to orchestrator via gRPC
    # Dry-run mode (capture without publishing)
```

### 3.2 Capture / Replay

Base class feature — all sensors get it for free. Two capture boundaries, both JSONL.

**Boundary 1: Driver → Sensor (raw)**
Captures what the driver sends before the sensor normalizes it. Enables sensor development without the target application running.

**Boundary 2: Sensor → Orchestrator (normalized)**
Captures the normalized GLADyS events the sensor publishes. Enables orchestrator/pipeline testing without live sensors.

| Aspect | Design |
|--------|--------|
| Format | JSONL — one record per line, each with capture timestamp. Appendable, crash-safe, streamable. |
| Stop conditions | Time-based (`--capture-duration`) OR record-count (`--capture-count`), whichever hits first. |
| Replay timing | Preserves original inter-event deltas. Optional `--replay-speed` multiplier (2x, 10x, etc.). No "instant dump" default — flooding the orchestrator produces unrealistic test results. |
| Multi-driver | Capture tags each record with driver instance ID (sensor's concern — sensor knows its own drivers). |
| Who captures | Sensor's ingestion layer, not the driver. Drivers stay lightweight — capture logic in Python, not duplicated across driver languages. |
| Dry-run mode | `--dry-run`: capture without publishing to orchestrator. Enables testing sensors in isolation without the full stack. |

CLI flags: `--capture-duration`, `--capture-count`, `--replay <file>`, `--replay-speed <multiplier>`, `--dry-run`

### 3.3 Metrics

Base class maintains in-memory counters. Emitted as `system.metrics` events via `PublishEvents` on a configurable heartbeat interval.

**Sensor-level metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `events_received` | counter | Raw events from driver(s) |
| `events_published` | counter | Normalized events sent to orchestrator |
| `events_filtered` | counter | Intentionally suppressed |
| `events_errored` | counter | Failed during processing |
| `last_event_at` | timestamp | Most recent event received |
| `started_at` | timestamp | Sensor start time |
| `avg_latency_ms` | gauge | Rolling avg processing latency |
| `error_count` | counter | Total errors (all types) |

**Driver-level metrics** (driver reports to sensor via existing transport, sensor aggregates):

| Metric | Type | Description |
|--------|------|-------------|
| `driver.events_handled` | counter | App events the driver captured |
| `driver.events_dropped` | counter | App events the driver couldn't capture |
| `driver.errors` | counter | Driver-side errors |
| `driver.last_report_at` | timestamp | Last time driver sent metrics |

Driver metrics stored as JSONB since different drivers report different things.

**Heartbeat**: Configurable `heartbeat_interval_s` (declared in manifest). Dead sensor detection: no heartbeat within 2x interval = presumed dead. Orchestrator monitors this.

**Persistence**: Orchestrator writes metrics to `sensor_metrics` table (one row per heartbeat push, rolling retention).

### 3.4 Flow Control

**System-level strategy pattern.** The base class accepts a flow control strategy injected by the orchestrator at registration time. All sensors use the same strategy — sensors do not choose whether to participate. The strategy is a configuration setting.

```python
class FlowControlStrategy(Protocol):
    """System-level flow control. Injected by orchestrator."""

    def should_publish(self, latency_ms: float, queue_depth: int) -> bool:
        """Check whether the sensor should publish now."""
        ...

    def on_publish_complete(self, latency_ms: float) -> None:
        """Report publish latency for tracking."""
        ...
```

The base class calls the strategy before every publish. If the strategy says "don't publish," the event is buffered (and may be dropped per buffer policy — see §3.5).

**PoC 2**: Start with no flow control strategy (all publishes allowed). The strategy pattern exists in the base class so we can add rate limiting or BBR-inspired control later without changing sensors.

**Future (PoC 3+)**: BBR-inspired strategy that tracks `PublishEvents` response latency. Latency increase → reduce publish rate. Return to baseline → increase rate. Sensor-specific throttle priority (game sensor drops position updates first, keeps combat events) via a domain-specific callback.

### 3.5 Event Buffering (Orchestrator Unavailable)

When the orchestrator is unreachable, the base class buffers events locally.

| Aspect | Design |
|--------|--------|
| Buffer | Bounded in-memory queue (configurable max size) |
| Drop policy | When buffer is full, drop least important first: `backfill` → `informational` → `unknown` → `actionable` |
| Reconnect | Retry with exponential backoff |
| Flush | On reconnect, publish buffered events in order. Events that aged beyond a configurable TTL are dropped. |

This is a base class concern — all sensors get it. Sensors do not implement their own buffering.

### 3.6 Emit Schedule

The sensor controls its own emit cadence, independent of the driver's event rate. The sensor buffers driver events and emits consolidated events on a timer or on meaningful change (domain-specific). This is rate control — the sensor decides *how often* to emit, not *what* to emit.

Example: Driver fires position every 600ms. Sensor emits position every 5s unless movement exceeds a threshold.

The base class tracks `events_received` vs `events_published` for the consolidation ratio metric.

---

## 4. Sensor Lifecycle

### 4.1 Three-fold lifecycle

| Concern | What it means | PoC 2 approach |
|---------|--------------|----------------|
| **Install** | Sensor code + manifest in place, prereqs declared | Dashboard triggers registration with orchestrator. Sensor processes started manually or by script. |
| **Awareness** | Orchestrator knows about sensor, subscribes to metrics | `RegisterComponent` gRPC + DB persistence in `component_registry` table. Orchestrator reads registry on startup. |
| **Health** | Orchestrator monitors heartbeats, can recover or stop unhealthy sensors | Heartbeat monitoring (2x interval = dead). Error-rate threshold triggers `recover()` → if still unhealthy → shutdown. |

### 4.2 Orchestrator health management

The orchestrator monitors sensor health via the `system.metrics` heartbeat events:

1. **Heartbeat timeout**: No heartbeat within 2x `heartbeat_interval_s` → sensor presumed dead. Orchestrator updates status, dashboard shows disconnected.
2. **Error rate threshold**: Configurable error events per time unit. When exceeded, orchestrator calls `recover()` on the sensor.
3. **Recovery flow**: `recover()` returns `True` (sensor fixed itself) or `False` (needs shutdown). If `True`, orchestrator resets the error counter and resumes monitoring. If `False` or still unhealthy after a grace period, orchestrator stops the sensor.
4. **Manual control**: Dashboard can activate/deactivate sensors via orchestrator (sends stop/start signals).

### 4.3 Registration persistence

Sensor registrations persist in a DB table so the orchestrator knows what sensors exist across restarts. The table stores: sensor ID, manifest data, status (active/inactive/error), last seen timestamp. The orchestrator reads this on startup — it doesn't need sensors to re-register after an orchestrator restart.

---

## 5. Manifest

The sensor manifest declares sensor identity, capabilities, and dependencies. For PoC 2, the manifest drives registration and documentation. Specific fields will be finalized during the orchestrator redesign — the manifest concept is established here; field details are TBD.

### 5.1 Established fields

```yaml
# Identity
id: melvor-sensor
name: Melvor Idle Sensor
version: 1.0.0
type: sensor
description: Captures game state from Melvor Idle
author: GLADyS

# Sensor config
delivery_pattern: push          # push | poll
source: melvor                  # source string for events
heartbeat_interval_s: 30        # required — dead sensor detection

# Event types (Layer 1 capability suppression)
event_types:
  - type: "game.combat"
    enabled: true
  - type: "game.skill"
    enabled: true
  - type: "game.idle"
    enabled: false              # noisy, not useful yet
```

### 5.2 Forward-looking fields (design for, don't build)

```yaml
# Dependencies — PoC 3 (domain skills)
requires:
  domain_skills: [melvor-domain-skill]

# Resource hints — orchestrator capacity planning
resources:
  memory_mb: 50
  models: []

# Poll config (poll sensors only)
poll_interval_s: 60
```

The orchestrator does not verify `requires` in PoC 2 — domain skills don't exist yet as modular components. The manifest declares them so the structure is ready for PoC 3.

### 5.3 Event type declarations (F-16 Layer 1)

The manifest declares all event types the sensor can produce, with `enabled: true/false` defaults. This is **capability suppression** — disabled types are never emitted. Per-sensor config can override manifest defaults.

This is distinct from flow control (dynamic, automatic) and salience habituation (learned, adaptive). Capability suppression answers: "Can the system even process this event type?" Sound events with no audio preprocessor = useless regardless of volume.

---

## 6. Suppression Architecture

Three layers, each solving a different problem.

| Layer | Where | Type | Mechanism | PoC 2 |
|-------|-------|------|-----------|-------|
| 1. Capability | Sensor manifest | Static, config-driven | `enabled: true/false` per event type | Yes |
| 2. Flow control | Sensor base class | Dynamic, strategy pattern | System-level strategy injected by orchestrator | Strategy exists, starts with "none" |
| 3. Habituation | Salience service | Learned, adaptive | Existing salience model (novelty, habituation dimensions) | Already implemented |

**Layer 1** prevents useless events from ever being emitted. **Layer 2** adapts to system load. **Layer 3** catches remaining redundancy through learned patterns.

---

## 7. Data Classification

### 7.1 Two-bucket event model (F-19)

- **`structured`** (existing): Normal event data. Forwarded everywhere — salience, executive, learning, storage.
- **`evaluation_data`** (new): Optional. Solution/answer data. Stored for learning and evaluation. Stripped by orchestrator before executive sees it. Defense in depth — executive never sees it.

The structure *is* the classification. Sensor developers put data in the right bucket. No per-field annotations or visibility enums.

### 7.2 Event intent routing (F-20)

| Intent | Routing |
|--------|---------|
| `actionable` | Full pipeline: salience → executive → response |
| `informational` | Store as context in memory. Available for retrieval by executive when processing future actionable events. No pipeline routing. |
| `unknown` (default) | Let salience decide. Sensors that haven't classified their events use this. |

### 7.3 Backfill handling (F-21)

`backfill: true` events are stored as context but never routed through the pipeline. The learning system does not treat them as missed response opportunities — GLADyS wasn't active when they occurred. Backfill events should also set `intent: informational`.

---

## 8. PoC 2 Sensor Profiles

All existing sensor code in `packs/sensors/` is exploratory — no design, no spec conformance. All sensors are rewritten from scratch against this architecture. Primary validation target: **1 game sensor + Gmail running simultaneously**.

| Sensor | Pattern | Driver(s) | PoC 2 Role |
|--------|---------|-----------|------------|
| RuneScape | push | Single — Java RuneLite plugin | Game sensor option |
| Melvor Idle | push | Single — browser extension | Game sensor option |
| Sudoku | push | Single — browser extension | Game sensor option |
| Gmail | poll | Multiple — one per email account | Email sensor (non-game) |

### Design characteristics by sensor type

| Characteristic | Game sensors | Email sensor |
|---------------|-------------|-------------|
| Driver management | Single driver, sensor-internal | Multiple driver instances (per account), sensor-internal |
| Delivery | Push (event-driven) | Poll (periodic) |
| Volume | High, bursty | Low, steady |
| Default intent | Mostly `actionable` or `unknown` | Mostly `informational` |
| Emit schedule | Consolidate high-frequency events | Emit on change (new/updated emails) |
| Privacy sensitivity | Low | High |

**Each sensor requires its own design effort before implementation.** The sensor architecture defines the contract and base class; individual sensor designs specify driver integration, event types, emit schedule tuning, domain-specific normalization, and testing strategy.

### Existing assets

- **RuneScape**: Java RuneLite plugin at `src/sensors/runescape/` with 1596 captured test events
- **Melvor**: Exploratory Python sensor at `packs/sensors/melvor-sensor/` (push pattern, HTTP from driver)
- **Sudoku**: Exploratory Python sensor at `packs/sensors/sudoku-sensor/`
- **Gmail**: UC-09 in `docs/design/USE_CASES.md` (email triage use case)

---

## 9. Sensor Dashboard & Control Plane

The dashboard is how developers manage and test the sensor subsystem — not just observation, but active management. Design details in #62.

### Required capabilities

| Capability | Description |
|------------|-------------|
| Register | Add sensors (manifest-driven registration with orchestrator) |
| Activate / Deactivate | Start/stop individual sensors at runtime |
| Observe status | Per-sensor: live / disconnected / error / recovering |
| Metrics | Event throughput, error rates, consolidation ratio, latency |
| Health actions | Trigger recovery, force shutdown |

### Data source

`sensor_metrics` table populated by heartbeat metrics (§3.3). Dashboard queries the table for status and metrics. Orchestrator provides sensor lifecycle actions via gRPC.

### Open design questions (tracked in #62)

- New dashboard tab vs extension of existing Lab tab?
- gRPC API surface for sensor lifecycle management (register, activate, deactivate, recover, shutdown)
- UX for multi-driver sensor visibility (e.g., Gmail showing per-account status)

---

## 10. Failure Modes

### 10.1 Orchestrator unavailable

Sensor base class buffers events locally (§3.5). Bounded buffer, drops least important first (`backfill` → `informational` → `unknown` → `actionable`). Retries with exponential backoff. On reconnect, flushes buffered events.

### 10.2 Orchestrator restart

Sensor registrations persist in DB (§4.3). Orchestrator reads registry on startup. Sensors reconnect via gRPC — the sensor's existing retry/reconnect logic handles this. No re-registration needed.

### 10.3 Driver disconnect

Sensor's internal concern. The sensor reports its own health — if a driver disconnects (game closed, browser tab closed), the sensor's `health()` method reflects that. The sensor may attempt to reconnect, wait for the user to restart the app, or report itself as unhealthy.

### 10.4 Unhealthy sensor

Orchestrator monitors error rate (configurable threshold per time unit). When exceeded: call `recover()` → sensor attempts self-healing (restart driver, clear buffers, reset state) → if still unhealthy → orchestrator shuts down the sensor. Dashboard shows status throughout.

### 10.5 Malformed events

Orchestrator-side concern (orchestrator redesign). Expected behavior: reject malformed events, log the error, increment sensor error count. If error rate exceeds threshold, triggers the unhealthy sensor flow (§10.4).

---

## 11. Event Ordering

Sensors emit events in order within a single source. The orchestrator processes events from different sources concurrently (worker pool, #118) but may process events from the same source concurrently too.

**Per-source ordering is NOT guaranteed by the orchestrator.** Each event is independently scored and processed. The learning module handles temporal context internally (undo detection uses timestamps and recent-fire lookups, not event ordering).

If a future use case requires strict per-source ordering, the orchestrator worker pool can be configured to partition by source. This is not needed for PoC 2.

---

## Proto Changes

New fields on `Event` message in `proto/common.proto`:

```protobuf
message Event {
    // ... existing fields 1-10, 15 ...

    // PoC 2 sensor contract extensions
    string intent = 11;                         // "actionable", "informational", "unknown"
    bool backfill = 12;                         // Pre-existing state dumped on connect
    google.protobuf.Struct evaluation_data = 13; // Solution/cheat data (stripped before executive)
}
```

---

## Out of Scope

- **Streaming delivery pattern** — deferred, not PoC 2
- **Domain skills** — PoC 3. Manifest declares dependencies but verification is not implemented.
- **Preprocessors** — concept exists for future performance/classification needs, not PoC 2
- **Cross-domain interfaces** — interfaces are defined by skill packs, not shared across domains
- **Sensor process management** — orchestrator does not start/stop sensor OS processes in PoC 2. Sensors are started manually or by script.
- **Context-aware cache invalidation** — orchestrator event-response cache uses simple TTL for PoC 2 (F-18)
- **Sensor isolation / fair scheduling** — orchestrator redesign concern, may be PoC 2 or deferred based on orchestrator design session

---

## References

| Source | Sections |
|--------|----------|
| F-01 (source filtering) | §2.5 |
| F-02 (matching quality) | §2.4 |
| F-14 (capture/replay) | §3.2 |
| F-15 (sensor metrics) | §3.3, §5, §9 |
| F-16 (suppression) | §3.4, §5.3, §6 |
| F-18 (event dedup/emit schedule) | §3.6 |
| F-19 (data classification) | §2.2, §7.1 |
| F-20 (intent field) | §2.2, §7.2 |
| F-21 (backfill flag) | §2.2, §7.3 |
| `resource-allocation.md` §Q4 | §2, §2.3, §2.4 |
| `INTERFACES.md` | §3.1, §5 |
| `USE_CASES.md` UC-09 | §8 |
| `sensor-dashboard.md` (#62) | §9 |
| ARCHITECTURE.md | §1.3 |
