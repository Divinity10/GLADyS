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
    private final OrchestratorServiceGrpc.OrchestratorServiceBlockingStub blockingStub;

    public GladysClient(String host, int port) {
        this(ManagedChannelBuilder.forAddress(host, port)
                .usePlaintext()
                .build());
    }

    // Package-private for testing with InProcessChannel
    GladysClient(ManagedChannel channel) {
        this.channel = channel;
        this.blockingStub = OrchestratorServiceGrpc.newBlockingStub(channel);
    }

    public Orchestrator.EventAck publishEvent(Common.Event event) {
        Orchestrator.PublishEventRequest request = Orchestrator.PublishEventRequest.newBuilder()
                .setEvent(event)
                .setMetadata(event.getMetadata())
                .build();
        Orchestrator.PublishEventResponse response = blockingStub.publishEvent(request);
        return response.getAck();
    }

    public List<Orchestrator.EventAck> publishEvents(List<Common.Event> events) {
        Common.RequestMetadata metadata = Common.RequestMetadata.newBuilder()
                .setRequestId(UUID.randomUUID().toString())
                .setTimestampMs(System.currentTimeMillis())
                .build();

        Orchestrator.PublishEventsRequest request = Orchestrator.PublishEventsRequest.newBuilder()
                .addAllEvents(events)
                .setMetadata(metadata)
                .build();
        Orchestrator.PublishEventsResponse response = blockingStub.publishEvents(request);
        return response.getAcksList();
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
        return blockingStub.registerComponent(request);
    }

    public Orchestrator.HeartbeatResponse heartbeat(String componentId) {
        Orchestrator.HeartbeatRequest request = Orchestrator.HeartbeatRequest.newBuilder()
                .setComponentId(componentId)
                .setState(Common.ComponentState.COMPONENT_STATE_ACTIVE)
                .setMetadata(Common.RequestMetadata.newBuilder()
                        .setRequestId(UUID.randomUUID().toString())
                        .setTimestampMs(System.currentTimeMillis())
                        .build())
                .build();
        return blockingStub.heartbeat(request);
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
