# SDK Command Handling Design

**Status**: Design Complete
**Date**: 2026-02-14
**Scope**: Java, JavaScript/TypeScript, Python sensor SDKs

## 1. Executive Summary

GLADyS sensor SDKs handle command dispatch, state management, and orchestrator communication so
sensor developers can focus on domain logic. The design targets **<50 lines** of command handling
code per sensor and **<10 lines** per unit test.

**Design philosophy**: Make sensor development *delightful*, not just possible. Developers should
fall into the pit of success -- correct command handling, state transitions, and error recovery
should be the path of least resistance.

**Key decisions**:

- **Callback/listener pattern** for handler registration (not base class) -- Java single-inheritance
  constraint (RuneLite Plugin) is a hard blocker. Python gets an idiomatic `AdapterBase` that
  delegates to the same dispatcher internally.
- **SDK runs heartbeat in background**, dispatches commands via registered callbacks. Sensor keeps
  control of its own execution.
- **Auto-managed state with escape hatch** -- SDK applies default transitions (START->ACTIVE,
  STOP->STOPPED, etc.). Handler returns `None`/`null` for default, explicit state to override,
  throws to trigger ERROR.
- **Per-command typed args** with `raw()` escape hatch for undocumented fields. Lenient parsing --
  missing/wrong-type returns defaults, never throws.
- **SensorTestHarness** ships in main SDK -- bypasses heartbeat/gRPC, dispatches commands directly.
- **gRPC timeouts enforced by default** per ADR-0005.

## 2. Architecture

### Component Composition

```
Sensor Code (developer writes)
    |
    v
AdapterBase / CommandDispatcher  <-- Handler registration + typed args
    |
    v
SensorLifecycle                  <-- Composes heartbeat + dispatcher + state
    |
    v
HeartbeatManager                 <-- Background heartbeat loop
    |
    v
GladysClient                     <-- gRPC client with TimeoutConfig
    |
    v
Orchestrator (gRPC)
```

### Integration with Existing SDK

The design composes existing components rather than replacing them:

| Component | Status | Changes |
|-----------|--------|---------|
| `GladysClient` | Exists (Java, JS) | Add `TimeoutConfig` constructor parameter |
| `HeartbeatManager` | Exists (Java, JS) | Add `on_command` callback for pending commands |
| `EventBuilder` | Exists (Java, JS) | No changes |
| `CommandDispatcher` | **NEW** | Routes commands to typed handlers |
| `SensorLifecycle` | **NEW** | Composes heartbeat + dispatcher + state |
| `SensorTestHarness` | **NEW** | Test utility (bypasses gRPC) |
| Typed Args classes | **NEW** | `StartArgs`, `StopArgs`, `RecoverArgs`, `HealthCheckArgs` |
| `AdapterBase` | **NEW** (Python only) | Idiomatic base class wrapping dispatcher |

### Command Flow

1. `HeartbeatManager` sends heartbeat on background thread/task
2. `HeartbeatResponse` contains `pending_commands[]`
3. `SensorLifecycle` iterates pending commands, calls `CommandDispatcher.dispatch(cmd, args)`
4. `CommandDispatcher` parses args into typed class, invokes registered handler
5. Handler returns `None`/`null` (default state) or explicit `ComponentState` (override)
6. On exception: SDK catches, sets ERROR by default (HEALTH_CHECK exception: state unchanged)
7. New state + optional `error_message` sent in next heartbeat

### State Transition Defaults

| Command | Default Transition | On Exception |
|---------|-------------------|--------------|
| START | -> ACTIVE | -> ERROR |
| STOP | -> STOPPED | -> ERROR |
| PAUSE | -> PAUSED | -> ERROR |
| RESUME | -> ACTIVE | -> ERROR |
| RELOAD | -> ACTIVE | -> ERROR |
| HEALTH_CHECK | (unchanged) | (unchanged) |
| RECOVER | -> ACTIVE | -> ERROR |

Handler can override any default by returning an explicit `ComponentState`.

### Event Dispatch Strategy

Sensors need configurable event sending. Some sensors (email, simple monitors) send events
immediately. Game sensors (RuneScape 0.6s tick, Melvor, Minecraft) accumulate events during a
processing cycle and send them as a batch. High-threat events may need to bypass the batch queue.

The SDK provides `EventDispatcher` with three modes:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Immediate** | Every `emit()` calls `publish_event()` | Email sensors, low-volume |
| **Scheduled** | Collect events, flush on timer | Game sensors (tick-aligned) |
| **Hybrid** | Scheduled + threat events bypass queue | Game sensors with threat detection |

```
Sensor domain logic
    |
    v
EventDispatcher.emit(event)
    |
    +-- immediate_on_threat && event.is_threat? --> publish_event() now
    |
    +-- flush_interval_ms == 0? --> publish_event() now (immediate mode)
    |
    +-- else --> buffer, flush on timer via publish_events() (scheduled mode)
```

**Configuration** (Python example, same concept in all languages):

```python
# Immediate (default) — every emit() sends immediately
dispatcher = EventDispatcher(client, source="email-sensor-1")

# Scheduled — flush every 600ms (RuneScape game tick)
dispatcher = EventDispatcher(client, source="game-sensor-1",
                             flush_interval_ms=600)

# Hybrid — scheduled + threat bypass (default: immediate_on_threat=True)
dispatcher = EventDispatcher(client, source="game-sensor-1",
                             flush_interval_ms=600,
                             immediate_on_threat=True)
```

**Sensor code is the same regardless of mode**:

```python
event = (EventBuilder(source=self.component_id)
        .text("Player entered PvP zone")
        .structured({"zone": "wilderness", "player": "xyz"})
        .threat(True)  # This triggers immediate send in hybrid mode
        .intent(Intent.ACTIONABLE)
        .build())

await self.events.emit(event)  # Strategy decides: send now or buffer
```

**Manual flush**: Sensors can call `await self.events.flush()` to force-send buffered events
(e.g., in `handle_stop` before shutdown).

**Integration with AdapterBase** (Python):

```python
class GameStateSensor(AdapterBase):
    def __init__(self, ...):
        super().__init__(..., flush_interval_ms=600)
        # self.events is now an EventDispatcher in scheduled mode

    async def handle_stop(self, args: StopArgs) -> Optional[ComponentState]:
        await self.events.flush()  # Send remaining buffered events
        await self.driver.disconnect()
        await self.lifecycle.stop()
        return None
```

## 3. API Specification

### Cross-Language Concept Map

| Concept | Python | Java | JS/TS |
|---------|--------|------|-------|
| **Primary API** | `AdapterBase` (subclass) | `CommandDispatcher.builder()` (composition) | `new CommandDispatcher()` (composition) |
| **Handler registration** | Override `handle_start()`, etc. | `.onStart(args -> ...)` | `.onStart(async (args) => ...)` |
| **Typed handler** | `CommandHandler<T>` (internal) | `CommandHandler<T extends CommandArgs>` | `CommandHandler<TArgs>` |
| **Simple handler** | Method with no args | `SimpleCommandHandler` | `SimpleCommandHandler` |
| **Error handler** | `on_command_error(cmd, ex, state)` | `CommandErrorHandler.handleError(cmd, ex, state)` | `CommandErrorHandler(cmd, err, state)` |
| **Lifecycle** | `SensorLifecycle` (via AdapterBase) | `SensorLifecycle.builder(client, id).build()` | `createSensorLifecycle({...})` |
| **Timeout config** | `TimeoutConfig(publish_event_ms=100, ...)` | `TimeoutConfig.defaults()` / `.builder()` | `DEFAULT_TIMEOUTS` / `NO_TIMEOUT` |
| **Test harness** | `SensorTestHarness(adapter)` | `SensorTestHarness(dispatcher)` | `SensorTestHarness()` |
| **Intent constants** | `Intent.ACTIONABLE` | `Intent.ACTIONABLE` | `Intent.ACTIONABLE` |

### TimeoutConfig (All Languages)

Three fields, same defaults everywhere:

| Field | Default | ADR-0005 Rationale |
|-------|---------|-------------------|
| `publish_event_ms` | 100 | Event publish is fire-and-forget, fast path |
| `heartbeat_ms` | 5000 | Heartbeat includes command delivery |
| `register_ms` | 10000 | Registration is one-time, may involve setup |

Factory: `no_timeout()` / `noTimeout()` / `NO_TIMEOUT` for tests (all values = 0).

### Standard Typed Args

These are the **canonical fields** for each command's typed args class. All languages must
implement these same fields (with language-idiomatic naming). Sensors use `raw(key)` for
additional custom fields.

**StartArgs**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `dry_run` | bool | false | Validate config without starting |

**StopArgs**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `force` | bool | false | Skip graceful shutdown |
| `timeout_ms` | int | 5000 | Shutdown timeout |

**RecoverArgs**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `strategy` | string | "default" | Recovery strategy identifier |

**HealthCheckArgs**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `deep` | bool | false | Perform comprehensive health check |

**PAUSE, RESUME, RELOAD**: No args parameter. Handler signature takes no arguments.

All typed args provide:

- Named accessors (e.g., `args.dry_run`, `args.isDryRun()`, `args.dryRun`)
- `raw(key)` escape hatch for undocumented/sensor-specific fields
- Lenient parsing: missing fields -> defaults, wrong type -> defaults, never throws
- Test factories: `test_defaults()` / `testArgs(...)` / `testDefaults()`

### Language-Specific API Details

Full API specifications with complete class signatures, method docs, and implementation details:

- **Python**: [`efforts/poc2/deliverables/python_sdk_api_spec.md`](../../efforts/poc2/deliverables/python_sdk_api_spec.md)
- **Java**: [`efforts/poc2/deliverables/java_sdk_api_spec.md`](../../efforts/poc2/deliverables/java_sdk_api_spec.md)
- **JS/TS**: [`efforts/poc2/deliverables/jsts_sdk_api_spec.md`](../../efforts/poc2/deliverables/jsts_sdk_api_spec.md)

## 4. Example: Game State Sensor

All three languages implement the same scenario: a game state capture sensor handling all 7
commands with domain-specific logic (driver connection, event publishing, config management).

### Python (Reference Implementation)

```python
class GameStateSensor(AdapterBase):
    """47 lines of command handlers (excluding domain logic)."""

    async def handle_start(self, args: StartArgs) -> Optional[ComponentState]:
        if args.config_override:
            self.config.update(args.config_override)
        self.dry_run_mode = args.dry_run
        await self.driver.connect()
        self.capture_task = asyncio.create_task(self._capture_loop())
        return None  # Default: ACTIVE

    async def handle_stop(self, args: StopArgs) -> Optional[ComponentState]:
        if self.capture_task:
            self.capture_task.cancel()
        if not args.force:
            await asyncio.sleep(0.1)  # Flush
        await self.driver.disconnect()
        await self.lifecycle.stop()
        return None  # Default: STOPPED

    async def handle_pause(self) -> Optional[ComponentState]:
        self.paused = True
        return None  # Default: PAUSED

    async def handle_resume(self) -> Optional[ComponentState]:
        self.paused = False
        return None  # Default: ACTIVE

    async def handle_reload(self) -> Optional[ComponentState]:
        # Re-read config
        return None  # Default: ACTIVE

    async def handle_health_check(self, args: HealthCheckArgs) -> Optional[ComponentState]:
        if args.deep:
            if not await self.driver.ping():
                raise RuntimeError("Driver not responding")
        return None  # State unchanged

    async def handle_recover(self, args: RecoverArgs) -> Optional[ComponentState]:
        await self.driver.restart()
        return None  # Default: ACTIVE
```

### Java

```java
// Extends GamePlugin (proving no-GLADyS-inheritance required)
public class GameStateSensor extends GamePlugin {
    CommandDispatcher dispatcher = CommandDispatcher.builder()
        .onStart(args -> {
            config = GameConfig.load();
            if (args.isDryRun()) return COMPONENT_STATE_STOPPED;
            monitor = new GameStateMonitor(config, this::onGameEvent);
            monitor.start();
            return null; // Default: ACTIVE
        })
        .onStop(args -> {
            if (args.isFlush()) monitor.flushEvents();
            if (args.isForce()) monitor.forceStop();
            else monitor.gracefulStop();
            lifecycle.stop();
            return null; // Default: STOPPED
        })
        .onPause(() -> { paused = true; monitor.pausePublishing(); return null; })
        .onResume(() -> { paused = false; monitor.resumePublishing(); return null; })
        .onReload(() -> { config = GameConfig.load(); monitor.updateConfig(config); return null; })
        .onHealthCheck(args -> {
            if (args.isDeep() && !validateGameConnection())
                throw new IllegalStateException("Game connection failed");
            return null; // State unchanged
        })
        .onRecover(args -> {
            if (monitor != null) monitor.forceStop();
            monitor = new GameStateMonitor(config, this::onGameEvent);
            monitor.start();
            return null; // Default: ACTIVE
        })
        .onCommandError(this::handleCommandError)
        .build();
}
```

### TypeScript

```typescript
const dispatcher = new CommandDispatcher()
  .onStart(async (args) => {
    if (args.dryRun) { await validateGameConfig(); return STARTING; }
    gameState.gameHandle = await attachToGame();
    gameState.isMonitoring = true;
    return null; // Default: ACTIVE
  })
  .onStop(async (args) => {
    if (args.flush) await flushGameEvents(gameState.gameHandle);
    if (args.force) gameState.gameHandle.destroy();
    else await gameState.gameHandle.disconnect();
    gameState.isMonitoring = false;
    return null; // Default: STOPPED
  })
  .onPause(async () => { gameState.isMonitoring = false; })
  .onResume(async () => { gameState.isMonitoring = true; })
  .onReload(async () => { await reloadGameConfig(); })
  .onHealthCheck(async (args) => {
    if (args.deep && !gameState.gameHandle?.isConnected())
      throw new Error("Game connection lost");
  })
  .onRecover(async (args) => {
    if (gameState.gameHandle) await gameState.gameHandle.disconnect();
    gameState.gameHandle = await attachToGame();
    gameState.isMonitoring = true;
  })
  .onCommandError((cmd, err, state) => {
    console.error(`Command ${cmd} failed:`, err.message);
    return null; // Accept ERROR
  });
```

## 5. Testing Strategy

### SensorTestHarness

All three languages ship a `SensorTestHarness` in the SDK's `testing` subpackage. It:

- **Wraps the dispatcher** (or adapter in Python), bypasses HeartbeatManager and gRPC entirely
- **Dispatches commands directly** with typed args or test factories
- **Provides state inspection** (`getState()` / `get_state()`)
- **Provides state setup** (`setState()` / `set_state()`) for test arrangement

### Example Tests (Python)

```python
@pytest.fixture
def harness():
    sensor = GameStateSensor(component_id="test", orchestrator_address="",
                             timeout_config=TimeoutConfig.no_timeout())
    return SensorTestHarness(sensor)

async def test_start_sets_active(harness):
    state, error = await harness.dispatch_start(StartArgs.test_defaults())
    assert state == ComponentState.ACTIVE
    assert error is None

async def test_health_check_failure_preserves_state(harness):
    harness.set_state(ComponentState.ACTIVE)
    harness.adapter.driver.ping = lambda: raise RuntimeError("down")
    state, error = await harness.dispatch_health_check()
    assert state == ComponentState.ACTIVE  # NOT ERROR
    assert "down" in error

async def test_handler_error_sets_error_state(harness):
    harness.adapter.driver.connect = lambda: raise RuntimeError("fail")
    state, error = await harness.dispatch_start()
    assert state == ComponentState.ERROR
```

### Test Arg Factories

Each typed args class provides test factories to eliminate dict-building boilerplate:

| Class | Python | Java | JS/TS |
|-------|--------|------|-------|
| StartArgs | `test_defaults()`, `test_dry_run()` | `testArgs(dryRun)` | `testDefaults()`, `testDryRun()` |
| StopArgs | `test_defaults()`, `test_force()` | `testArgs(force, flush)` | `testDefaults()`, `testForce()` |
| RecoverArgs | `test_defaults()` | `testArgs(strategy)` | `testDefaults()` |
| HealthCheckArgs | `test_defaults()` | `testArgs(deep)` | `testDefaults()` |

## 6. Migration Guide

**No migration needed.** The only sensor PR (#158) was rejected and will be rewritten with the new
SDK. Archived exploratory sensors are throwaway code. All sensors will be written fresh against
the new SDK API.

For reference, the migration from raw proto handling to SDK is:

| Before (raw proto) | After (SDK) |
|---------------------|-------------|
| Manual `if/elif` dispatch chain | Register typed handlers |
| Manual `self.current_state = ...` | SDK auto-manages state |
| No error handling pattern | SDK catches + ERROR state + global callback |
| No test support | `SensorTestHarness` + test factories |
| Manual heartbeat loop | `SensorLifecycle` composes it |

## 7. Proto Changes Required

### `error_message` field on HeartbeatRequest

```protobuf
message HeartbeatRequest {
    string component_id = 1;
    ComponentState state = 2;
    string error_message = 3;  // NEW: Populated by SDK on command failure
    RequestMetadata metadata = 15;
}
```

SDK populates this when a command handler throws an exception. Orchestrator logs/displays the
error. Field is empty on successful heartbeats. This enables the dashboard to show why a sensor
entered ERROR state.

## 8. Open Questions

### Resolved (Deferred to Implementation)

1. **Arg field details**: Cross-language review found field divergences in the language-specific
   specs (Python has richer fields than Java/JS). The canonical fields are defined in Section 3
   above. Language specs will be updated to match during implementation.

2. **Lenient parsing edge cases**: What happens if `dry_run` is string `"true"` or number `1`?
   Decision: coerce where reasonable (string "true" -> true, number 1 -> true), otherwise use
   default. Exact behavior documented per-language during implementation.

### Future Enhancements (Not in PoC 2)

1. **Command acknowledgment**: Explicit ack/nack to orchestrator per command (currently implicit
   via state change in next heartbeat)
2. **Command queuing**: Client-side command queue for offline/disconnected sensors
3. **Middleware pattern**: Pre/post command hooks for logging, metrics, tracing
4. **Schema validation**: Validate args against declared schema at dispatch time

## References

- **Proto definitions**: `proto/orchestrator.proto` (Command enum, PendingCommand, HeartbeatResponse)
- **Sensor control protocol**: `docs/codebase/SENSOR_CONTROL.md`
- **Sensor architecture**: `docs/design/SENSOR_ARCHITECTURE.md`
- **ADR-0005**: gRPC timeout defaults
- **Cross-language review**: `efforts/poc2/deliverables/cross_language_review.md`
