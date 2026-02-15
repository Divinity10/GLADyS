package com.gladys.sensor;

import gladys.v1.Common;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.ToDoubleFunction;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Configurable event dispatch strategy for sensors.
 *
 * Three modes:
 * - Immediate (flushIntervalMs=0): Every emit() calls publishEvent() immediately.
 * - Scheduled (flushIntervalMs>0): Buffer events and flush on timer.
 * - Hybrid (scheduled + immediateOnThreat): Scheduled mode but threat events bypass the buffer.
 *
 * Thread Safety: emit() and flush() are synchronized on the event buffer.
 */
public class EventDispatcher {

    private static final Logger logger = Logger.getLogger(EventDispatcher.class.getName());

    private final GladysClient client;
    private final String source;
    private final long flushIntervalMs;
    private final boolean immediateOnThreat;
    private final ToDoubleFunction<Common.Event> priorityFn;
    private volatile FlowStrategy strategy;
    private final List<Common.Event> buffer = new ArrayList<>();
    private final AtomicLong eventsFiltered = new AtomicLong(0);
    private final AtomicLong eventsPublished = new AtomicLong(0);
    private final ScheduledExecutorService scheduler;
    private ScheduledFuture<?> flushTask;

    /**
     * Create an immediate-mode EventDispatcher (every emit sends immediately).
     *
     * @param client GladysClient for publishing
     * @param source Source identifier for events
     */
    public EventDispatcher(GladysClient client, String source) {
        this(client, source, 0, true, null, null);
    }

    /**
     * Create an EventDispatcher with configurable flush interval.
     *
     * @param client GladysClient for publishing
     * @param source Source identifier for events
     * @param flushIntervalMs Flush interval in milliseconds (0 = immediate mode)
     * @param immediateOnThreat If true, threat events bypass the buffer (hybrid mode)
     */
    public EventDispatcher(GladysClient client, String source, long flushIntervalMs,
                           boolean immediateOnThreat) {
        this(client, source, flushIntervalMs, immediateOnThreat, null, null);
    }

    /**
     * Create an EventDispatcher with configurable flush interval and flow strategy.
     *
     * @param client GladysClient for publishing
     * @param source Source identifier for events
     * @param flushIntervalMs Flush interval in milliseconds (0 = immediate mode)
     * @param immediateOnThreat If true, threat events bypass the buffer (hybrid mode)
     * @param strategy Flow control strategy (null defaults to NoOpStrategy)
     */
    public EventDispatcher(GladysClient client, String source, long flushIntervalMs,
                           boolean immediateOnThreat, FlowStrategy strategy) {
        this(client, source, flushIntervalMs, immediateOnThreat, strategy, null);
    }

    public EventDispatcher(GladysClient client, String source, long flushIntervalMs,
                           boolean immediateOnThreat, FlowStrategy strategy,
                           ToDoubleFunction<Common.Event> priorityFn) {
        this.client = client;
        this.source = source;
        this.flushIntervalMs = flushIntervalMs;
        this.immediateOnThreat = immediateOnThreat;
        this.priorityFn = priorityFn;
        this.strategy = strategy != null ? strategy : new NoOpStrategy();
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "gladys-event-flush-" + source);
            t.setDaemon(true);
            return t;
        });

        if (flushIntervalMs > 0) {
            flushTask = scheduler.scheduleAtFixedRate(this::flush, flushIntervalMs,
                    flushIntervalMs, TimeUnit.MILLISECONDS);
        }
    }

    /**
     * Emit an event. Depending on mode, this either sends immediately or buffers.
     *
     * @param event Event to emit
     */
    public boolean emit(Common.Event event) {
        boolean threat = isThreat(event);

        // Hybrid: threat events bypass buffer
        if (immediateOnThreat && threat && flushIntervalMs > 0) {
            sendImmediate(event);
            eventsPublished.incrementAndGet();
            return true;
        }

        // Threat events always bypass strategy checks.
        if (!threat && !strategy.shouldPublish(event)) {
            eventsFiltered.incrementAndGet();
            return false;
        }

        // Immediate mode: send directly
        if (flushIntervalMs <= 0) {
            sendImmediate(event);
            eventsPublished.incrementAndGet();
            return true;
        }

        // Scheduled mode: buffer
        synchronized (buffer) {
            buffer.add(event);
        }
        eventsPublished.incrementAndGet();
        return true;
    }

    public EmitResult emitBatch(List<Common.Event> events) {
        if (events == null || events.isEmpty()) {
            return new EmitResult(0, 0);
        }

        PartitionedEvents partitioned = partitionThreats(events);

        if (partitioned.candidates.isEmpty()) {
            List<Common.Event> toSend = reorderOriginal(events, partitioned.threats, List.of());
            sendEvents(toSend);
            eventsPublished.addAndGet(toSend.size());
            return new EmitResult(toSend.size(), 0);
        }

        int budget = strategy.availableTokens();
        List<IndexedEvent> kept;
        int suppressed = 0;

        if (budget >= partitioned.candidates.size()) {
            strategy.consume(partitioned.candidates.size());
            kept = new ArrayList<>(partitioned.candidates);
        } else if (budget <= 0) {
            kept = List.of();
            suppressed = partitioned.candidates.size();
            eventsFiltered.addAndGet(suppressed);
        } else {
            kept = selectByPriority(partitioned.candidates, budget);
            strategy.consume(kept.size());
            suppressed = partitioned.candidates.size() - kept.size();
            eventsFiltered.addAndGet(suppressed);
        }

        List<Common.Event> toSend = reorderOriginal(events, partitioned.threats, kept);
        sendEvents(toSend);
        eventsPublished.addAndGet(toSend.size());
        return new EmitResult(toSend.size(), suppressed);
    }

    /**
     * Force-flush all buffered events. Safe to call even with an empty buffer.
     */
    public void flush() {
        List<Common.Event> toSend;
        synchronized (buffer) {
            if (buffer.isEmpty()) {
                return;
            }
            toSend = new ArrayList<>(buffer);
            buffer.clear();
        }

        try {
            if (toSend.size() == 1) {
                client.publishEvent(toSend.get(0));
            } else {
                client.publishEvents(toSend);
            }
        } catch (Exception e) {
            logger.log(Level.WARNING, "Failed to flush " + toSend.size() + " events for " + source, e);
        }
    }

    /**
     * Shutdown the dispatcher, flushing any remaining events.
     */
    public void shutdown() {
        if (flushTask != null) {
            flushTask.cancel(false);
        }
        flush();
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

    /**
     * Replace the active flow control strategy.
     *
     * @param strategy New strategy (null resets to NoOpStrategy)
     */
    public void setStrategy(FlowStrategy strategy) {
        this.strategy = strategy != null ? strategy : new NoOpStrategy();
    }

    public long getEventsFiltered() {
        return eventsFiltered.get();
    }

    public long getEventsPublished() {
        return eventsPublished.get();
    }

    private PartitionedEvents partitionThreats(List<Common.Event> events) {
        List<IndexedEvent> threats = new ArrayList<>();
        List<IndexedEvent> candidates = new ArrayList<>();
        for (int i = 0; i < events.size(); i++) {
            Common.Event event = events.get(i);
            if (isThreat(event)) {
                threats.add(new IndexedEvent(i, event));
            } else {
                candidates.add(new IndexedEvent(i, event));
            }
        }
        return new PartitionedEvents(threats, candidates);
    }

    private List<IndexedEvent> selectByPriority(List<IndexedEvent> candidates, int budget) {
        if (priorityFn == null) {
            return new ArrayList<>(candidates.subList(0, budget));
        }

        List<IndexedEvent> selected = new ArrayList<>(candidates);
        selected.sort((left, right) -> {
            int byPriority = Double.compare(
                    priorityFn.applyAsDouble(right.event),
                    priorityFn.applyAsDouble(left.event)
            );
            if (byPriority != 0) {
                return byPriority;
            }
            return Integer.compare(left.index, right.index);
        });
        selected = new ArrayList<>(selected.subList(0, budget));
        selected.sort(Comparator.comparingInt(item -> item.index));
        return selected;
    }

    private List<Common.Event> reorderOriginal(List<Common.Event> original,
                                               List<IndexedEvent> threats,
                                               List<IndexedEvent> kept) {
        Set<Integer> selectedIndices = new HashSet<>();
        for (IndexedEvent item : threats) {
            selectedIndices.add(item.index);
        }
        for (IndexedEvent item : kept) {
            selectedIndices.add(item.index);
        }

        List<Common.Event> reordered = new ArrayList<>();
        for (int i = 0; i < original.size(); i++) {
            if (selectedIndices.contains(i)) {
                reordered.add(original.get(i));
            }
        }
        return reordered;
    }

    private void sendEvents(List<Common.Event> events) {
        if (events.isEmpty()) {
            return;
        }

        if (flushIntervalMs <= 0) {
            try {
                if (events.size() == 1) {
                    client.publishEvent(events.get(0));
                } else {
                    client.publishEvents(events);
                }
            } catch (Exception e) {
                logger.log(Level.WARNING, "Failed to publish " + events.size() + " events for " + source, e);
            }
            return;
        }

        if (immediateOnThreat) {
            List<Common.Event> buffered = new ArrayList<>();
            for (Common.Event event : events) {
                if (isThreat(event)) {
                    sendImmediate(event);
                } else {
                    buffered.add(event);
                }
            }
            synchronized (buffer) {
                buffer.addAll(buffered);
            }
            return;
        }

        synchronized (buffer) {
            buffer.addAll(events);
        }
    }

    private void sendImmediate(Common.Event event) {
        try {
            client.publishEvent(event);
        } catch (Exception e) {
            logger.log(Level.WARNING, "Failed to publish event for " + source, e);
        }
    }

    private boolean isThreat(Common.Event event) {
        return event.hasSalience() && event.getSalience().getThreat() > 0;
    }

    private static final class PartitionedEvents {
        private final List<IndexedEvent> threats;
        private final List<IndexedEvent> candidates;

        private PartitionedEvents(List<IndexedEvent> threats, List<IndexedEvent> candidates) {
            this.threats = threats;
            this.candidates = candidates;
        }
    }

    private static final class IndexedEvent {
        private final int index;
        private final Common.Event event;

        private IndexedEvent(int index, Common.Event event) {
            this.index = index;
            this.event = event;
        }
    }
}
