package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;
import gladys.v1.OrchestratorServiceGrpc;
import gladys.types.Types;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlowStrategyTest {
    private final AtomicInteger publishEventCount = new AtomicInteger();
    private Server server;
    private ManagedChannel channel;
    private GladysClient client;

    private final OrchestratorServiceGrpc.OrchestratorServiceImplBase serviceImpl =
            new OrchestratorServiceGrpc.OrchestratorServiceImplBase() {
                @Override
                public void publishEvent(Orchestrator.PublishEventRequest request,
                                          StreamObserver<Orchestrator.PublishEventResponse> responseObserver) {
                    publishEventCount.incrementAndGet();
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
                    publishEventCount.addAndGet(request.getEventsCount());
                    responseObserver.onNext(Orchestrator.PublishEventsResponse.newBuilder()
                            .setAcceptedCount(request.getEventsCount())
                            .build());
                    responseObserver.onCompleted();
                }
            };

    @BeforeEach
    void setUp() throws Exception {
        publishEventCount.set(0);
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
    void testNoOpAlwaysAllows() {
        NoOpStrategy strategy = new NoOpStrategy();
        Common.Event event = new EventBuilder("sensor").text("test").build();
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
    }

    @Test
    void test_noop_available_tokens_returns_max() {
        NoOpStrategy strategy = new NoOpStrategy();
        assertEquals(Integer.MAX_VALUE, strategy.availableTokens());
    }

    @Test
    void test_noop_consume_is_noop() {
        NoOpStrategy strategy = new NoOpStrategy();
        int before = strategy.availableTokens();
        strategy.consume(10);
        assertEquals(before, strategy.availableTokens());
    }

    @Test
    void testRateLimitAllowsWithinBudget() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(5, 1, now::get);
        Common.Event event = new EventBuilder("sensor").text("test").build();

        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
    }

    @Test
    void testRateLimitBlocksOverBudget() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(5, 1, now::get);
        Common.Event event = new EventBuilder("sensor").text("test").build();

        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertFalse(strategy.shouldPublish(event));
    }

    @Test
    void testRateLimitRefillsOverTime() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(2, 2, now::get);
        Common.Event event = new EventBuilder("sensor").text("test").build();

        assertTrue(strategy.shouldPublish(event));
        assertTrue(strategy.shouldPublish(event));
        assertFalse(strategy.shouldPublish(event));

        now.set(1_100_000_000L);
        assertTrue(strategy.shouldPublish(event));
    }

    @Test
    void test_rate_limit_available_tokens_reflects_budget() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(5, 1, now::get);
        Common.Event event = new EventBuilder("sensor").text("test").build();

        strategy.shouldPublish(event);
        strategy.shouldPublish(event);

        assertEquals(3, strategy.availableTokens());
    }

    @Test
    void test_rate_limit_consume_decrements_tokens() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(10, 1, now::get);
        strategy.consume(5);
        assertEquals(5, strategy.availableTokens());
    }

    @Test
    void testRateLimitRejectsZeroMaxEvents() {
        assertThrows(IllegalArgumentException.class, () -> new RateLimitStrategy(0, 1));
    }

    @Test
    void testRateLimitRejectsZeroWindow() {
        assertThrows(IllegalArgumentException.class, () -> new RateLimitStrategy(1, 0));
    }

    @Test
    void testRateLimitRejectsNegativeValues() {
        assertThrows(IllegalArgumentException.class, () -> new RateLimitStrategy(-1, 1));
        assertThrows(IllegalArgumentException.class, () -> new RateLimitStrategy(1, -1));
    }

    @Test
    void testCreateNoneStrategy() {
        FlowStrategy strategy = FlowStrategyFactory.create(Map.of("strategy", "none"));
        assertInstanceOf(NoOpStrategy.class, strategy);
    }

    @Test
    void testCreateRateLimitStrategy() {
        Map<String, Object> config = new HashMap<>();
        config.put("strategy", "rate_limit");
        config.put("max_events", 5);
        config.put("window_seconds", 1);
        FlowStrategy strategy = FlowStrategyFactory.create(config);
        assertInstanceOf(RateLimitStrategy.class, strategy);
    }

    @Test
    void testCreateUnknownFallsBackToNoOp() {
        FlowStrategy strategy = FlowStrategyFactory.create(Map.of("strategy", "mystery"));
        assertInstanceOf(NoOpStrategy.class, strategy);
    }

    @Test
    void testCreateDefaultIsNoOp() {
        FlowStrategy strategy = FlowStrategyFactory.create(new HashMap<>());
        assertInstanceOf(NoOpStrategy.class, strategy);
    }

    @Test
    void testEmitWithNoOpStrategyPublishes() {
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, new NoOpStrategy());
        boolean result = dispatcher.emit(new EventBuilder("sensor").text("test").build());
        assertTrue(result);
        assertEquals(1, publishEventCount.get());
        dispatcher.shutdown();
    }

    @Test
    void testEmitWithRateLimitBlocksExcess() {
        AtomicLong now = new AtomicLong(0L);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                new RateLimitStrategy(1, 10, now::get)
        );

        boolean first = dispatcher.emit(new EventBuilder("sensor").text("first").build());
        boolean second = dispatcher.emit(new EventBuilder("sensor").text("second").build());

        assertTrue(first);
        assertFalse(second);
        assertEquals(1, publishEventCount.get());
        dispatcher.shutdown();
    }

    @Test
    void testEmitThreatBypassesRateLimit() {
        AtomicLong now = new AtomicLong(0L);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                new RateLimitStrategy(1, 10, now::get)
        );

        dispatcher.emit(new EventBuilder("sensor").text("normal").build());
        Common.Event threat = new EventBuilder("sensor")
                .text("danger")
                .build()
                .toBuilder()
                .setSalience(Types.SalienceResult.newBuilder().setThreat(1.0f).build())
                .build();
        boolean result = dispatcher.emit(threat);

        assertTrue(result);
        assertEquals(2, publishEventCount.get());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_returns_true_when_published() {
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, new NoOpStrategy());
        boolean result = dispatcher.emit(new EventBuilder("sensor").text("ok").build());
        assertTrue(result);
        dispatcher.shutdown();
    }

    @Test
    void test_emit_returns_false_when_suppressed() {
        AtomicLong now = new AtomicLong(0L);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                new RateLimitStrategy(1, 10, now::get)
        );

        dispatcher.emit(new EventBuilder("sensor").text("first").build());
        boolean result = dispatcher.emit(new EventBuilder("sensor").text("blocked").build());
        assertFalse(result);
        dispatcher.shutdown();
    }

    @Test
    void test_emit_threat_returns_true_when_rate_limited() {
        AtomicLong now = new AtomicLong(0L);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                new RateLimitStrategy(1, 10, now::get)
        );

        dispatcher.emit(new EventBuilder("sensor").text("first").build());
        Common.Event threat = new EventBuilder("sensor")
                .text("danger")
                .build()
                .toBuilder()
                .setSalience(Types.SalienceResult.newBuilder().setThreat(1.0f).build())
                .build();
        boolean result = dispatcher.emit(threat);
        assertTrue(result);
        dispatcher.shutdown();
    }

    @Test
    void test_events_filtered_increments_on_suppression() {
        AtomicLong now = new AtomicLong(0L);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                new RateLimitStrategy(1, 10, now::get)
        );

        dispatcher.emit(new EventBuilder("sensor").text("first").build());
        dispatcher.emit(new EventBuilder("sensor").text("blocked").build());
        assertEquals(1, dispatcher.getEventsFiltered());
        dispatcher.shutdown();
    }

    @Test
    void test_events_published_increments_on_send() {
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, new NoOpStrategy());
        dispatcher.emit(new EventBuilder("sensor").text("sent").build());
        assertEquals(1, dispatcher.getEventsPublished());
        dispatcher.shutdown();
    }

    @Test
    void test_counters_zero_initially() {
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, new NoOpStrategy());
        assertEquals(0, dispatcher.getEventsFiltered());
        assertEquals(0, dispatcher.getEventsPublished());
        dispatcher.shutdown();
    }

    @Test
    void testSetStrategyReplacesStrategy() {
        FlowStrategy denyStrategy = new FlowStrategy() {
            @Override
            public boolean shouldPublish(Common.Event event) {
                return false;
            }

            @Override
            public int availableTokens() {
                return 0;
            }

            @Override
            public void consume(int n) {
                // no-op
            }
        };

        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, denyStrategy);

        dispatcher.emit(new EventBuilder("sensor").text("blocked").build());
        dispatcher.setStrategy(new NoOpStrategy());
        dispatcher.emit(new EventBuilder("sensor").text("allowed").build());

        assertEquals(1, publishEventCount.get());
        dispatcher.shutdown();
    }
}
