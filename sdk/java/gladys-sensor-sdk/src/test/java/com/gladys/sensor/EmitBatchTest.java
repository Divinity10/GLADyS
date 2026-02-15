package com.gladys.sensor;

import com.google.protobuf.Value;
import gladys.types.Types;
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

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EmitBatchTest {
    private final AtomicInteger publishEventCount = new AtomicInteger();
    private final List<Common.Event> publishedEvents = new ArrayList<>();
    private Server server;
    private ManagedChannel channel;
    private GladysClient client;

    private final OrchestratorServiceGrpc.OrchestratorServiceImplBase serviceImpl =
            new OrchestratorServiceGrpc.OrchestratorServiceImplBase() {
                @Override
                public void publishEvent(Orchestrator.PublishEventRequest request,
                                         StreamObserver<Orchestrator.PublishEventResponse> responseObserver) {
                    publishEventCount.incrementAndGet();
                    publishedEvents.add(request.getEvent());
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
                    publishedEvents.addAll(request.getEventsList());
                    responseObserver.onNext(Orchestrator.PublishEventsResponse.newBuilder()
                            .setAcceptedCount(request.getEventsCount())
                            .build());
                    responseObserver.onCompleted();
                }
            };

    @BeforeEach
    void setUp() throws Exception {
        publishEventCount.set(0);
        publishedEvents.clear();
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
    void test_emit_batch_empty_list() {
        BudgetStrategy strategy = new BudgetStrategy(10);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of());

        assertEquals(new EmitResult(0, 0), result);
        assertEquals(0, strategy.availableCalls);
        assertEquals(List.of(), strategy.consumeCalls);
        assertEquals(0, publishEventCount.get());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_all_threats() {
        BudgetStrategy strategy = new BudgetStrategy(0);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                threatEvent("t1"),
                threatEvent("t2")
        ));

        assertEquals(new EmitResult(2, 0), result);
        assertEquals(0, strategy.availableCalls);
        assertEquals(List.of(), strategy.consumeCalls);
        assertEquals(List.of("t1", "t2"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_all_within_budget() {
        BudgetStrategy strategy = new BudgetStrategy(3);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 1),
                event("b", 2),
                event("c", 3)
        ));

        assertEquals(new EmitResult(3, 0), result);
        assertEquals(List.of(3), strategy.consumeCalls);
        assertEquals(List.of("a", "b", "c"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_zero_budget() {
        BudgetStrategy strategy = new BudgetStrategy(0);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                threatEvent("t"),
                event("a", 1),
                event("b", 2)
        ));

        assertEquals(new EmitResult(1, 2), result);
        assertEquals(2, dispatcher.getEventsFiltered());
        assertEquals(List.of(), strategy.consumeCalls);
        assertEquals(List.of("t"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_single_event() {
        BudgetStrategy strategy = new BudgetStrategy(1);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(event("single", 1)));

        assertEquals(new EmitResult(1, 0), result);
        assertEquals(List.of(1), strategy.consumeCalls);
        assertEquals(1, publishEventCount.get());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_fifo_when_no_priority_fn() {
        BudgetStrategy strategy = new BudgetStrategy(2);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 1),
                event("b", 2),
                event("c", 3)
        ));

        assertEquals(new EmitResult(2, 1), result);
        assertEquals(List.of("a", "b"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_priority_fn_selects_top_n() {
        BudgetStrategy strategy = new BudgetStrategy(2);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                strategy,
                this::priority
        );

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 1),
                event("b", 10),
                event("c", 5)
        ));

        assertEquals(new EmitResult(2, 1), result);
        assertEquals(List.of("b", "c"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_priority_fn_preserves_order() {
        BudgetStrategy strategy = new BudgetStrategy(2);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                strategy,
                this::priority
        );

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 5),
                event("b", 1),
                event("c", 10)
        ));

        assertEquals(new EmitResult(2, 1), result);
        assertEquals(List.of("a", "c"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_equal_priority_preserves_order() {
        BudgetStrategy strategy = new BudgetStrategy(2);
        EventDispatcher dispatcher = new EventDispatcher(
                client,
                "sensor",
                0,
                true,
                strategy,
                event -> 1.0
        );

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 1),
                event("b", 1),
                event("c", 1)
        ));

        assertEquals(new EmitResult(2, 1), result);
        assertEquals(List.of("a", "b"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_threats_bypass_budget() {
        BudgetStrategy strategy = new BudgetStrategy(0);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                threatEvent("t1"),
                event("a", 1),
                threatEvent("t2"),
                event("b", 2)
        ));

        assertEquals(new EmitResult(2, 2), result);
        assertEquals(List.of("t1", "t2"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_threats_dont_consume_tokens() {
        AtomicLong now = new AtomicLong(0L);
        RateLimitStrategy strategy = new RateLimitStrategy(5, 10, now::get);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);
        List<Common.Event> events = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            events.add(threatEvent("t" + i));
        }

        int before = strategy.availableTokens();
        EmitResult result = dispatcher.emitBatch(events);
        int after = strategy.availableTokens();

        assertEquals(new EmitResult(10, 0), result);
        assertEquals(5, before);
        assertEquals(5, after);
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_mixed_threats_and_candidates() {
        BudgetStrategy strategy = new BudgetStrategy(1);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                threatEvent("t1"),
                event("a", 1),
                event("b", 2),
                threatEvent("t2")
        ));

        assertEquals(new EmitResult(3, 1), result);
        assertEquals(List.of("t1", "a", "t2"), labels());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_updates_events_filtered() {
        BudgetStrategy strategy = new BudgetStrategy(1);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                event("a", 1),
                event("b", 2),
                event("c", 3)
        ));

        assertEquals(new EmitResult(1, 2), result);
        assertEquals(2, dispatcher.getEventsFiltered());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_batch_updates_events_published() {
        BudgetStrategy strategy = new BudgetStrategy(1);
        EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);

        EmitResult result = dispatcher.emitBatch(List.of(
                threatEvent("t"),
                event("a", 1),
                event("b", 2)
        ));

        assertEquals(new EmitResult(2, 1), result);
        assertEquals(2, dispatcher.getEventsPublished());
        dispatcher.shutdown();
    }

    @Test
    void test_emit_result_sent_plus_suppressed_equals_total() {
        List<Scenario> scenarios = List.of(
                new Scenario(0, List.of()),
                new Scenario(0, List.of(event("a", 1), event("b", 2), threatEvent("t"))),
                new Scenario(2, List.of(event("a", 1), event("b", 2), event("c", 3))),
                new Scenario(1, List.of(threatEvent("t"), event("a", 1), event("b", 2)))
        );

        for (Scenario scenario : scenarios) {
            BudgetStrategy strategy = new BudgetStrategy(scenario.budget);
            EventDispatcher dispatcher = new EventDispatcher(client, "sensor", 0, true, strategy);
            EmitResult result = dispatcher.emitBatch(scenario.events);
            assertEquals(scenario.events.size(), result.sent() + result.suppressed());
            dispatcher.shutdown();
        }
    }

    private Common.Event event(String label, double priority) {
        return new EventBuilder("sensor")
                .text(label)
                .structured(Map.of("priority", priority))
                .build();
    }

    private Common.Event threatEvent(String label) {
        return event(label, 0).toBuilder()
                .setSalience(Types.SalienceResult.newBuilder().setThreat(1.0f).build())
                .build();
    }

    private double priority(Common.Event event) {
        Value value = event.getStructured().getFieldsMap().get("priority");
        if (value == null) {
            return 0;
        }
        return value.getNumberValue();
    }

    private List<String> labels() {
        List<String> labels = new ArrayList<>();
        for (Common.Event event : publishedEvents) {
            labels.add(event.getRawText());
        }
        return labels;
    }

    private static final class BudgetStrategy implements FlowStrategy {
        private int budget;
        private int availableCalls = 0;
        private final List<Integer> consumeCalls = new ArrayList<>();

        private BudgetStrategy(int budget) {
            this.budget = budget;
        }

        @Override
        public boolean shouldPublish(Common.Event event) {
            return true;
        }

        @Override
        public int availableTokens() {
            availableCalls += 1;
            return budget;
        }

        @Override
        public void consume(int n) {
            consumeCalls.add(n);
            budget -= n;
        }
    }

    private static final class Scenario {
        private final int budget;
        private final List<Common.Event> events;

        private Scenario(int budget, List<Common.Event> events) {
            this.budget = budget;
            this.events = events;
        }
    }
}
