# GLADyS Java Sensor SDK

Java client library for integrating sensors with the GLADyS orchestrator via gRPC.

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

Fluent builder for `Event` protobuf messages. Populates the sensor-responsibility
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

## Typical Sensor Lifecycle

```java
try (GladysClient client = new GladysClient("localhost", 50050)) {
    // 1. Register
    SensorRegistration.register(client, "my-sensor", "sensor", capabilities);

    // 2. Start heartbeats
    HeartbeatManager hb = new HeartbeatManager(client, "my-sensor", 30);
    hb.start();

    // 3. Emit events in your main loop
    while (running) {
        Event event = new EventBuilder("my-sensor")
            .text(observeSomething())
            .build();
        client.publishEvent(event);
    }

    // 4. Shutdown
    hb.stop();
}
```

## Protocol Details

See [SENSOR_ARCHITECTURE.md](../../../docs/design/SENSOR_ARCHITECTURE.md) for
the full sensor protocol specification, delivery patterns, and capture/replay
design.
