package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Manages sensor lifecycle including heartbeat, command dispatch, and state transitions.
 * Composes HeartbeatManager and CommandDispatcher with automatic state management.
 *
 * Usage:
 * 1. Build via SensorLifecycle.builder()
 * 2. Register command handlers via CommandDispatcher.builder()
 * 3. Call start() to begin heartbeat and command processing
 * 4. Handlers call stop() to shutdown when receiving STOP command
 */
public class SensorLifecycle {

    private static final Logger logger = Logger.getLogger(SensorLifecycle.class.getName());

    private final GladysClient client;
    private final String componentId;
    private final int heartbeatIntervalSeconds;
    private final CommandDispatcher dispatcher;
    private final ScheduledExecutorService scheduler;
    private final AtomicBoolean running = new AtomicBoolean(false);

    private SensorLifecycle(GladysClient client, String componentId,
                           int heartbeatIntervalSeconds, CommandDispatcher dispatcher) {
        this.client = client;
        this.componentId = componentId;
        this.heartbeatIntervalSeconds = heartbeatIntervalSeconds;
        this.dispatcher = dispatcher;
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "gladys-lifecycle-" + componentId);
            t.setDaemon(true);
            return t;
        });
    }

    /**
     * Start the lifecycle (begin heartbeat and command processing).
     * This method is non-blocking - heartbeat runs on a background thread.
     */
    public void start() {
        if (running.compareAndSet(false, true)) {
            scheduler.scheduleAtFixedRate(this::heartbeatCycle, 0,
                heartbeatIntervalSeconds, TimeUnit.SECONDS);
            logger.info("Started lifecycle for component: " + componentId);
        }
    }

    /**
     * Stop the lifecycle (graceful shutdown).
     * Typically called by STOP command handler.
     */
    public void stop() {
        if (running.compareAndSet(true, false)) {
            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                    scheduler.shutdownNow();
                }
                logger.info("Stopped lifecycle for component: " + componentId);
            } catch (InterruptedException e) {
                scheduler.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    /**
     * Check if lifecycle is running.
     *
     * @return True if heartbeat is active
     */
    public boolean isRunning() {
        return running.get();
    }

    /**
     * Get the current component state.
     *
     * @return Current state from dispatcher
     */
    public Common.ComponentState getCurrentState() {
        return dispatcher.getCurrentState();
    }

    /**
     * Heartbeat cycle: send heartbeat, receive and dispatch pending commands.
     */
    private void heartbeatCycle() {
        try {
            Common.ComponentState currentState = dispatcher.getCurrentState();
            String errorMessage = dispatcher.getLastErrorMessage();

            Orchestrator.HeartbeatResponse response = client.heartbeat(
                componentId, currentState, errorMessage);

            if (response.getAcknowledged() && response.getPendingCommandsCount() > 0) {
                for (Orchestrator.PendingCommand cmd : response.getPendingCommandsList()) {
                    logger.info("Dispatching command: " + cmd.getCommand());
                    CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                        cmd.getCommand(), cmd.getArgs());

                    if (result.hasError()) {
                        logger.log(Level.WARNING, "Command failed: " + cmd.getCommand() +
                            " - " + result.errorMessage);
                    }
                }
            }
        } catch (Exception e) {
            logger.log(Level.WARNING, "Heartbeat cycle failed for " + componentId, e);
        }
    }

    /**
     * Create a builder for SensorLifecycle.
     *
     * @param client GladysClient instance
     * @param componentId Component identifier
     * @return Builder instance
     */
    public static Builder builder(GladysClient client, String componentId) {
        return new Builder(client, componentId);
    }

    /**
     * Builder for SensorLifecycle.
     */
    public static class Builder {
        private final GladysClient client;
        private final String componentId;
        private int heartbeatIntervalSeconds = 10;
        private CommandDispatcher dispatcher;

        private Builder(GladysClient client, String componentId) {
            this.client = client;
            this.componentId = componentId;
        }

        /**
         * Set the heartbeat interval.
         *
         * @param seconds Interval between heartbeats (default: 10)
         * @return This builder
         */
        public Builder heartbeatInterval(int seconds) {
            this.heartbeatIntervalSeconds = seconds;
            return this;
        }

        /**
         * Set the command dispatcher with registered handlers.
         *
         * @param dispatcher Configured dispatcher
         * @return This builder
         */
        public Builder dispatcher(CommandDispatcher dispatcher) {
            this.dispatcher = dispatcher;
            return this;
        }

        /**
         * Build the SensorLifecycle.
         *
         * @return Configured lifecycle manager
         * @throws IllegalStateException if dispatcher is not set
         */
        public SensorLifecycle build() {
            if (dispatcher == null) {
                throw new IllegalStateException("CommandDispatcher must be set");
            }
            return new SensorLifecycle(client, componentId, heartbeatIntervalSeconds, dispatcher);
        }
    }
}
