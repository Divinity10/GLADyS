package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;
import gladys.v1.OrchestratorServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class HeartbeatManagerTest {

    private Server server;
    private ManagedChannel channel;
    private GladysClient client;
    private final AtomicInteger heartbeatCount = new AtomicInteger(0);
    private final CopyOnWriteArrayList<Common.ComponentState> receivedStates = new CopyOnWriteArrayList<>();

    private final OrchestratorServiceGrpc.OrchestratorServiceImplBase serviceImpl =
            new OrchestratorServiceGrpc.OrchestratorServiceImplBase() {
                @Override
                public void heartbeat(Orchestrator.HeartbeatRequest request,
                                       StreamObserver<Orchestrator.HeartbeatResponse> responseObserver) {
                    heartbeatCount.incrementAndGet();
                    receivedStates.add(request.getState());
                    responseObserver.onNext(Orchestrator.HeartbeatResponse.newBuilder()
                            .setAcknowledged(true)
                            .build());
                    responseObserver.onCompleted();
                }
            };

    @BeforeEach
    void setUp() throws Exception {
        heartbeatCount.set(0);
        receivedStates.clear();
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(serviceImpl)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        client = new GladysClient(channel);
    }

    @AfterEach
    void tearDown() {
        client.close();
        server.shutdownNow();
    }

    @Test
    void testHeartbeatSendsPeriodicRequests() throws InterruptedException {
        HeartbeatManager hb = new HeartbeatManager(client, "test-sensor", 1);
        hb.start();

        // Wait for at least 2 heartbeats (initial + 1 periodic)
        Thread.sleep(2500);
        hb.stop();

        assertTrue(heartbeatCount.get() >= 2,
                "Expected at least 2 heartbeats, got " + heartbeatCount.get());
    }

    @Test
    void testSetStateSendsUpdatedState() throws InterruptedException {
        HeartbeatManager hb = new HeartbeatManager(client, "test-sensor", 1);
        hb.start();

        // Let initial heartbeat fire (ACTIVE by default)
        Thread.sleep(500);
        assertTrue(receivedStates.size() >= 1, "Expected at least 1 heartbeat");
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, receivedStates.get(0));

        // Change state and wait for next heartbeat
        hb.setState(Common.ComponentState.COMPONENT_STATE_PAUSED);
        Thread.sleep(1500);
        hb.stop();

        // Verify at least one heartbeat was sent with PAUSED state
        boolean foundPaused = receivedStates.stream()
                .anyMatch(s -> s == Common.ComponentState.COMPONENT_STATE_PAUSED);
        assertTrue(foundPaused, "Expected at least one heartbeat with PAUSED state, got: " + receivedStates);
    }

    @Test
    void testHeartbeatStopsCleanly() throws InterruptedException {
        HeartbeatManager hb = new HeartbeatManager(client, "test-sensor", 1);
        hb.start();
        assertTrue(hb.isRunning());

        // Let one heartbeat fire
        Thread.sleep(500);
        hb.stop();

        assertFalse(hb.isRunning());

        // Record count after stop, wait, verify no more heartbeats
        int countAfterStop = heartbeatCount.get();
        Thread.sleep(2000);
        assertEquals(countAfterStop, heartbeatCount.get(),
                "Heartbeats should not fire after stop()");
    }
}
