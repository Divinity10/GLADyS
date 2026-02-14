# Java SDK Command Handling Design

**Status**: Design complete
**Target**: GLADyS PoC 2
**Language**: Java 8+

## Overview

This document specifies the complete Java SDK API for GLADyS sensor command handling. The design prioritizes idiomatic Java patterns
(callback/listener, builder, functional interfaces) and removes boilerplate through typed command handlers and automatic state management.

## Design Goals

1. **Zero dispatch chains**: No if/elif command type checking in sensor code
2. **Idiomatic Java**: Feels like Spring Boot, gRPC, JUnit patterns
3. **Composition over inheritance**: Sensors extend any base class (critical for RuneLite Plugin compatibility)
4. **Automatic state management**: SDK handles state transitions with escape hatch for overrides
5. **Fast handler execution**: Handlers run on heartbeat thread, should be fast
6. **Testability**: Test harness bypasses gRPC, dispatches commands directly

## API Specification

### 1. TimeoutConfig

Builder pattern for gRPC timeout configuration.

```java
package com.gladys.sensor;

/**
 * Configuration for gRPC call timeouts.
 * Default values follow ADR-0005 heartbeat/command latency requirements.
 */
public class TimeoutConfig {
    private final long publishEventMs;
    private final long heartbeatMs;
    private final long registerMs;

    private TimeoutConfig(Builder builder) {
        this.publishEventMs = builder.publishEventMs;
        this.heartbeatMs = builder.heartbeatMs;
        this.registerMs = builder.registerMs;
    }

    public long getPublishEventMs() { return publishEventMs; }
    public long getHeartbeatMs() { return heartbeatMs; }
    public long getRegisterMs() { return registerMs; }

    /**
     * Creates default timeout configuration:
     * - publishEvent: 100ms
     * - heartbeat: 5000ms
     * - register: 10000ms
     */
    public static TimeoutConfig defaults() {
        return new Builder().build();
    }

    /**
     * Creates no-timeout configuration for testing.
     * Sets all timeouts to Long.MAX_VALUE.
     */
    public static TimeoutConfig noTimeout() {
        return new Builder()
            .publishEventMs(Long.MAX_VALUE)
            .heartbeatMs(Long.MAX_VALUE)
            .registerMs(Long.MAX_VALUE)
            .build();
    }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private long publishEventMs = 100;
        private long heartbeatMs = 5000;
        private long registerMs = 10000;

        public Builder publishEventMs(long ms) {
            this.publishEventMs = ms;
            return this;
        }

        public Builder heartbeatMs(long ms) {
            this.heartbeatMs = ms;
            return this;
        }

        public Builder registerMs(long ms) {
            this.registerMs = ms;
            return this;
        }

        public TimeoutConfig build() {
            return new TimeoutConfig(this);
        }
    }
}
```

### 2. Updated GladysClient

Add TimeoutConfig to constructor, apply deadlines to blocking stubs.

```java
package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;
import gladys.v1.OrchestratorServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * gRPC client for communicating with the GLADyS orchestrator.
 * Manages channel lifecycle and provides typed methods for event publishing,
 * registration, and heartbeat.
 */
public class GladysClient implements AutoCloseable {

    private final ManagedChannel channel;
    private final OrchestratorServiceGrpc.OrchestratorServiceBlockingStub baseStub;
    private final TimeoutConfig timeoutConfig;

    /**
     * Creates client with default timeouts.
     */
    public GladysClient(String host, int port) {
        this(host, port, TimeoutConfig.defaults());
    }

    /**
     * Creates client with custom timeout configuration.
     */
    public GladysClient(String host, int port, TimeoutConfig timeoutConfig) {
        this(ManagedChannelBuilder.forAddress(host, port)
                .usePlaintext()
                .build(), timeoutConfig);
    }

    // Package-private for testing with InProcessChannel
    GladysClient(ManagedChannel channel, TimeoutConfig timeoutConfig) {
        this.channel = channel;
        this.baseStub = OrchestratorServiceGrpc.newBlockingStub(channel);
        this.timeoutConfig = timeoutConfig;
    }

    public Orchestrator.EventAck publishEvent(Common.Event event) {
        Orchestrator.PublishEventRequest request = Orchestrator.PublishEventRequest.newBuilder()
                .setEvent(event)
                .setMetadata(event.getMetadata())
                .build();
        Orchestrator.PublishEventResponse response = baseStub
                .withDeadlineAfter(timeoutConfig.getPublishEventMs(), TimeUnit.MILLISECONDS)
                .publishEvent(request);
        return response.getAck();
    }

    public Orchestrator.PublishEventsResponse publishEvents(List<Common.Event> events) {
        Common.RequestMetadata metadata = Common.RequestMetadata.newBuilder()
                .setRequestId(UUID.randomUUID().toString())
                .setTimestampMs(System.currentTimeMillis())
                .build();

        Orchestrator.PublishEventsRequest request = Orchestrator.PublishEventsRequest.newBuilder()
                .addAllEvents(events)
                .setMetadata(metadata)
                .build();
        return baseStub
                .withDeadlineAfter(timeoutConfig.getPublishEventMs(), TimeUnit.MILLISECONDS)
                .publishEvents(request);
    }

    public Orchestrator.RegisterResponse register(String sensorId, String sensorType,
                                                   Orchestrator.ComponentCapabilities capabilities) {
        return register(sensorId, sensorType, "", capabilities);
    }

    public Orchestrator.RegisterResponse register(String sensorId, String sensorType, String address,
                                                   Orchestrator.ComponentCapabilities capabilities) {
        Orchestrator.RegisterRequest request = Orchestrator.RegisterRequest.newBuilder()
                .setComponentId(sensorId)
                .setComponentType(sensorType)
                .setAddress(address)
                .setCapabilities(capabilities)
                .setMetadata(Common.RequestMetadata.newBuilder()
                        .setRequestId(UUID.randomUUID().toString())
                        .setTimestampMs(System.currentTimeMillis())
                        .build())
                .build();
        return baseStub
                .withDeadlineAfter(timeoutConfig.getRegisterMs(), TimeUnit.MILLISECONDS)
                .registerComponent(request);
    }

    /**
     * Sends heartbeat with ACTIVE state.
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId) {
        return heartbeat(componentId, Common.ComponentState.COMPONENT_STATE_ACTIVE, null);
    }

    /**
     * Sends heartbeat with specified state.
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId, Common.ComponentState state) {
        return heartbeat(componentId, state, null);
    }

    /**
     * Sends heartbeat with specified state and optional error message.
     * Error message should be populated when state is ERROR.
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId, Common.ComponentState state, String errorMessage) {
        Orchestrator.HeartbeatRequest.Builder requestBuilder = Orchestrator.HeartbeatRequest.newBuilder()
                .setComponentId(componentId)
                .setState(state)
                .setMetadata(Common.RequestMetadata.newBuilder()
                        .setRequestId(UUID.randomUUID().toString())
                        .setTimestampMs(System.currentTimeMillis())
                        .build());

        if (errorMessage != null) {
            requestBuilder.setErrorMessage(errorMessage);
        }

        return baseStub
                .withDeadlineAfter(timeoutConfig.getHeartbeatMs(), TimeUnit.MILLISECONDS)
                .heartbeat(requestBuilder.build());
    }

    @Override
    public void close() {
        channel.shutdown();
        try {
            if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                channel.shutdownNow();
            }
        } catch (InterruptedException e) {
            channel.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

### 3. Intent Constants

String constants for event intent field.

```java
package com.gladys.sensor;

/**
 * Intent constants for Event.intent field.
 * Intent is a string in the proto (not enum) to support domain-specific intents.
 */
public final class Intent {
    private Intent() {}

    public static final String ACTIONABLE = "actionable";
    public static final String INFORMATIONAL = "informational";
    public static final String UNKNOWN = "unknown";
}
```

### 4. Command Args Classes

Typed args classes with getters and raw() escape hatch.

```java
package com.gladys.sensor;

import com.google.protobuf.Struct;
import com.google.protobuf.Value;

/**
 * Generic command arguments wrapper.
 * Used by typed args classes as escape hatch for undocumented args.
 */
public class CommandArgs {
    private final Struct struct;

    CommandArgs(Struct struct) {
        this.struct = struct != null ? struct : Struct.getDefaultInstance();
    }

    /**
     * Returns raw protobuf Struct containing all arguments.
     */
    public Struct getStruct() {
        return struct;
    }

    /**
     * Gets string value for key, returns default if missing or wrong type.
     */
    public String getString(String key, String defaultValue) {
        Value value = struct.getFieldsMap().get(key);
        if (value == null || value.getKindCase() != Value.KindCase.STRING_VALUE) {
            return defaultValue;
        }
        return value.getStringValue();
    }

    /**
     * Gets boolean value for key, returns default if missing or wrong type.
     */
    public boolean getBoolean(String key, boolean defaultValue) {
        Value value = struct.getFieldsMap().get(key);
        if (value == null || value.getKindCase() != Value.KindCase.BOOL_VALUE) {
            return defaultValue;
        }
        return value.getBoolValue();
    }

    /**
     * Gets number value for key, returns default if missing or wrong type.
     */
    public double getNumber(String key, double defaultValue) {
        Value value = struct.getFieldsMap().get(key);
        if (value == null || value.getKindCase() != Value.KindCase.NUMBER_VALUE) {
            return defaultValue;
        }
        return value.getNumberValue();
    }

    /**
     * Gets integer value for key, returns default if missing or wrong type.
     */
    public int getInt(String key, int defaultValue) {
        return (int) getNumber(key, defaultValue);
    }

    /**
     * Creates test args from varargs pairs.
     * Example: CommandArgs.test("key1", "value1", "key2", true)
     */
    public static CommandArgs test(Object... keyValuePairs) {
        if (keyValuePairs.length % 2 != 0) {
            throw new IllegalArgumentException("Must provide key-value pairs");
        }
        Struct.Builder builder = Struct.newBuilder();
        for (int i = 0; i < keyValuePairs.length; i += 2) {
            String key = (String) keyValuePairs[i];
            Object value = keyValuePairs[i + 1];
            builder.putFields(key, EventBuilder.objectToValue(value));
        }
        return new CommandArgs(builder.build());
    }

    // Package-private helper to convert Object to protobuf Value
    static Value objectToValue(Object obj) {
        if (obj == null) {
            return Value.newBuilder().setNullValueValue(0).build();
        } else if (obj instanceof String) {
            return Value.newBuilder().setStringValue((String) obj).build();
        } else if (obj instanceof Number) {
            return Value.newBuilder().setNumberValue(((Number) obj).doubleValue()).build();
        } else if (obj instanceof Boolean) {
            return Value.newBuilder().setBoolValue((Boolean) obj).build();
        } else {
            return Value.newBuilder().setStringValue(obj.toString()).build();
        }
    }
}

/**
 * Arguments for START command.
 */
public class StartArgs extends CommandArgs {
    StartArgs(Struct struct) {
        super(struct);
    }

    /**
     * Returns true if sensor should run in dry-run mode (no side effects).
     */
    public boolean isDryRun() {
        return getBoolean("dry_run", false);
    }

    /**
     * Returns config override key-value pairs.
     * Empty string if not specified.
     */
    public String getConfigOverride() {
        return getString("config_override", "");
    }

    /**
     * Creates test START args.
     */
    public static StartArgs test() {
        return new StartArgs(Struct.getDefaultInstance());
    }

    /**
     * Creates test START args with dry_run=true.
     */
    public static StartArgs testDryRun() {
        return new StartArgs(Struct.newBuilder()
                .putFields("dry_run", Value.newBuilder().setBoolValue(true).build())
                .build());
    }

    /**
     * Creates test START args with custom config override.
     */
    public static StartArgs testWithConfig(String configOverride) {
        return new StartArgs(Struct.newBuilder()
                .putFields("config_override", Value.newBuilder().setStringValue(configOverride).build())
                .build());
    }
}

/**
 * Arguments for STOP command.
 */
public class StopArgs extends CommandArgs {
    StopArgs(Struct struct) {
        super(struct);
    }

    /**
     * Returns true if sensor should skip cleanup (force stop).
     */
    public boolean isForce() {
        return getBoolean("force", false);
    }

    /**
     * Returns graceful shutdown timeout in seconds.
     * Default: 30 seconds.
     */
    public int getTimeoutSeconds() {
        return getInt("timeout_seconds", 30);
    }

    /**
     * Creates test STOP args.
     */
    public static StopArgs test() {
        return new StopArgs(Struct.getDefaultInstance());
    }

    /**
     * Creates test STOP args with force=true.
     */
    public static StopArgs testForce() {
        return new StopArgs(Struct.newBuilder()
                .putFields("force", Value.newBuilder().setBoolValue(true).build())
                .build());
    }

    /**
     * Creates test STOP args with custom timeout.
     */
    public static StopArgs testWithTimeout(int timeoutSeconds) {
        return new StopArgs(Struct.newBuilder()
                .putFields("timeout_seconds", Value.newBuilder().setNumberValue(timeoutSeconds).build())
                .build());
    }
}

/**
 * Arguments for RECOVER command.
 */
public class RecoverArgs extends CommandArgs {
    RecoverArgs(Struct struct) {
        super(struct);
    }

    /**
     * Returns recovery strategy: "restart", "reconnect", "reset".
     * Default: "restart".
     */
    public String getStrategy() {
        return getString("strategy", "restart");
    }

    /**
     * Returns max retry attempts.
     * Default: 3.
     */
    public int getMaxRetries() {
        return getInt("max_retries", 3);
    }

    /**
     * Creates test RECOVER args.
     */
    public static RecoverArgs test() {
        return new RecoverArgs(Struct.getDefaultInstance());
    }

    /**
     * Creates test RECOVER args with specific strategy.
     */
    public static RecoverArgs testWithStrategy(String strategy) {
        return new RecoverArgs(Struct.newBuilder()
                .putFields("strategy", Value.newBuilder().setStringValue(strategy).build())
                .build());
    }

    /**
     * Creates test RECOVER args with max retries.
     */
    public static RecoverArgs testWithRetries(int maxRetries) {
        return new RecoverArgs(Struct.newBuilder()
                .putFields("max_retries", Value.newBuilder().setNumberValue(maxRetries).build())
                .build());
    }
}

/**
 * Arguments for HEALTH_CHECK command.
 */
public class HealthCheckArgs extends CommandArgs {
    HealthCheckArgs(Struct struct) {
        super(struct);
    }

    /**
     * Returns true if health check should be deep (check all subsystems).
     * Default: false (shallow check).
     */
    public boolean isDeep() {
        return getBoolean("deep", false);
    }

    /**
     * Returns timeout for health check in milliseconds.
     * Default: 5000ms.
     */
    public int getTimeoutMs() {
        return getInt("timeout_ms", 5000);
    }

    /**
     * Creates test HEALTH_CHECK args.
     */
    public static HealthCheckArgs test() {
        return new HealthCheckArgs(Struct.getDefaultInstance());
    }

    /**
     * Creates test HEALTH_CHECK args with deep=true.
     */
    public static HealthCheckArgs testDeep() {
        return new HealthCheckArgs(Struct.newBuilder()
                .putFields("deep", Value.newBuilder().setBoolValue(true).build())
                .build());
    }

    /**
     * Creates test HEALTH_CHECK args with custom timeout.
     */
    public static HealthCheckArgs testWithTimeout(int timeoutMs) {
        return new HealthCheckArgs(Struct.newBuilder()
                .putFields("timeout_ms", Value.newBuilder().setNumberValue(timeoutMs).build())
                .build());
    }
}
```

### 5. Handler Functional Interfaces

```java
package com.gladys.sensor;

import gladys.v1.Common;

/**
 * Functional interface for command handlers with typed arguments.
 * Returns null to accept default state transition.
 * Returns explicit ComponentState to override default.
 * Throws exception to set ERROR state.
 *
 * @param <T> Typed args class (StartArgs, StopArgs, RecoverArgs, HealthCheckArgs)
 */
@FunctionalInterface
public interface CommandHandler<T extends CommandArgs> {
    /**
     * Handles command with typed arguments.
     *
     * @param args Typed command arguments
     * @return ComponentState to override default, or null to accept default
     * @throws Exception to set ERROR state (populated in error_message field)
     */
    Common.ComponentState handle(T args) throws Exception;
}

/**
 * Functional interface for simple command handlers (PAUSE, RESUME, RELOAD).
 * These commands have no documented arguments.
 */
@FunctionalInterface
public interface SimpleCommandHandler {
    /**
     * Handles command with no arguments.
     *
     * @return ComponentState to override default, or null to accept default
     * @throws Exception to set ERROR state (populated in error_message field)
     */
    Common.ComponentState handle() throws Exception;
}

/**
 * Functional interface for command error callback.
 * Called when a command handler throws an exception.
 * HEALTH_CHECK failures do NOT trigger this callback (health check fail ≠ broken).
 */
@FunctionalInterface
public interface CommandErrorHandler {
    /**
     * Handles command execution error.
     *
     * @param command The command that failed
     * @param exception The exception thrown by handler
     * @param currentState The component state before error
     * @return ComponentState to set (null = accept ERROR state)
     */
    Common.ComponentState onError(Orchestrator.Command command, Exception exception, Common.ComponentState currentState);
}
```

### 6. CommandDispatcher

Builder pattern for registering command handlers.

```java
package com.gladys.sensor;

import com.google.protobuf.Struct;
import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Dispatcher for sensor command handlers.
 * Uses builder pattern for handler registration.
 * Dispatches commands to registered handlers and manages state transitions.
 *
 * Thread safety: All handlers execute on heartbeat thread.
 */
public class CommandDispatcher {

    private static final Logger logger = Logger.getLogger(CommandDispatcher.class.getName());

    private final CommandHandler<StartArgs> startHandler;
    private final CommandHandler<StopArgs> stopHandler;
    private final SimpleCommandHandler pauseHandler;
    private final SimpleCommandHandler resumeHandler;
    private final SimpleCommandHandler reloadHandler;
    private final CommandHandler<HealthCheckArgs> healthCheckHandler;
    private final CommandHandler<RecoverArgs> recoverHandler;
    private final CommandErrorHandler errorHandler;

    private CommandDispatcher(Builder builder) {
        this.startHandler = builder.startHandler;
        this.stopHandler = builder.stopHandler;
        this.pauseHandler = builder.pauseHandler;
        this.resumeHandler = builder.resumeHandler;
        this.reloadHandler = builder.reloadHandler;
        this.healthCheckHandler = builder.healthCheckHandler;
        this.recoverHandler = builder.recoverHandler;
        this.errorHandler = builder.errorHandler;
    }

    /**
     * Dispatches command to registered handler.
     * Returns new state after command execution.
     * Default state transitions:
     * - START → ACTIVE
     * - STOP → STOPPED
     * - PAUSE → PAUSED
     * - RESUME → ACTIVE
     * - RELOAD → ACTIVE
     * - HEALTH_CHECK → unchanged
     * - RECOVER → ACTIVE
     *
     * Handler returns null = accept default.
     * Handler returns explicit state = override default.
     * Handler throws = ERROR (except HEALTH_CHECK).
     *
     * @param command Command enum value
     * @param args Command arguments (google.protobuf.Struct)
     * @param currentState Current component state
     * @return Tuple of (new state, error message or null)
     */
    StateAndError dispatch(Orchestrator.Command command, Struct args, Common.ComponentState currentState) {
        try {
            Common.ComponentState resultState = null;

            switch (command) {
                case COMMAND_START:
                    if (startHandler != null) {
                        resultState = startHandler.handle(new StartArgs(args));
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_ACTIVE,
                            null
                    );

                case COMMAND_STOP:
                    if (stopHandler != null) {
                        resultState = stopHandler.handle(new StopArgs(args));
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_STOPPED,
                            null
                    );

                case COMMAND_PAUSE:
                    if (pauseHandler != null) {
                        resultState = pauseHandler.handle();
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_PAUSED,
                            null
                    );

                case COMMAND_RESUME:
                    if (resumeHandler != null) {
                        resultState = resumeHandler.handle();
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_ACTIVE,
                            null
                    );

                case COMMAND_RELOAD:
                    if (reloadHandler != null) {
                        resultState = reloadHandler.handle();
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_ACTIVE,
                            null
                    );

                case COMMAND_HEALTH_CHECK:
                    if (healthCheckHandler != null) {
                        resultState = healthCheckHandler.handle(new HealthCheckArgs(args));
                    }
                    // HEALTH_CHECK failure does NOT set ERROR state
                    return new StateAndError(
                            resultState != null ? resultState : currentState,
                            null
                    );

                case COMMAND_RECOVER:
                    if (recoverHandler != null) {
                        resultState = recoverHandler.handle(new RecoverArgs(args));
                    }
                    return new StateAndError(
                            resultState != null ? resultState : Common.ComponentState.COMPONENT_STATE_ACTIVE,
                            null
                    );

                default:
                    logger.warning("Unhandled command: " + command);
                    return new StateAndError(currentState, "Unhandled command: " + command);
            }

        } catch (Exception e) {
            // HEALTH_CHECK exception does NOT set ERROR
            if (command == Orchestrator.Command.COMMAND_HEALTH_CHECK) {
                logger.log(Level.WARNING, "Health check failed", e);
                return new StateAndError(currentState, null);
            }

            // Other commands: invoke error handler or default to ERROR
            logger.log(Level.SEVERE, "Command handler failed: " + command, e);
            String errorMessage = e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName();

            Common.ComponentState errorState = Common.ComponentState.COMPONENT_STATE_ERROR;
            if (errorHandler != null) {
                Common.ComponentState handlerResult = errorHandler.onError(command, e, currentState);
                if (handlerResult != null) {
                    errorState = handlerResult;
                }
            }

            return new StateAndError(errorState, errorMessage);
        }
    }

    static class StateAndError {
        final Common.ComponentState state;
        final String errorMessage;

        StateAndError(Common.ComponentState state, String errorMessage) {
            this.state = state;
            this.errorMessage = errorMessage;
        }
    }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private CommandHandler<StartArgs> startHandler;
        private CommandHandler<StopArgs> stopHandler;
        private SimpleCommandHandler pauseHandler;
        private SimpleCommandHandler resumeHandler;
        private SimpleCommandHandler reloadHandler;
        private CommandHandler<HealthCheckArgs> healthCheckHandler;
        private CommandHandler<RecoverArgs> recoverHandler;
        private CommandErrorHandler errorHandler;

        /**
         * Registers START command handler.
         */
        public Builder onStart(CommandHandler<StartArgs> handler) {
            this.startHandler = handler;
            return this;
        }

        /**
         * Registers STOP command handler.
         */
        public Builder onStop(CommandHandler<StopArgs> handler) {
            this.stopHandler = handler;
            return this;
        }

        /**
         * Registers PAUSE command handler.
         */
        public Builder onPause(SimpleCommandHandler handler) {
            this.pauseHandler = handler;
            return this;
        }

        /**
         * Registers RESUME command handler.
         */
        public Builder onResume(SimpleCommandHandler handler) {
            this.resumeHandler = handler;
            return this;
        }

        /**
         * Registers RELOAD command handler.
         */
        public Builder onReload(SimpleCommandHandler handler) {
            this.reloadHandler = handler;
            return this;
        }

        /**
         * Registers HEALTH_CHECK command handler.
         */
        public Builder onHealthCheck(CommandHandler<HealthCheckArgs> handler) {
            this.healthCheckHandler = handler;
            return this;
        }

        /**
         * Registers RECOVER command handler.
         */
        public Builder onRecover(CommandHandler<RecoverArgs> handler) {
            this.recoverHandler = handler;
            return this;
        }

        /**
         * Registers global error handler.
         * Called when any command handler throws an exception.
         * HEALTH_CHECK failures do NOT trigger this handler.
         */
        public Builder onCommandError(CommandErrorHandler handler) {
            this.errorHandler = handler;
            return this;
        }

        public CommandDispatcher build() {
            return new CommandDispatcher(this);
        }
    }
}
```

### 7. SensorLifecycle

Top-level entry point that composes HeartbeatManager + CommandDispatcher.

```java
package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.logging.Logger;

/**
 * Top-level sensor lifecycle manager.
 * Composes HeartbeatManager + CommandDispatcher + state management.
 * Builder pattern for configuration.
 */
public class SensorLifecycle {

    private static final Logger logger = Logger.getLogger(SensorLifecycle.class.getName());

    private final GladysClient client;
    private final String componentId;
    private final HeartbeatManager heartbeatManager;
    private final CommandDispatcher dispatcher;
    private volatile boolean running = false;

    private SensorLifecycle(Builder builder) {
        this.client = builder.client;
        this.componentId = builder.componentId;
        this.dispatcher = builder.dispatcherBuilder.build();
        this.heartbeatManager = new HeartbeatManager(client, componentId, builder.heartbeatIntervalSeconds);
        this.heartbeatManager.setDispatcher(dispatcher);
    }

    /**
     * Starts heartbeat in background.
     * Non-blocking - sensor keeps control.
     * Heartbeat thread dispatches commands and manages state transitions.
     */
    public void start() {
        if (running) {
            logger.warning("Lifecycle already started");
            return;
        }
        running = true;
        heartbeatManager.start();
        logger.info("Sensor lifecycle started: " + componentId);
    }

    /**
     * Stops heartbeat and closes client.
     * Blocks until heartbeat thread terminates.
     */
    public void stop() {
        if (!running) {
            return;
        }
        running = false;
        heartbeatManager.stop();
        client.close();
        logger.info("Sensor lifecycle stopped: " + componentId);
    }

    /**
     * Returns true if lifecycle is running.
     */
    public boolean isRunning() {
        return running;
    }

    /**
     * Sets component state.
     * Used by command handlers to override default state transitions.
     */
    public void setState(Common.ComponentState state) {
        heartbeatManager.setState(state);
    }

    /**
     * Gets current component state.
     */
    public Common.ComponentState getState() {
        return heartbeatManager.getState();
    }

    /**
     * Returns GladysClient for event publishing.
     */
    public GladysClient getClient() {
        return client;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private GladysClient client;
        private String componentId;
        private int heartbeatIntervalSeconds = 30;
        private final CommandDispatcher.Builder dispatcherBuilder = CommandDispatcher.builder();

        /**
         * Sets GladysClient (required).
         */
        public Builder client(GladysClient client) {
            this.client = client;
            return this;
        }

        /**
         * Sets component ID (required).
         */
        public Builder componentId(String componentId) {
            this.componentId = componentId;
            return this;
        }

        /**
         * Sets heartbeat interval in seconds.
         * Default: 30 seconds.
         */
        public Builder heartbeatInterval(int seconds) {
            this.heartbeatIntervalSeconds = seconds;
            return this;
        }

        /**
         * Registers START command handler.
         */
        public Builder onStart(CommandHandler<StartArgs> handler) {
            dispatcherBuilder.onStart(handler);
            return this;
        }

        /**
         * Registers STOP command handler.
         */
        public Builder onStop(CommandHandler<StopArgs> handler) {
            dispatcherBuilder.onStop(handler);
            return this;
        }

        /**
         * Registers PAUSE command handler.
         */
        public Builder onPause(SimpleCommandHandler handler) {
            dispatcherBuilder.onPause(handler);
            return this;
        }

        /**
         * Registers RESUME command handler.
         */
        public Builder onResume(SimpleCommandHandler handler) {
            dispatcherBuilder.onResume(handler);
            return this;
        }

        /**
         * Registers RELOAD command handler.
         */
        public Builder onReload(SimpleCommandHandler handler) {
            dispatcherBuilder.onReload(handler);
            return this;
        }

        /**
         * Registers HEALTH_CHECK command handler.
         */
        public Builder onHealthCheck(CommandHandler<HealthCheckArgs> handler) {
            dispatcherBuilder.onHealthCheck(handler);
            return this;
        }

        /**
         * Registers RECOVER command handler.
         */
        public Builder onRecover(CommandHandler<RecoverArgs> handler) {
            dispatcherBuilder.onRecover(handler);
            return this;
        }

        /**
         * Registers global error handler.
         */
        public Builder onCommandError(CommandErrorHandler handler) {
            dispatcherBuilder.onCommandError(handler);
            return this;
        }

        public SensorLifecycle build() {
            if (client == null) {
                throw new IllegalStateException("client is required");
            }
            if (componentId == null || componentId.isEmpty()) {
                throw new IllegalStateException("componentId is required");
            }
            return new SensorLifecycle(this);
        }
    }
}
```

### 8. HeartbeatManager Updates

Enhanced to dispatch commands from `HeartbeatResponse.pending_commands`.

```java
package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Sends periodic heartbeats to the orchestrator on a background thread.
 * Dispatches pending commands from HeartbeatResponse.
 */
public class HeartbeatManager {

    private static final Logger logger = Logger.getLogger(HeartbeatManager.class.getName());

    private final GladysClient client;
    private final String componentId;
    private final int intervalSeconds;
    private final ScheduledExecutorService scheduler;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile Common.ComponentState state = Common.ComponentState.COMPONENT_STATE_ACTIVE;
    private volatile String errorMessage = null;
    private CommandDispatcher dispatcher;

    public HeartbeatManager(GladysClient client, String componentId, int intervalSeconds) {
        this.client = client;
        this.componentId = componentId;
        this.intervalSeconds = intervalSeconds;
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "gladys-heartbeat-" + componentId);
            t.setDaemon(true);
            return t;
        });
    }

    /**
     * Sets command dispatcher for handling pending commands.
     * Must be called before start().
     */
    void setDispatcher(CommandDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    public void start() {
        if (running.compareAndSet(false, true)) {
            scheduler.scheduleAtFixedRate(this::sendHeartbeat, 0, intervalSeconds, TimeUnit.SECONDS);
        }
    }

    public void stop() {
        if (running.compareAndSet(true, false)) {
            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                    scheduler.shutdownNow();
                }
            } catch (InterruptedException e) {
                scheduler.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    public boolean isRunning() {
        return running.get();
    }

    public void setState(Common.ComponentState state) {
        this.state = state;
        this.errorMessage = null; // Clear error on explicit state change
    }

    public Common.ComponentState getState() {
        return state;
    }

    private void sendHeartbeat() {
        try {
            Orchestrator.HeartbeatResponse response = client.heartbeat(componentId, state, errorMessage);

            // Dispatch pending commands
            if (dispatcher != null && response.getPendingCommandsCount() > 0) {
                for (Orchestrator.PendingCommand pendingCommand : response.getPendingCommandsList()) {
                    dispatchCommand(pendingCommand);
                }
            }
        } catch (Exception e) {
            logger.log(Level.WARNING, "Heartbeat failed for " + componentId, e);
        }
    }

    private void dispatchCommand(Orchestrator.PendingCommand pendingCommand) {
        try {
            logger.info("Dispatching command: " + pendingCommand.getCommand() + " (id=" + pendingCommand.getCommandId() + ")");

            CommandDispatcher.StateAndError result = dispatcher.dispatch(
                    pendingCommand.getCommand(),
                    pendingCommand.getArgs(),
                    state
            );

            state = result.state;
            errorMessage = result.errorMessage;

            logger.info("Command completed: " + pendingCommand.getCommand() + " -> " + state);
        } catch (Exception e) {
            logger.log(Level.SEVERE, "Command dispatch failed: " + pendingCommand.getCommand(), e);
            state = Common.ComponentState.COMPONENT_STATE_ERROR;
            errorMessage = e.getMessage();
        }
    }
}
```

### 9. TestSensorHarness

Testing utility in `com.gladys.sensor.testing` package.

```java
package com.gladys.sensor.testing;

import com.gladys.sensor.*;
import com.google.protobuf.Struct;
import gladys.v1.Common;
import gladys.v1.Orchestrator;

/**
 * Test harness for sensor command handling.
 * Bypasses heartbeat loop and gRPC, dispatches commands directly.
 * Ships in main SDK artifact for use in sensor tests.
 */
public class TestSensorHarness {

    private final CommandDispatcher dispatcher;
    private Common.ComponentState currentState = Common.ComponentState.COMPONENT_STATE_ACTIVE;
    private String lastErrorMessage = null;

    /**
     * Creates test harness from CommandDispatcher.
     */
    public TestSensorHarness(CommandDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    /**
     * Dispatches command with args, returns new state.
     */
    public Common.ComponentState dispatch(Orchestrator.Command command, Struct args) {
        CommandDispatcher.StateAndError result = dispatcher.dispatch(command, args, currentState);
        currentState = result.state;
        lastErrorMessage = result.errorMessage;
        return currentState;
    }

    /**
     * Dispatches command with no args (PAUSE, RESUME, RELOAD).
     */
    public Common.ComponentState dispatch(Orchestrator.Command command) {
        return dispatch(command, Struct.getDefaultInstance());
    }

    /**
     * Returns current component state.
     */
    public Common.ComponentState getState() {
        return currentState;
    }

    /**
     * Returns last error message (populated on command failure).
     */
    public String getLastErrorMessage() {
        return lastErrorMessage;
    }

    /**
     * Resets state to ACTIVE and clears error message.
     */
    public void reset() {
        currentState = Common.ComponentState.COMPONENT_STATE_ACTIVE;
        lastErrorMessage = null;
    }
}
```

## Package Structure

```
com.gladys.sensor/
├── GladysClient.java              (updated - TimeoutConfig)
├── HeartbeatManager.java          (updated - add getState())
├── EventBuilder.java              (unchanged)
├── SensorRegistration.java        (unchanged)
├── TimeoutConfig.java             (new)
├── Intent.java                    (new)
├── CommandArgs.java               (new)
├── StartArgs.java                 (new)
├── StopArgs.java                  (new)
├── RecoverArgs.java               (new)
├── HealthCheckArgs.java           (new)
├── CommandHandler.java            (new)
├── SimpleCommandHandler.java      (new)
├── CommandErrorHandler.java       (new)
├── CommandDispatcher.java         (new)
├── SensorLifecycle.java           (new)
└── testing/
    └── TestSensorHarness.java     (new)
```

## Complete Example: Game State Sensor

Sensor that extends `GamePlugin` base class, proving no-inheritance-required pattern.

```java
package com.example.game;

import com.gladys.sensor.*;
import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Game state capture sensor.
 * Extends GamePlugin (simulating RuneLite constraint).
 * Uses SensorLifecycle via composition.
 */
public class GameStateSensor extends GamePlugin {

    private static final Logger logger = Logger.getLogger(GameStateSensor.class.getName());
    private static final String SENSOR_ID = "game-state-sensor-001";

    private GladysClient client;
    private SensorLifecycle lifecycle;
    private GameDriver gameDriver;
    private EventBuffer eventBuffer;
    private SensorConfig config;

    @Override
    public void onPluginStart() {
        // Initialize GLADyS client and lifecycle
        client = new GladysClient("localhost", 50051);

        // Register sensor
        Orchestrator.ComponentCapabilities capabilities = Orchestrator.ComponentCapabilities.newBuilder()
                .setSupportsEvents(true)
                .build();
        client.register(SENSOR_ID, "game-state", capabilities);

        // Build lifecycle with command handlers
        lifecycle = SensorLifecycle.builder()
                .client(client)
                .componentId(SENSOR_ID)
                .heartbeatInterval(30)
                .onStart(this::handleStart)
                .onStop(this::handleStop)
                .onPause(this::handlePause)
                .onResume(this::handleResume)
                .onReload(this::handleReload)
                .onHealthCheck(this::handleHealthCheck)
                .onRecover(this::handleRecover)
                .onCommandError(this::handleError)
                .build();

        // Start heartbeat (non-blocking)
        lifecycle.start();
        logger.info("Game state sensor started");
    }

    @Override
    public void onPluginStop() {
        if (lifecycle != null) {
            lifecycle.stop();
        }
        logger.info("Game state sensor stopped");
    }

    // Command handlers (all run on heartbeat thread - keep fast)

    private Common.ComponentState handleStart(StartArgs args) throws Exception {
        logger.info("START: dry_run=" + args.isDryRun() + ", config=" + args.getConfigOverride());

        if (!args.isDryRun()) {
            gameDriver = new GameDriver();
            gameDriver.connect();

            eventBuffer = new EventBuffer(client, SENSOR_ID);
            eventBuffer.start();
        }

        return null; // Accept default ACTIVE state
    }

    private Common.ComponentState handleStop(StopArgs args) throws Exception {
        logger.info("STOP: force=" + args.isForce() + ", timeout=" + args.getTimeoutSeconds());

        if (!args.isForce() && eventBuffer != null) {
            eventBuffer.flush();
        }

        if (gameDriver != null) {
            gameDriver.disconnect();
            gameDriver = null;
        }

        if (eventBuffer != null) {
            eventBuffer.stop();
            eventBuffer = null;
        }

        return null; // Accept default STOPPED state
    }

    private Common.ComponentState handlePause() {
        logger.info("PAUSE");
        if (eventBuffer != null) {
            eventBuffer.pause();
        }
        return null; // Accept default PAUSED state
    }

    private Common.ComponentState handleResume() {
        logger.info("RESUME");
        if (eventBuffer != null) {
            eventBuffer.resume();
        }
        return null; // Accept default ACTIVE state
    }

    private Common.ComponentState handleReload() {
        logger.info("RELOAD");
        config = SensorConfig.load();
        if (gameDriver != null) {
            gameDriver.setPollingInterval(config.getPollingIntervalMs());
            gameDriver.setEventFilters(config.getEventFilters());
        }
        return null; // Accept default ACTIVE state
    }

    private Common.ComponentState handleHealthCheck(HealthCheckArgs args) throws Exception {
        logger.info("HEALTH_CHECK: deep=" + args.isDeep());

        if (gameDriver == null) {
            throw new IllegalStateException("Game driver not initialized");
        }

        if (!gameDriver.ping(args.getTimeoutMs())) {
            throw new IllegalStateException("Game driver ping failed");
        }

        if (args.isDeep() && eventBuffer != null) {
            int queueDepth = eventBuffer.getQueueDepth();
            if (queueDepth > 1000) {
                throw new IllegalStateException("Event queue depth too high: " + queueDepth);
            }
        }

        return null; // Health check passed, state unchanged
    }

    private Common.ComponentState handleRecover(RecoverArgs args) throws Exception {
        logger.info("RECOVER: strategy=" + args.getStrategy() + ", max_retries=" + args.getMaxRetries());

        int retries = 0;
        Exception lastException = null;

        while (retries < args.getMaxRetries()) {
            try {
                switch (args.getStrategy()) {
                    case "restart":
                        if (gameDriver != null) {
                            gameDriver.disconnect();
                        }
                        gameDriver = new GameDriver();
                        gameDriver.connect();
                        break;

                    case "reconnect":
                        if (gameDriver != null) {
                            gameDriver.reconnect();
                        }
                        break;

                    case "reset":
                        if (gameDriver != null) {
                            gameDriver.reset();
                        }
                        break;

                    default:
                        throw new IllegalArgumentException("Unknown strategy: " + args.getStrategy());
                }

                logger.info("Recovery successful on attempt " + (retries + 1));
                return null; // Accept default ACTIVE state

            } catch (Exception e) {
                lastException = e;
                retries++;
                logger.warning("Recovery attempt " + retries + " failed: " + e.getMessage());
            }
        }

        throw new Exception("Recovery failed after " + args.getMaxRetries() + " attempts", lastException);
    }

    private Common.ComponentState handleError(Orchestrator.Command command, Exception exception, Common.ComponentState currentState) {
        logger.severe("Command failed: " + command + " - " + exception.getMessage());

        // For STOP failures, force transition to STOPPED
        if (command == Orchestrator.Command.COMMAND_STOP) {
            return Common.ComponentState.COMPONENT_STATE_STOPPED;
        }

        // Accept ERROR state for other commands
        return null;
    }
}
```

## Complete Test Example

JUnit 5 tests using `TestSensorHarness`.

```java
package com.example.game;

import com.gladys.sensor.*;
import com.gladys.sensor.testing.TestSensorHarness;
import gladys.v1.Common;
import gladys.v1.Orchestrator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GameStateSensorTest {

    private TestSensorHarness harness;
    private boolean startCalled;
    private boolean dryRunMode;
    private boolean stopCalled;
    private boolean forceStop;

    @BeforeEach
    void setUp() {
        startCalled = false;
        dryRunMode = false;
        stopCalled = false;
        forceStop = false;

        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> {
                    startCalled = true;
                    dryRunMode = args.isDryRun();
                    return null; // Accept ACTIVE
                })
                .onStop(args -> {
                    stopCalled = true;
                    forceStop = args.isForce();
                    return null; // Accept STOPPED
                })
                .build();

        harness = new TestSensorHarness(dispatcher);
    }

    @Test
    void testStartSetsActiveState() {
        Common.ComponentState state = harness.dispatch(
                Orchestrator.Command.COMMAND_START,
                StartArgs.test().getStruct()
        );

        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, state);
        assertTrue(startCalled);
        assertFalse(dryRunMode);
    }

    @Test
    void testStartWithDryRunDoesNotStartDrivers() {
        harness.dispatch(
                Orchestrator.Command.COMMAND_START,
                StartArgs.testDryRun().getStruct()
        );

        assertTrue(startCalled);
        assertTrue(dryRunMode);
    }

    @Test
    void testStopWithForceSkipsFlush() {
        harness.dispatch(Orchestrator.Command.COMMAND_START);
        Common.ComponentState state = harness.dispatch(
                Orchestrator.Command.COMMAND_STOP,
                StopArgs.testForce().getStruct()
        );

        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, state);
        assertTrue(stopCalled);
        assertTrue(forceStop);
    }

    @Test
    void testHandlerFailureSetsErrorState() {
        CommandDispatcher failingDispatcher = CommandDispatcher.builder()
                .onStart(args -> {
                    throw new RuntimeException("Connection failed");
                })
                .build();

        TestSensorHarness failHarness = new TestSensorHarness(failingDispatcher);
        Common.ComponentState state = failHarness.dispatch(Orchestrator.Command.COMMAND_START);

        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, state);
        assertEquals("Connection failed", failHarness.getLastErrorMessage());
    }

    @Test
    void testHealthCheckFailureDoesNotSetError() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onHealthCheck(args -> {
                    throw new IllegalStateException("Driver offline");
                })
                .build();

        TestSensorHarness testHarness = new TestSensorHarness(dispatcher);
        Common.ComponentState state = testHarness.dispatch(Orchestrator.Command.COMMAND_HEALTH_CHECK);

        // State should remain ACTIVE (not ERROR)
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, state);
        assertNull(testHarness.getLastErrorMessage());
    }
}
```

## Quality Checklist

- [x] All 7 commands handled in example sensor — 8 handler methods (7 commands + 1 error handler) totaling 119 lines
- [x] Zero if/elif dispatch chains in sensor code — CommandDispatcher.dispatch() uses switch internally, sensors register lambdas
- [x] Each test is <15 lines — Tests range from 7-13 lines
- [x] Builder patterns feel natural — Like gRPC's ManagedChannelBuilder, chained handler registration
- [x] Functional interfaces support Java 8+ lambdas — CommandHandler<T>, SimpleCommandHandler, CommandErrorHandler
- [x] AutoCloseable where appropriate — GladysClient implements AutoCloseable
- [x] Thread safety documented — JavaDoc states handlers run on heartbeat thread, should be fast

## Stub Classes in Example

The game state sensor example uses these domain-specific classes (not part of SDK):

```java
// Base class representing RuneLite plugin constraint
abstract class GamePlugin {
    public abstract void onPluginStart();
    public abstract void onPluginStop();
}

// Game driver for connecting to game
class GameDriver {
    void connect() throws Exception { /* ... */ }
    void disconnect() { /* ... */ }
    void reconnect() throws Exception { /* ... */ }
    void reset() throws Exception { /* ... */ }
    boolean ping(int timeoutMs) { /* ... */ }
    void setPollingInterval(int ms) { /* ... */ }
    void setEventFilters(String filters) { /* ... */ }
}

// Event buffer for batching events
class EventBuffer {
    EventBuffer(GladysClient client, String sensorId) { /* ... */ }
    void start() { /* ... */ }
    void stop() { /* ... */ }
    void pause() { /* ... */ }
    void resume() { /* ... */ }
    void flush() { /* ... */ }
    int getQueueDepth() { /* ... */ }
}

// Sensor configuration
class SensorConfig {
    static SensorConfig load() { /* ... */ }
    int getPollingIntervalMs() { /* ... */ }
    String getEventFilters() { /* ... */ }
}
```

## Proto Updates Required

Add `error_message` field to `HeartbeatRequest`:

```protobuf
message HeartbeatRequest {
    string component_id = 1;
    ComponentState state = 2;
    string error_message = 3;  // Populated when state is ERROR
    RequestMetadata metadata = 15;
}
```

Update `docs/codebase/SENSOR_ARCHITECTURE.md` and ADR-0005 to document error_message field usage.

## Implementation Notes

1. **HeartbeatManager.setDispatcher()** is package-private - only SensorLifecycle can call it
2. **CommandDispatcher.dispatch()** returns package-private `StateAndError` class
3. **Test harness** requires building CommandDispatcher directly (not via SensorLifecycle.Builder)
4. **Error message** is cleared on explicit `setState()` calls (only populated by command failures)
5. **HEALTH_CHECK exceptions** do NOT populate error_message field
6. **Timeout configuration** applies per-call via `withDeadlineAfter()` on blocking stub
