# GLADyS Java Sensor SDK

Java client library for building GLADyS sensors. Provides adapter infrastructure
(gRPC client, heartbeat, event builder, registration) so sensor developers focus
on driver integration and domain-specific normalization.

**Terminology**: A sensor is a bundle of driver (captures from app) + adapter
(normalizes and publishes to orchestrator). This SDK provides the adapter half.

## Prerequisites

- JDK 11+ (sourceCompatibility is Java 11)
- Gradle (wrapper included)
- Proto files in `proto/` at the project root (referenced via `../../../proto`)

## Build

```bash
./gradlew build
```

The build uses the `com.google.protobuf` Gradle plugin to compile `.proto` files
and generate Java/gRPC stubs automatically. Proto source directory is configured
to read from the shared `proto/` directory at the project root.

## Test

```bash
./gradlew test
```

Tests use JUnit 5 and gRPC in-process transport for testing without a live server.

## API Overview

### GladysClient

gRPC client wrapping the `OrchestratorService` blocking stub. Manages channel
lifecycle and implements `AutoCloseable`.

```java
try (GladysClient client = new GladysClient("localhost", 50050)) {
    // Publish a single event
    EventAck ack = client.publishEvent(event);

    // Publish a batch of events
    List<EventAck> acks = client.publishEvents(events);

    // Register as a sensor
    RegisterResponse resp = client.register(
        "my-sensor", "sensor", capabilities);

    // Send heartbeat
    HeartbeatResponse hb = client.heartbeat("my-sensor");

    // Heartbeat with explicit state
    client.heartbeat("my-sensor", ComponentState.COMPONENT_STATE_PAUSED);
}
```

### EventBuilder

Fluent builder for `Event` protobuf messages. Populates the adapter-responsibility
fields (id, timestamp, source, raw_text, structured, intent, evaluation_data,
metadata). Fields populated downstream by the pipeline (salience, entity_ids) are
not exposed.

```java
Event event = new EventBuilder("my-sensor")
    .text("Player health dropped to 3 hearts")
    .structured(Map.of("health", 3, "maxHealth", 20))
    .intent("health_alert")
    .evaluationData(Map.of("threshold", 0.2))
    .build();
```

Each call to `build()` generates a unique event ID and request ID automatically.

### HeartbeatManager

Background heartbeat sender using a `ScheduledExecutorService` with a daemon
thread. Sends periodic heartbeats to the orchestrator so it can detect sensor
liveness.

```java
HeartbeatManager hb = new HeartbeatManager(client, "my-sensor", 30);
hb.start();

// Change reported state (e.g., when pausing)
hb.setState(ComponentState.COMPONENT_STATE_PAUSED);

// On shutdown
hb.stop();
```

The manager swallows heartbeat errors with a log warning so a transient network
failure does not crash the sensor.

### SensorRegistration

Static one-shot helper for registering a sensor with the orchestrator.

```java
ComponentCapabilities caps = ComponentCapabilities.newBuilder()
    .setTransportMode(TransportMode.TRANSPORT_MODE_EVENT)
    .build();

RegisterResponse resp = SensorRegistration.register(
    client, "my-sensor", "sensor", caps);
```

### EventDispatcher

Configurable event dispatch with three modes: immediate (default), scheduled
(buffer + timer flush), and hybrid (scheduled + threat bypass).

```java
// Immediate mode (default) — every emit sends now
EventDispatcher events = new EventDispatcher(client, "my-sensor");

// Scheduled mode (600ms flush interval)
EventDispatcher events = new EventDispatcher(client, "my-sensor", 600, true);

// With flow control strategy
EventDispatcher events = new EventDispatcher(
    client, "my-sensor", 0, true, new RateLimitStrategy(100, 60));

// Single event — returns true if published, false if suppressed
boolean sent = events.emit(event);

// Batch with selective filtering
EmitResult result = events.emitBatch(eventList);
// result.sent() + result.suppressed() == eventList.size()

// Metrics
events.getEventsPublished();
events.getEventsFiltered();

// Shutdown (flushes remaining buffer)
events.shutdown();
```

### CommandDispatcher

Processes commands received via heartbeat responses. Register handlers per
command type; unhandled commands are logged and skipped.

```java
CommandDispatcher commands = new CommandDispatcher("my-sensor");
commands.onStart(args -> startSensor(args));
commands.onStop(args -> stopSensor(args));

// In heartbeat callback
commands.dispatch(heartbeatResponse.getPendingCommandsList());
```

### FlowStrategy

Pluggable rate limiting for event emission. The SDK ships `NoOpStrategy`
(passthrough) and `RateLimitStrategy` (token bucket).

```java
// Token bucket: 100 events per 60-second window
FlowStrategy strategy = new RateLimitStrategy(100, 60);

// From orchestrator config
FlowStrategy strategy = FlowStrategyFactory.create(configMap);

// Hot-swap at runtime
events.setStrategy(strategy);
```

## Typical Sensor Lifecycle

```java
try (GladysClient client = new GladysClient("localhost", 50050)) {
    // 1. Register
    SensorRegistration.register(client, "my-sensor", "sensor", capabilities);

    // 2. Start heartbeats
    HeartbeatManager hb = new HeartbeatManager(client, "my-sensor", 30);
    hb.start();

    // 3. Set up event dispatch with flow control
    EventDispatcher events = new EventDispatcher(client, "my-sensor");

    // 4. Emit events in your main loop
    while (running) {
        Event event = new EventBuilder("my-sensor")
            .text(observeSomething())
            .build();
        events.emit(event);
    }

    // 5. Shutdown
    events.shutdown();
    hb.stop();
}
```

## Protocol Details

See [SENSOR_ARCHITECTURE.md](../../../docs/design/SENSOR_ARCHITECTURE.md) for
the full sensor protocol specification, delivery patterns, and capture/replay
design.
