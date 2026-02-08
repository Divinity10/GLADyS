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

import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class GladysClientTest {

    private Server server;
    private ManagedChannel channel;
    private GladysClient client;

    private final OrchestratorServiceGrpc.OrchestratorServiceImplBase serviceImpl =
            new OrchestratorServiceGrpc.OrchestratorServiceImplBase() {
                @Override
                public void publishEvent(Orchestrator.PublishEventRequest request,
                                          StreamObserver<Orchestrator.PublishEventResponse> responseObserver) {
                    responseObserver.onNext(Orchestrator.PublishEventResponse.newBuilder()
                            .setAck(Orchestrator.EventAck.newBuilder()
                                    .setEventId(request.getEvent().getId())
                                    .setAccepted(true)
                                    .build())
                            .build());
                    responseObserver.onCompleted();
                }

                @Override
                public void publishEvents(Orchestrator.PublishEventsRequest request,
                                           StreamObserver<Orchestrator.PublishEventsResponse> responseObserver) {
                    responseObserver.onNext(Orchestrator.PublishEventsResponse.newBuilder()
                            .setAcceptedCount(request.getEventsCount())
                            .build());
                    responseObserver.onCompleted();
                }
            };

    @BeforeEach
    void setUp() throws Exception {
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
    void testPublishEventReturnsAck() {
        Common.Event event = new EventBuilder("test-sensor")
                .text("test event")
                .build();

        Orchestrator.EventAck ack = client.publishEvent(event);

        assertNotNull(ack);
        assertEquals(event.getId(), ack.getEventId());
        assertTrue(ack.getAccepted());
    }

    @Test
    void testPublishEventsReturnsSummary() {
        Common.Event event1 = new EventBuilder("test-sensor")
                .text("event one")
                .build();
        Common.Event event2 = new EventBuilder("test-sensor")
                .text("event two")
                .build();

        Orchestrator.PublishEventsResponse response = client.publishEvents(Arrays.asList(event1, event2));

        assertEquals(2, response.getAcceptedCount());
        assertEquals(0, response.getErrorsCount());
    }
}
