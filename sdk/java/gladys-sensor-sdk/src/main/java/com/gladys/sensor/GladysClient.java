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
 * registration, and heartbeat with configurable timeouts.
 */
public class GladysClient implements AutoCloseable {

    private final ManagedChannel channel;
    private final OrchestratorServiceGrpc.OrchestratorServiceBlockingStub blockingStub;
    private final TimeoutConfig timeoutConfig;

    /**
     * Create a client with default timeout configuration.
     *
     * @param host Orchestrator host
     * @param port Orchestrator port
     */
    public GladysClient(String host, int port) {
        this(host, port, TimeoutConfig.defaults());
    }

    /**
     * Create a client with custom timeout configuration.
     *
     * @param host Orchestrator host
     * @param port Orchestrator port
     * @param timeoutConfig Timeout configuration for gRPC calls
     */
    public GladysClient(String host, int port, TimeoutConfig timeoutConfig) {
        this(ManagedChannelBuilder.forAddress(host, port)
                .usePlaintext()
                .build(), timeoutConfig);
    }

    // Package-private for testing with InProcessChannel
    GladysClient(ManagedChannel channel) {
        this(channel, TimeoutConfig.defaults());
    }

    GladysClient(ManagedChannel channel, TimeoutConfig timeoutConfig) {
        this.channel = channel;
        this.timeoutConfig = timeoutConfig;
        this.blockingStub = OrchestratorServiceGrpc.newBlockingStub(channel);
    }

    /**
     * Publish a single event to the orchestrator.
     *
     * @param event The event to publish
     * @return EventAck containing acknowledgment and routing information
     */
    public Orchestrator.EventAck publishEvent(Common.Event event) {
        Orchestrator.PublishEventRequest request = Orchestrator.PublishEventRequest.newBuilder()
                .setEvent(event)
                .setMetadata(event.getMetadata())
                .build();

        OrchestratorServiceGrpc.OrchestratorServiceBlockingStub stub = blockingStub;
        if (timeoutConfig.publishEventMs > 0) {
            stub = stub.withDeadlineAfter(timeoutConfig.publishEventMs, TimeUnit.MILLISECONDS);
        }

        Orchestrator.PublishEventResponse response = stub.publishEvent(request);
        return response.getAck();
    }

    /**
     * Publish multiple events in a batch.
     *
     * @param events List of events to publish
     * @return PublishEventsResponse containing accepted count and any errors
     */
    public Orchestrator.PublishEventsResponse publishEvents(List<Common.Event> events) {
        Common.RequestMetadata metadata = Common.RequestMetadata.newBuilder()
                .setRequestId(UUID.randomUUID().toString())
                .setTimestampMs(System.currentTimeMillis())
                .build();

        Orchestrator.PublishEventsRequest request = Orchestrator.PublishEventsRequest.newBuilder()
                .addAllEvents(events)
                .setMetadata(metadata)
                .build();

        OrchestratorServiceGrpc.OrchestratorServiceBlockingStub stub = blockingStub;
        if (timeoutConfig.publishEventMs > 0) {
            stub = stub.withDeadlineAfter(timeoutConfig.publishEventMs, TimeUnit.MILLISECONDS);
        }

        return stub.publishEvents(request);
    }

    /**
     * Register a component with the orchestrator.
     *
     * @param sensorId Unique sensor identifier
     * @param sensorType Sensor type descriptor
     * @param capabilities Component capabilities
     * @return RegisterResponse indicating success or failure
     */
    public Orchestrator.RegisterResponse register(String sensorId, String sensorType,
                                                   Orchestrator.ComponentCapabilities capabilities) {
        return register(sensorId, sensorType, "", capabilities);
    }

    /**
     * Register a component with the orchestrator including address.
     *
     * @param sensorId Unique sensor identifier
     * @param sensorType Sensor type descriptor
     * @param address Component network address (optional)
     * @param capabilities Component capabilities
     * @return RegisterResponse indicating success or failure
     */
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

        OrchestratorServiceGrpc.OrchestratorServiceBlockingStub stub = blockingStub;
        if (timeoutConfig.registerMs > 0) {
            stub = stub.withDeadlineAfter(timeoutConfig.registerMs, TimeUnit.MILLISECONDS);
        }

        return stub.registerComponent(request);
    }

    /**
     * Send a heartbeat with default ACTIVE state.
     *
     * @param componentId Component identifier
     * @return HeartbeatResponse containing pending commands
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId) {
        return heartbeat(componentId, Common.ComponentState.COMPONENT_STATE_ACTIVE, null);
    }

    /**
     * Send a heartbeat with specific state.
     *
     * @param componentId Component identifier
     * @param state Current component state
     * @return HeartbeatResponse containing pending commands
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId, Common.ComponentState state) {
        return heartbeat(componentId, state, null);
    }

    /**
     * Send a heartbeat with state and optional error message.
     *
     * @param componentId Component identifier
     * @param state Current component state
     * @param errorMessage Error message (populated when state is ERROR)
     * @return HeartbeatResponse containing pending commands
     */
    public Orchestrator.HeartbeatResponse heartbeat(String componentId, Common.ComponentState state, String errorMessage) {
        Orchestrator.HeartbeatRequest.Builder requestBuilder = Orchestrator.HeartbeatRequest.newBuilder()
                .setComponentId(componentId)
                .setState(state)
                .setMetadata(Common.RequestMetadata.newBuilder()
                        .setRequestId(UUID.randomUUID().toString())
                        .setTimestampMs(System.currentTimeMillis())
                        .build());

        if (errorMessage != null && !errorMessage.isEmpty()) {
            requestBuilder.setErrorMessage(errorMessage);
        }

        OrchestratorServiceGrpc.OrchestratorServiceBlockingStub stub = blockingStub;
        if (timeoutConfig.heartbeatMs > 0) {
            stub = stub.withDeadlineAfter(timeoutConfig.heartbeatMs, TimeUnit.MILLISECONDS);
        }

        return stub.heartbeat(requestBuilder.build());
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
