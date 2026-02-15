# GLADyS Python Sensor SDK

Async Python client library for building GLADyS sensors. Provides adapter
infrastructure (gRPC client, heartbeat, event builder, registration, lifecycle
management) so sensor developers focus on driver integration and domain-specific
normalization. Requires Python 3.11+.

**Terminology**: A sensor is a bundle of driver (captures from app) + adapter
(normalizes and publishes to orchestrator). This SDK provides the adapter half.

## Prerequisites

- Python 3.11+
- uv (recommended) or pip
- Proto files in `proto/` at the project root (referenced via `../../../proto`)

## Setup

```bash
uv sync --all-extras
```

Or with pip:

```bash
pip install -e ".[dev]"
```

## Test

```bash
pytest
```

Tests use pytest with pytest-asyncio (`asyncio_mode = "auto"`).

## API Overview

### GladysClient

Async gRPC client wrapping the `OrchestratorService` stub. All methods are
`async`. Accepts an address string and optional `TimeoutConfig`.

```python
from gladys_sensor_sdk import GladysClient, ComponentState, TimeoutConfig

client = GladysClient("localhost:50051")
await client.connect()

# Publish a single event
ack = await client.publish_event(event)

# Publish a batch of events
acks = await client.publish_events([event1, event2])

# Register as a sensor
resp = await client.register_component("my-sensor", "sensor.game")

# Send heartbeat
hb = await client.heartbeat("my-sensor", ComponentState.ACTIVE)

# Heartbeat with error message
hb = await client.heartbeat("my-sensor", ComponentState.ERROR, "connection lost")

# Cleanup
await client.close()
```

### EventBuilder

Fluent builder for `Event` messages. Populates adapter-responsibility fields
(id, timestamp, source, raw_text, structured, intent, evaluation_data).
Fields populated downstream (salience, entity_ids) are left at defaults.

```python
from gladys_sensor_sdk import EventBuilder, Intent

event = (
    EventBuilder("my-sensor")
    .text("Player health dropped to 3 hearts")
    .structured({"health": 3, "max_health": 20})
    .intent(Intent.ACTIONABLE)
    .evaluation_data({"threshold": 0.2})
    .build()
)
```

Each call to `build()` generates a unique event ID and timestamp automatically.
Use `.threat()` to mark events that bypass habituation in hybrid dispatch mode.

### HeartbeatManager

Background heartbeat sender using `asyncio.create_task`. Sends periodic
heartbeats to the orchestrator and dispatches pending commands via an async
callback.

```python
from gladys_sensor_sdk import GladysClient
from gladys_sensor_sdk.heartbeat import HeartbeatManager
from gladys_sensor_sdk import ComponentState

hb = HeartbeatManager(client, "my-sensor", interval_seconds=30.0)
await hb.start()

# Change reported state (e.g., when pausing)
hb.set_state(ComponentState.PAUSED)

# On shutdown
await hb.stop()
```

Heartbeat errors are logged and swallowed so a transient network failure does
not crash the sensor.

### SensorRegistration

Static async one-shot helper for registering a sensor without full adapter
lifecycle.

```python
from gladys_sensor_sdk import SensorRegistration

resp = await SensorRegistration.register(
    component_id="my-sensor",
    component_type="sensor.game",
    orchestrator_address="localhost:50051",
    capabilities={"transport_mode": "event"},
)
```

### EventDispatcher

Configurable event dispatch with three modes: immediate (default), scheduled
(buffer + timer flush), and hybrid (scheduled + threat bypass).

```python
from gladys_sensor_sdk import EventDispatcher, RateLimitStrategy

# Immediate mode (default) -- every emit sends now
events = EventDispatcher(client, source="my-sensor")

# Scheduled mode (600ms flush interval)
events = EventDispatcher(client, source="my-sensor", flush_interval_ms=600)
await events.start()

# With flow control strategy
events = EventDispatcher(
    client, source="my-sensor",
    strategy=RateLimitStrategy(100, 60),
)

# Single event -- returns True if published, False if suppressed
sent = await events.emit(event)

# Batch with selective filtering
result = await events.emit_batch(event_list)
# result.sent + result.suppressed == len(event_list)

# Metrics
events.events_published
events.events_filtered

# Shutdown (flushes remaining buffer)
await events.stop()
```

### CommandDispatcher

Internal command router composed by `SensorLifecycle`. Routes incoming commands
from heartbeat responses to registered handlers and manages state transitions.
Sensor developers interact with commands by overriding `AdapterBase` handler
methods rather than using `CommandDispatcher` directly.

```python
from gladys_sensor_sdk.dispatcher import CommandDispatcher
from gladys_sensor_sdk import Command, ComponentState

dispatcher = CommandDispatcher(component_id="my-sensor")
dispatcher.register_handler(Command.START, handle_start)
dispatcher.register_handler(Command.STOP, handle_stop)

# Dispatch returns (new_state, error_message)
new_state, error = await dispatcher.dispatch(Command.START, args_dict={"dry_run": False})
```

### FlowStrategy

Pluggable rate limiting for event emission. The SDK ships `NoOpStrategy`
(passthrough) and `RateLimitStrategy` (token bucket).

```python
from gladys_sensor_sdk import RateLimitStrategy, create_strategy

# Token bucket: 100 events per 60-second window
strategy = RateLimitStrategy(100, 60)

# From orchestrator config
strategy = create_strategy({"strategy": "rate_limit", "max_events": 100, "window_seconds": 60})

# Hot-swap at runtime
events.set_strategy(strategy)
```

### AdapterBase

Primary developer-facing API. Subclass `AdapterBase` and override command
handlers. The SDK handles client setup, registration, heartbeat, event
dispatch, and state transitions automatically.

```python
from gladys_sensor_sdk import AdapterBase, EventBuilder, Intent
from gladys_sensor_sdk import StartArgs, StopArgs, ComponentState

class GameSensor(AdapterBase):
    async def handle_start(self, args: StartArgs) -> ComponentState | None:
        # Connect to game, start capturing events
        return None  # Accept default ACTIVE state

    async def handle_stop(self, args: StopArgs) -> ComponentState | None:
        # Disconnect from game
        return None  # Accept default STOPPED state

sensor = GameSensor(
    component_id="my-sensor",
    component_type="sensor.game",
    orchestrator_address="localhost:50051",
    heartbeat_interval_seconds=30.0,
    flush_interval_ms=0,
)

# Lifecycle managed by SDK
await sensor.lifecycle.start()

# Emit events via the built-in dispatcher
event = EventBuilder("my-sensor").text("Something happened").build()
await sensor.events.emit(event)

# Shutdown
await sensor.lifecycle.stop()
```

## Typical Sensor Lifecycle

```python
from gladys_sensor_sdk import (
    AdapterBase,
    EventBuilder,
    Intent,
    StartArgs,
    StopArgs,
)

class MySensor(AdapterBase):
    async def handle_start(self, args: StartArgs) -> None:
        pass  # Initialize driver

    async def handle_stop(self, args: StopArgs) -> None:
        pass  # Cleanup driver

sensor = MySensor(
    component_id="my-sensor",
    component_type="sensor.game",
    orchestrator_address="localhost:50051",
)

# 1. Start lifecycle (registers, starts heartbeat)
await sensor.lifecycle.start()

# 2. Emit events in your main loop
while running:
    event = (
        EventBuilder("my-sensor")
        .text(observe_something())
        .intent(Intent.ACTIONABLE)
        .build()
    )
    await sensor.events.emit(event)

# 3. Shutdown (stops heartbeat, unregisters)
await sensor.lifecycle.stop()
```

## Protocol Details

See [SENSOR_ARCHITECTURE.md](../../../docs/design/SENSOR_ARCHITECTURE.md) for
the full sensor protocol specification, delivery patterns, and capture/replay
design.
