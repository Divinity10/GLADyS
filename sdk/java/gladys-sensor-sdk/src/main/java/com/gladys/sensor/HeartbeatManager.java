package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Sends periodic heartbeats to the orchestrator on a background thread.
 * Optionally dispatches pending commands received in heartbeat responses.
 */
public class HeartbeatManager {

    private static final Logger logger = Logger.getLogger(HeartbeatManager.class.getName());

    private final GladysClient client;
    private final String componentId;
    private final int intervalSeconds;
    private final ScheduledExecutorService scheduler;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final Consumer<Orchestrator.PendingCommand> onCommand;
    private volatile Common.ComponentState state = Common.ComponentState.COMPONENT_STATE_ACTIVE;
    private volatile String errorMessage;

    public HeartbeatManager(GladysClient client, String componentId, int intervalSeconds) {
        this(client, componentId, intervalSeconds, null);
    }

    public HeartbeatManager(GladysClient client, String componentId, int intervalSeconds,
                            Consumer<Orchestrator.PendingCommand> onCommand) {
        this.client = client;
        this.componentId = componentId;
        this.intervalSeconds = intervalSeconds;
        this.onCommand = onCommand;
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

    public void setState(Common.ComponentState state) {
        this.state = state;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    private void sendHeartbeat() {
        try {
            Orchestrator.HeartbeatResponse response = client.heartbeat(componentId, state, errorMessage);

            if (onCommand != null && response.getAcknowledged()
                    && response.getPendingCommandsCount() > 0) {
                for (Orchestrator.PendingCommand cmd : response.getPendingCommandsList()) {
                    try {
                        onCommand.accept(cmd);
                    } catch (Exception e) {
                        logger.log(Level.WARNING,
                                "Command callback failed for " + cmd.getCommand(), e);
                    }
                }
            }
        } catch (Exception e) {
            logger.log(Level.WARNING, "Heartbeat failed for " + componentId, e);
        }
    }
}
