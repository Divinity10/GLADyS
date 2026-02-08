package com.gladys.sensor;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Sends periodic heartbeats to the orchestrator on a background thread.
 */
public class HeartbeatManager {

    private static final Logger logger = Logger.getLogger(HeartbeatManager.class.getName());

    private final GladysClient client;
    private final String componentId;
    private final int intervalSeconds;
    private final ScheduledExecutorService scheduler;
    private final AtomicBoolean running = new AtomicBoolean(false);

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

    private void sendHeartbeat() {
        try {
            client.heartbeat(componentId);
        } catch (Exception e) {
            logger.log(Level.WARNING, "Heartbeat failed for " + componentId, e);
        }
    }
}
