package com.gladys.sensor;

import gladys.v1.Common;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
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
    private final List<Common.Event> buffer = new ArrayList<>();
    private final ScheduledExecutorService scheduler;
    private ScheduledFuture<?> flushTask;

    /**
     * Create an immediate-mode EventDispatcher (every emit sends immediately).
     *
     * @param client GladysClient for publishing
     * @param source Source identifier for events
     */
    public EventDispatcher(GladysClient client, String source) {
        this(client, source, 0, true);
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
        this.client = client;
        this.source = source;
        this.flushIntervalMs = flushIntervalMs;
        this.immediateOnThreat = immediateOnThreat;
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
    public void emit(Common.Event event) {
        // Hybrid: threat events bypass buffer
        if (immediateOnThreat && isThreat(event)) {
            sendImmediate(event);
            return;
        }

        // Immediate mode: send directly
        if (flushIntervalMs <= 0) {
            sendImmediate(event);
            return;
        }

        // Scheduled mode: buffer
        synchronized (buffer) {
            buffer.add(event);
        }
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
}
