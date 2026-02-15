# GLADyS TypeScript Sensor SDK

TypeScript client library for building GLADyS sensors. Provides adapter
infrastructure (gRPC client, heartbeat, event builder, registration) so sensor
developers focus on driver integration and domain-specific normalization.

**Terminology**: A sensor is a bundle of driver (captures from app) + adapter
(normalizes and publishes to orchestrator). This SDK provides the adapter half.

## Prerequisites

- Node.js 18+
- Proto files in `proto/` at the project root

## Setup

```bash
npm install
npm run build
```

The `build` script automatically runs `proto:generate` first (via the `prebuild`
hook), which invokes `scripts/generate-protos.js` to produce TypeScript stubs
from the shared `proto/` definitions using ts-proto and grpc-tools.

## Test

```bash
npm test
```

Tests use Vitest (`vitest run`). Use `npm run test:watch` for watch mode.

## API Overview

### GladysClient

Promise-based gRPC client wrapping the generated `OrchestratorServiceClient`.
Accepts either `(host, port)` or `(address, credentials)` constructor overloads.

```typescript
import { GladysClient, ComponentState } from "gladys-sensor-sdk";

const client = new GladysClient("localhost", 50050);

// Publish a single event
const ack = await client.publishEvent(event);

// Publish a batch of events
const acks = await client.publishEvents([event1, event2]);

// Register as a sensor
const resp = await client.register("my-sensor", "sensor", capabilities);

// Send heartbeat
const hb = await client.heartbeat("my-sensor");

// Heartbeat with explicit state
await client.heartbeat("my-sensor", ComponentState.COMPONENT_STATE_PAUSED);

// Cleanup
client.close();
```

### EventBuilder

Fluent builder for `Event` messages. Populates adapter-responsibility fields
(id, timestamp, source, rawText, structured, intent, evaluationData, metadata).
Fields populated downstream (salience, entityIds) are left at defaults.

```typescript
import { EventBuilder } from "gladys-sensor-sdk";

const event = new EventBuilder("my-sensor")
  .text("Player health dropped to 3 hearts")
  .structured({ health: 3, maxHealth: 20 })
  .intent("health_alert")
  .evaluationData({ threshold: 0.2 })
  .build();
```

Each call to `build()` generates a unique event ID and request ID automatically.

### HeartbeatManager

Background heartbeat sender using `setInterval`. The timer is `unref()`'d so it
does not prevent Node.js process exit. Default state is
`COMPONENT_STATE_ACTIVE`; call `setState()` to change.

```typescript
import { HeartbeatManager, ComponentState } from "gladys-sensor-sdk";

const hb = new HeartbeatManager(client, "my-sensor", 30);
hb.start();

// Change reported state (e.g., when pausing)
hb.setState(ComponentState.COMPONENT_STATE_PAUSED);

// Query current state
console.log(hb.getState());

// On shutdown
hb.stop();
```

Heartbeat errors are swallowed silently. The orchestrator monitors heartbeat
absence for dead sensor detection.

### SensorRegistration

Static async one-shot helper for registering a sensor.

```typescript
import { SensorRegistration, TransportMode } from "gladys-sensor-sdk";

const resp = await SensorRegistration.register(
  client,
  "my-sensor",
  "sensor",
  { transportMode: TransportMode.TRANSPORT_MODE_EVENT }
);
```

### EventDispatcher

Configurable event dispatch with three modes: immediate (default), scheduled
(buffer + timer flush), and hybrid (scheduled + threat bypass).

```typescript
import { EventDispatcher } from "gladys-sensor-sdk";

// Immediate mode (default) — every emit sends now
const events = new EventDispatcher(client, "my-sensor");

// Scheduled mode (600ms flush interval)
const events = new EventDispatcher(client, "my-sensor", {
  flushIntervalMs: 600,
});

// With flow control strategy
const events = new EventDispatcher(client, "my-sensor", {
  strategy: new RateLimitStrategy(100, 60),
});

// Single event — returns true if published, false if suppressed
const sent = await events.emit(event);

// Batch with selective filtering
const result = await events.emitBatch(eventList);
// result.sent + result.suppressed === eventList.length

// Metrics
events.eventsPublished;
events.eventsFiltered;

// Shutdown
await events.flush();
events.stop();
```

### CommandDispatcher

Processes commands received via heartbeat responses. Register handlers per
command type; unhandled commands are logged and skipped.

```typescript
import { CommandDispatcher } from "gladys-sensor-sdk";

const commands = new CommandDispatcher("my-sensor");
commands.onStart(async (args) => startSensor(args));
commands.onStop(async (args) => stopSensor(args));

// In heartbeat callback
await commands.dispatch(heartbeatResponse.pendingCommands);
```

### FlowStrategy

Pluggable rate limiting for event emission. The SDK ships `NoOpStrategy`
(passthrough) and `RateLimitStrategy` (token bucket).

```typescript
import { RateLimitStrategy, createStrategy } from "gladys-sensor-sdk";

// Token bucket: 100 events per 60-second window
const strategy = new RateLimitStrategy(100, 60);

// From orchestrator config
const strategy = createStrategy(configObject);

// Hot-swap at runtime
events.setStrategy(strategy);
```

## Typical Sensor Lifecycle

```typescript
import {
  GladysClient,
  EventBuilder,
  EventDispatcher,
  SensorRegistration,
  HeartbeatManager,
  TransportMode,
} from "gladys-sensor-sdk";

const client = new GladysClient("localhost", 50050);

// 1. Register
await SensorRegistration.register(client, "my-sensor", "sensor", {
  transportMode: TransportMode.TRANSPORT_MODE_EVENT,
});

// 2. Start heartbeats
const hb = new HeartbeatManager(client, "my-sensor", 30);
hb.start();

// 3. Set up event dispatch with flow control
const events = new EventDispatcher(client, "my-sensor");

// 4. Emit events
const event = new EventBuilder("my-sensor")
  .text("Something happened")
  .build();
await events.emit(event);

// 5. Shutdown
await events.flush();
events.stop();
hb.stop();
client.close();
```

## Protocol Details

See [SENSOR_ARCHITECTURE.md](../../../docs/design/SENSOR_ARCHITECTURE.md) for
the full sensor protocol specification, delivery patterns, and capture/replay
design.
