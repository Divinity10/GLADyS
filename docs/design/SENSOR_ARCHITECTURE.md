# Sensor Architecture

**Status**: Proposed
**Date**: 2026-02-07 (updated 2026-02-07 with review feedback)
**Issue**: #143
**Phase Scope**: Phase 2 (Multi-Sensor Pipeline)
**Informed by**: Phase 1 findings F-14, F-15, F-16, F-18, F-19, F-20, F-21

## Purpose

Define the architecture for GLADyS sensors — components that capture events from external applications and deliver them to the orchestrator as normalized GLADyS events. This doc covers the sensor protocol, language-specific SDKs, event contract extensions, and Phase 2 sensor profiles.

Sensors are one component of a **skill pack** (sensor + domain skill + heuristics). This doc covers the sensor layer only. Domain skills are a separate concern (Phase 3).

---

## 1. Architecture: Driver / Adapter / Orchestrator

Three-layer pipeline with clear boundaries.

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     native      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     gRPC        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  Driver   â”‚ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–º â”‚  Adapter  â”‚ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–º â”‚ Orchestrator â”‚
â”‚ (polyglot)â”‚   transport     â”‚ (polyglot)â”‚  PublishEvent(s)â”‚              â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 App-specific                 Normalizes                    Routes, stores,
 event capture                to GLADyS                     processes
                              event contract
```

### 1.1 Driver (polyglot, lightweight)

- Runs inside or alongside the target application
- Language = whatever the app requires (Java for RuneLite, browser extension for web apps, etc.)
- Responsibilities: capture app events, send to adapter via native transport (HTTP, WebSocket, file, etc.)
- Does NOT normalize, classify, or filter — that's the adapter's job
- Reports driver-level metrics to adapter (events handled, dropped, errors)
- **Drivers are a sensor concern, not a GLADyS concern.** Each sensor decides the best way to collect data from its target.

#### Browser extension drivers

Browser extensions push data outward — external processes cannot reach into an extension. Communication patterns:
- **HTTP push**: Extension POSTs to adapter's local HTTP endpoint (simplest, used by existing Melvor exploratory code)
- **WebSocket**: Extension opens persistent connection to adapter. Enables bidirectional communication — adapter can request "check now" for poll-pattern adapter.

The adapter cannot poll a browser extension. For poll-pattern adapter using browser extensions (e.g., Gmail), the extension handles polling internally and pushes results to the adapter.

### 1.2 Adapter (polyglot, protocol-driven)

- Receives raw driver data, normalizes to GLADyS event contract
- Implements the **sensor protocol** (Â§3) — language-agnostic contract
- Manages its own emit schedule (rate control independent of driver event rate)
- Publishes normalized events to orchestrator via gRPC `PublishEvent` / `PublishEvents`
- How the adapter manages its driver(s) is an internal implementation detail. A game adapter may have one driver; an email adapter may manage multiple driver instances (one per account).

**Language choice**: adapter may be written in any language that can implement the protocol. When driver and adapter share a language, they can use native calls instead of IPC — eliminating a serialization boundary. Python, Java, and JavaScript/TypeScript SDKs are provided for Phase 2 (Â§3.3).

### 1.3 Orchestrator interface

- `PublishEvent` — single event gRPC call
- `PublishEvents` — batch gRPC call (repeated Event). For high-volume sensors (e.g., RuneScape: 100+ events per tick). Sensor chooses which to use based on volume.
- `RegisterComponent` for sensor registration
- `system.metrics` events routed to system handlers, not salience pipeline
- Orchestrator sees one sensor (the adapter), not individual drivers — the adapter abstracts its driver topology

### 1.4 Remote sensors (future consideration)

Phase 2 sensors are all local (same machine as orchestrator). Future sensors may run on phones, other network devices, or remote computers. Remote sensors raise connectivity questions:
- Push from remote sensor requires network path to orchestrator (NAT traversal, VPN, relay)
- Orchestrator polling remote sensor has the same NAT problem in reverse

**Phase 2 approach**: Push only, local only. The design does not preclude remote sensors but does not engineer for them. When remote sensors become a need, the solution likely involves a relay or message broker.

**Polling stub concept** (noted, YAGNI): A remote sensor could provide an installable local module that runs alongside the orchestrator, handling the remote communication. The orchestrator polls the local stub; the stub communicates with the remote sensor. Not designed or built — noted for future reference.

---

## 2. Event Contract

The GLADyS event contract defines what a sensor produces. The current `Event` message in `proto/common.proto` (fields 1-10, 15) is the base. Phase 2 adds two new fields.

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

### 2.2 New fields (Phase 2)

| Field | Proto field # | Type | Default | Source |
|-------|--------------|------|---------|--------|
| `intent` | 11 | enum: `actionable`, `informational`, `unknown` | `unknown` | F-20 |
| `evaluation_data` | 12 | Struct | empty | F-19 |

**`intent`** — Routing hint from the adapter. The adapter knows best whether an event expects a response.

| Intent | Routing |
|--------|---------|
| `actionable` | Full pipeline: salience → executive → response |
| `informational` | Store as context in memory. Available for retrieval by executive when processing future actionable events. No pipeline routing. |
| `unknown` (default) | Let salience decide. Adapters that haven't classified their events use this. |

**Note**: `backfill` (F-21: pre-existing state dumped on connect) is deferred. If needed, it can be added as a fourth intent value (`intent: backfill`) which would route identically to `informational` with additional semantics: timestamps may be inaccurate, not a missed learning opportunity.

**`evaluation_data`** — Optional second data bucket for solution/cheat data. Stored for learning and evaluation, stripped by orchestrator before executive sees it. Example: Sudoku solution visible in DOM — useful for evaluating response quality but must not appear in responses. The structure *is* the classification — sensor developers put data in the right bucket.

### 2.2.1 Future field: Urgency metadata

*Not implemented in Phase 2. Design direction captured in [urgency-selection.md](questions/urgency-selection.md).*

Sensors are domain experts — they know whether an event needs immediate response (combat health critical) or can wait (newsletter arrived). A future `urgency` field would allow sensors to provide domain-specific urgency hints that the orchestrator uses to modulate heuristic selection strategy (cache-first vs DB-query vs LLM-preferred).

Urgency is domain-specific: real-time games need sub-second response, email sensors can wait minutes. The sensor's urgency hint combined with the salience threat score provides "cheap" urgency for routing decisions before the executive's domain skill does deeper assessment.

**Phase 2 approach**: No urgency field. All events use the default path. The design accommodates urgency without requiring it.

### 2.3 Delivery patterns

Two patterns for Phase 2 (streaming deferred):

| Pattern | How it works | Examples | Volume profile |
|---------|-------------|----------|---------------|
| Push (`event`) | Driver sends events when things happen | Game combat, game state changes | Bursty — zero to hundreds/sec |
| Poll | Adapter periodically checks state | Email check, system monitor | Steady — configurable interval |

Each pattern has different volume management characteristics. The `structured` field carries delivery-pattern-specific attributes when needed (e.g., `poll_interval` for poll sensors).

### 2.4 Domain interfaces

- Domain-specific payload lives in the `structured` field (JSON)
- Interfaces are defined by the skill pack, not by GLADyS core
- Sub-interfaces conditional on domain field values (e.g., `damage_type: "fire"` implies `damage_per_tick`, `duration` fields)
- `raw_text` best practice: natural-language sentences describing the event, not key-value dumps (F-02). "The player took 15 fire damage" not "damage_type=fire damage=15"

### 2.5 Source semantics

- Adapter decides the source string per event
- Flat string sufficient for Phase 2
- Used as hard filter in heuristic matching (F-01) — prevents cross-domain false matches
- Multi-driver sensors may differentiate source per driver instance or use a shared source — sensor's decision

---

## 3. Sensor Protocol & SDKs

The sensor architecture is defined as a **protocol** (language-agnostic contract) with per-language **SDKs** as convenience implementations.

### 3.1 Sensor Protocol (language-agnostic)

Every adapter, regardless of implementation language, must:

1. **Register** with the orchestrator via `RegisterComponent` gRPC
2. **Publish events** via `PublishEvent` (single) or `PublishEvents` (batch) gRPC
3. **Emit heartbeats** as `system.metrics` events at the declared `heartbeat_interval_s`
4. **Report health** when queried by orchestrator
5. **Attempt recovery** when orchestrator calls `recover()`
6. **Support capture/replay** — write JSONL at two boundaries (driver→adapter raw, adapter→orchestrator normalized)
7. **Enforce flow control** — accept strategy configuration from orchestrator at registration, execute locally

The protocol is defined by the gRPC service contract and the JSONL capture format. Any language that can do gRPC can implement an adapter.

### 3.2 Protocol Interface

```
Sensor Protocol:
    start()                    → Begin sensing
    stop()                     → Stop sensing, flush buffers
    health() → SensorHealth    → Report current health
    recover() → bool           → Attempt self-healing (True=recovered, False=shutdown needed)
    emit_events() → Event[]    → Produce normalized events
    start_capture(boundary, max_duration?, max_count?) → Begin JSONL capture
    stop_capture(boundary)     → Stop JSONL capture, flush file
```

Flow control is **configuration-injected**, not code-injected. At registration, the orchestrator sends: strategy name + parameters (e.g., `{ strategy: "rate_limiter", max_events_per_sec: 100 }`). Each language SDK implements the named strategies locally. This works across process and language boundaries — the orchestrator injects configuration, adapters execute the behavior locally.

### 3.3 Language SDKs (Phase 2)

| SDK | Language | Covers | Scope |
|-----|----------|--------|-------|
| **Python SDK** | Python | Generic adapters, reference implementation | Full base class with capture/replay, metrics, flow control, buffering. Adapters extend and get infrastructure for free. |
| **JavaScript/TypeScript SDK** | JS/TS | Browser extension drivers (Melvor, Sudoku, Gmail) | Lightweight library: gRPC publish client (or HTTP-to-gRPC proxy — browser extensions can't do gRPC directly), metrics helpers, JSONL capture. |
| **Java SDK** | Java | RuneScape (RuneLite plugin) | Lightweight library: gRPC publish client, metrics helpers, JSONL capture. |

**Why per-language SDKs, not per-language base classes?** Base classes are inheritance-based and don't translate well across languages. SDKs provide composable helpers. The Python SDK uses a base class because Python adapters benefit from it (multiple potential generic adapters). The JS and Java SDKs are libraries, not base classes.

**Browser extension limitation**: Browser extensions cannot make gRPC calls (no HTTP/2 client-initiated connections). Browser-based sensors need either:
- A local HTTP endpoint on the orchestrator (REST alongside gRPC)
- A thin local HTTP-to-gRPC proxy

This is a shared concern for the three browser-based Phase 2 sensors (Melvor, Sudoku, Gmail). The JS/TS SDK should handle this transparently.

### 3.4 Python Base Class

The Python SDK provides a full base class. Adapters extend it and implement domain-specific logic only.

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class AdapterBase(ABC):
    """Base class for Python GLADyS adapters."""

    # --- Lifecycle (adapter implements) ---

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter. Connect to driver(s), begin event collection."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter. Disconnect from driver(s), flush buffers."""
        ...

    @abstractmethod
    async def health(self) -> AdapterHealth:
        """Report adapter health status."""
        ...

    @abstractmethod
    async def recover(self) -> bool:
        """Orchestrator requests self-healing.

        Called when the orchestrator detects the adapter is unhealthy.
        Adapter decides what to do: restart driver, clear buffers, etc.
        Returns True if recovery succeeded, False if shutdown needed.
        """
        ...

    # --- Event production (adapter implements) ---

    @abstractmethod
    async def emit_events(self) -> AsyncIterator[Event]:
        """Yield normalized GLADyS events.

        The adapter controls its own emit cadence — it may buffer
        driver events and consolidate them before yielding.
        """
        ...

    # --- Provided by base class (adapter does NOT override) ---

    # Capture/replay (Â§4)
    # Metrics collection (Â§5)
    # Flow control enforcement (Â§6)
    # Event buffering during orchestrator outage (Â§7)
    # Publish to orchestrator via gRPC (PublishEvent / PublishEvents)
    # Dry-run mode (capture without publishing)
```

---

## 4. Capture / Replay

Protocol-level feature — all SDKs implement it. Two capture boundaries, both JSONL.

**Boundary 1: Driver → Adapter (raw)**
Captures what the driver sends before the adapter normalizes it. Enables adapter development without the target application running.

**Boundary 2: Adapter → Orchestrator (normalized)**
Captures the normalized GLADyS events the adapter publishes. Enables orchestrator/pipeline testing without live sensors.

| Aspect | Design |
|--------|--------|
| Format | JSONL — one record per line, each with capture timestamp. Appendable, crash-safe, streamable. |
| Stop conditions | Time-based (`--capture-duration`) OR record-count (`--capture-count`), whichever hits first. |
| Replay timing | Preserves original inter-event deltas. Optional `--replay-speed` multiplier (2x, 10x, etc.). No "instant dump" default — flooding the orchestrator produces unrealistic test results. |
| Multi-driver | Capture tags each record with driver instance ID (sensor's concern). |
| Who captures | Adapter's ingestion layer, not the driver. Drivers stay lightweight. |
| Dry-run mode | `--dry-run`: capture without publishing to orchestrator. Enables testing sensors in isolation. |

### Activation

**Capture** supports both startup and runtime activation:
- **CLI flags** (`--capture-duration`, `--capture-count`): Start capturing at sensor launch. Good for planned recording sessions.
- **Runtime toggle** (`start_capture()` / `stop_capture()`): Protocol methods callable at any time. Enables "something weird is happening, start recording" without restarting the sensor. Dashboard control plane can invoke these via the orchestrator. `start_capture` accepts optional `max_duration` and `max_count` stop conditions (same as CLI). If neither is specified, a configurable default max duration applies (e.g., 30 minutes) to prevent unbounded capture.

**Replay** is CLI-only (`--replay <file>`, `--replay-speed <multiplier>`). Replay replaces live driver input — it's a fundamentally different operating mode, not something you toggle mid-session.

**Dry-run** is CLI-only (`--dry-run`). Runs the adapter without an orchestrator connection.

---

## 5. Metrics

All SDKs implement metrics collection. Emitted as `system.metrics` events via `PublishEvent` on a configurable heartbeat interval.

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

**Driver-level metrics** (driver reports to adapter, adapter aggregates):

| Metric | Type | Description |
|--------|------|-------------|
| `driver.events_handled` | counter | App events the driver captured |
| `driver.events_dropped` | counter | App events the driver couldn't capture |
| `driver.errors` | counter | Driver-side errors |
| `driver.last_report_at` | timestamp | Last time driver sent metrics |

Driver metrics stored as JSONB since different drivers report different things.

**Heartbeat**: Configurable `heartbeat_interval_s` (declared in manifest). Dead sensor detection: no heartbeat within 2x interval = presumed dead. Orchestrator monitors this.

**Persistence**: Orchestrator writes metrics to `sensor_metrics` table (one row per heartbeat push, rolling retention).

---

## 6. Flow Control

**System-level strategy pattern.** The orchestrator sends flow control configuration to the adapter at registration time. All adapters use the same strategy — adapters do not choose whether to participate.

**Configuration injection** (not code injection): The orchestrator sends a strategy name and parameters. Each language SDK implements the named strategies locally. Example: `{ strategy: "rate_limiter", max_events_per_sec: 100 }` or `{ strategy: "none" }`.

The SDK calls the strategy before every publish. If the strategy says "don't publish," the event is buffered (and may be dropped per buffer policy — see Â§7).

**Phase 2**: Start with `strategy: "none"` (all publishes allowed). The pattern exists in all SDKs so strategies can be added later without changing adapters.

**Future (Phase 3+)**: BBR-inspired strategy that tracks `PublishEvent(s)` response latency. Latency increase → reduce publish rate. Return to baseline → increase rate.

---

## 7. Event Buffering (Orchestrator Unavailable)

When the orchestrator is unreachable, the SDK buffers events locally.

| Aspect | Design |
|--------|--------|
| Buffer | Bounded in-memory queue (configurable max size) |
| Drop policy | When buffer is full, drop least important first: `informational` → `unknown` → `actionable` |
| Reconnect | Retry with exponential backoff |
| Flush | On reconnect, publish buffered events in order. Events that aged beyond a configurable TTL are dropped. |

All SDKs implement this. Adapters do not implement their own buffering.

---

## 8. Emit Schedule

The adapter controls its own emit cadence, independent of the driver's event rate. The adapter buffers driver events and emits consolidated events on a timer or on meaningful change (domain-specific). This is rate control — the adapter decides *how often* to emit, not *what* to emit.

Example: Driver fires position every 600ms. Adapter emits position every 5s unless movement exceeds a threshold.

The SDK tracks `events_received` vs `events_published` for the consolidation ratio metric.

---

## 9. Sensor Lifecycle

### 9.1 Three-fold lifecycle

| Concern | What it means | Phase 2 approach |
|---------|--------------|----------------|
| **Install** | Sensor code + manifest in place, prereqs declared | Dashboard triggers registration with orchestrator. Sensor processes started manually or by script. |
| **Awareness** | Orchestrator knows about sensor, subscribes to metrics | `RegisterComponent` gRPC + DB persistence. Orchestrator reads registry on startup. |
| **Health** | Orchestrator monitors heartbeats, can recover or stop unhealthy sensors | Heartbeat monitoring (2x interval = dead). Error-rate threshold triggers `recover()` → if still unhealthy → shutdown. |

### 9.2 Orchestrator health management

The orchestrator monitors sensor health via the `system.metrics` heartbeat events:

1. **Heartbeat timeout**: No heartbeat within 2x `heartbeat_interval_s` → sensor presumed dead. Orchestrator updates status, dashboard shows disconnected.
2. **Error rate threshold**: Configurable error events per time unit. When exceeded, orchestrator calls `recover()` on the sensor.
3. **Recovery flow**: `recover()` returns `True` (sensor fixed itself) or `False` (needs shutdown). If `True`, orchestrator resets the error counter and resumes monitoring. If `False` or still unhealthy after a grace period, orchestrator stops the sensor.
4. **Manual control**: Dashboard can activate/deactivate sensors via orchestrator (sends stop/start signals).

### 9.3 Registration persistence

Sensor registrations persist in a DB table so the orchestrator knows what sensors exist across restarts. The table stores: sensor ID, manifest data, status (active/inactive/error), last seen timestamp. The orchestrator reads this on startup — it doesn't need sensors to re-register after an orchestrator restart.

---

## 10. Manifest

The sensor manifest declares sensor identity, capabilities, and dependencies. For Phase 2, the manifest drives registration and documentation. Specific fields will be finalized during the orchestrator redesign.

### 10.1 Established fields

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

### 10.2 Forward-looking fields (design for, don't build)

```yaml
# Dependencies — Phase 3 (domain skills)
requires:
  domain_skills: [melvor-domain-skill]

# Resource hints — orchestrator capacity planning
resources:
  memory_mb: 50
  models: []

# Poll config (poll sensors only)
poll_interval_s: 60
```

The orchestrator does not verify `requires` in Phase 2 — domain skills don't exist yet as modular components. The manifest declares them so the structure is ready for Phase 3.

### 10.3 Event type declarations (F-16 Layer 1)

The manifest declares all event types the sensor can produce, with `enabled: true/false` defaults. This is **capability suppression** — disabled types are never emitted. Per-sensor config can override manifest defaults.

This is distinct from flow control (dynamic, automatic) and salience habituation (learned, adaptive). Capability suppression answers: "Can the system even process this event type?"

---

## 11. Suppression Architecture

Three layers, each solving a different problem.

| Layer | Where | Type | Mechanism | Phase 2 |
|-------|-------|------|-----------|-------|
| 1. Capability | Sensor manifest | Static, config-driven | `enabled: true/false` per event type | Yes |
| 2. Flow control | Sensor SDK | Dynamic, strategy pattern | System-level strategy, config-injected by orchestrator | Strategy exists, starts with "none" |
| 3. Habituation | Salience service | Learned, adaptive | Existing salience model (novelty, habituation dimensions) | Already implemented |

**Layer 1** prevents useless events from ever being emitted. **Layer 2** adapts to system load. **Layer 3** catches remaining redundancy through learned patterns.

---

## 12. Phase 2 Sensor Profiles

All existing sensor code in `packs/sensors/` is exploratory — no design, no spec conformance. All sensors are rewritten from scratch against this architecture. Primary validation target: **1 game sensor + Gmail running simultaneously**.

| Sensor | Pattern | Driver(s) | Language | Phase 2 Role |
|--------|---------|-----------|----------|------------|
| RuneScape | push | Single — Java RuneLite plugin | Java (driver+adapter) | Game sensor option |
| Melvor Idle | push | Single — browser extension | JS/TS (extension) + Python or JS adapter | Game sensor option |
| Sudoku | push | Single — browser extension | JS/TS (extension) + Python or JS adapter | Game sensor option |
| Gmail | poll | Multiple — one per email account | JS/TS (extension) + Python or JS adapter | Email sensor (non-game) |

### Design characteristics by sensor type

| Characteristic | Game sensors | Email sensor |
|---------------|-------------|-------------|
| Driver management | Single driver, sensor-internal | Multiple driver instances (per account), sensor-internal |
| Delivery | Push (event-driven) | Poll (periodic, extension polls internally and pushes to adapter) |
| Volume | High, bursty | Low, steady |
| Default intent | Mostly `actionable` or `unknown` | Mostly `informational` |
| Emit schedule | Consolidate high-frequency events | Emit on change (new/updated emails) |
| Privacy sensitivity | Low | High |

**Each sensor requires its own design effort before implementation.** The sensor architecture defines the protocol and SDKs; individual sensor designs specify driver integration, event types, emit schedule tuning, domain-specific normalization, and testing strategy.

### Existing assets

- **RuneScape**: Java RuneLite plugin at `src/sensors/runescape/` with 1596 captured test events
- **Melvor**: Exploratory Python sensor at `packs/sensors/melvor-sensor/` (push pattern, HTTP from driver)
- **Sudoku**: Exploratory Python sensor at `packs/sensors/sudoku-sensor/`
- **Gmail**: UC-09 in `docs/design/USE_CASES.md` (email triage use case)

---

## 13. Sensor Dashboard & Control Plane

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

`sensor_metrics` table populated by heartbeat metrics (Â§5). Dashboard queries the table for status and metrics. Orchestrator provides sensor lifecycle actions via gRPC.

### Open design questions (tracked in #62)

- New dashboard tab vs extension of existing Lab tab?
- gRPC API surface for sensor lifecycle management (register, activate, deactivate, recover, shutdown)
- UX for multi-driver sensor visibility (e.g., Gmail showing per-account status)

---

## 14. Failure Modes

### 14.1 Orchestrator unavailable

Sensor SDK buffers events locally (Â§7). Bounded buffer, drops least important first (`informational` → `unknown` → `actionable`). Retries with exponential backoff. On reconnect, flushes buffered events.

### 14.2 Orchestrator restart

Sensor registrations persist in DB (Â§9.3). Orchestrator reads registry on startup. Sensors reconnect via gRPC — the sensor's existing retry/reconnect logic handles this. No re-registration needed.

### 14.3 Driver disconnect

Sensor's internal concern. The sensor reports its own health — if a driver disconnects (game closed, browser tab closed), the sensor's `health()` method reflects that. The sensor may attempt to reconnect, wait for the user to restart the app, or report itself as unhealthy.

### 14.4 Unhealthy sensor

Orchestrator monitors error rate (configurable threshold per time unit). When exceeded: call `recover()` → sensor attempts self-healing (restart driver, clear buffers, reset state) → if still unhealthy → orchestrator shuts down the sensor. Dashboard shows status throughout.

### 14.5 Malformed events

Orchestrator-side concern (orchestrator redesign). Expected behavior: reject malformed events, log the error, increment sensor error count. If error rate exceeds threshold, triggers the unhealthy sensor flow (Â§14.4).

---

## 15. Event Ordering

Sensors emit events in order within a single source. The orchestrator processes events from different sources concurrently (worker pool, #118) but may process events from the same source concurrently too.

**Per-source ordering is NOT guaranteed by the orchestrator.** Each event is independently scored and processed. The learning module handles temporal context internally (undo detection uses timestamps and recent-fire lookups, not event ordering).

If a future use case requires strict per-source ordering, the orchestrator worker pool can be configured to partition by source. This is not needed for Phase 2.

---

## Proto Changes

New fields on `Event` message in `proto/common.proto`:

```protobuf
message Event {
    // ... existing fields 1-10, 15 ...

    // Phase 2 sensor contract extensions
    string intent = 11;                         // "actionable", "informational", "unknown"
    google.protobuf.Struct evaluation_data = 12; // Solution/cheat data (stripped before executive)
}
```

New gRPC methods on orchestrator service:

```protobuf
// Single event publish
rpc PublishEvent(PublishEventRequest) returns (PublishEventResponse);

// Batch event publish (high-volume sensors)
rpc PublishEvents(PublishEventsRequest) returns (PublishEventsResponse);

message PublishEventsRequest {
    repeated Event events = 1;
    RequestMetadata metadata = 2;
}
```

---

## Out of Scope

- **Streaming delivery pattern** — deferred, not Phase 2
- **Domain skills** — Phase 3. Manifest declares dependencies but verification is not implemented.
- **Preprocessors** — concept exists for future performance/classification needs, not Phase 2
- **Cross-domain interfaces** — interfaces are defined by skill packs, not shared across domains
- **Sensor process management** — orchestrator does not start/stop sensor OS processes in Phase 2. Sensors are started manually or by script.
- **Context-aware cache invalidation** — orchestrator event-response cache uses simple TTL for Phase 2 (F-18)
- **Sensor isolation / fair scheduling** — orchestrator redesign concern, may be Phase 2 or deferred
- **Remote sensors** — local-only for Phase 2. Polling stub concept noted but not designed.
- **Backfill flag** — deferred. Can be added as `intent: backfill` when needed.

---

## References

| Source | Sections |
|--------|----------|
| F-01 (source filtering) | Â§2.5 |
| F-02 (matching quality) | Â§2.4 |
| F-14 (capture/replay) | Â§4 |
| F-15 (sensor metrics) | Â§5, Â§10, Â§13 |
| F-16 (suppression) | Â§6, Â§10.3, Â§11 |
| F-18 (event dedup/emit schedule) | Â§8 |
| F-19 (data classification) | Â§2.2 |
| F-20 (intent field) | Â§2.2 |
| F-21 (backfill flag) | Â§2.2 (deferred) |
| `resource-allocation.md` Â§Q4 | Â§1, Â§2.3, Â§2.4 |
| `INTERFACES.md` | Â§3.4, Â§10 |
| `USE_CASES.md` UC-09 | Â§12 |
| `sensor-dashboard.md` (#62) | Â§13 |
| ARCHITECTURE.md | Â§1.3 |


