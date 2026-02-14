package com.gladys.sensor;

import com.google.protobuf.Struct;
import gladys.v1.Common;
import gladys.v1.Orchestrator;

import java.util.HashMap;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Dispatches lifecycle commands to registered handlers.
 * Automatically manages component state transitions based on commands and handler results.
 *
 * Thread Safety: dispatch() is synchronized and safe to call from the heartbeat thread and external
 * threads. Handlers execute inside the synchronized dispatch path, so keep them fast.
 */
public class CommandDispatcher {

    private static final Logger logger = Logger.getLogger(CommandDispatcher.class.getName());

    private final Map<Orchestrator.Command, HandlerEntry> handlers = new HashMap<>();
    private CommandErrorHandler errorHandler = null;
    private volatile Common.ComponentState currentState = Common.ComponentState.COMPONENT_STATE_UNKNOWN;
    private volatile String lastErrorMessage = null;

    private CommandDispatcher() {
        // Use builder
    }

    /**
     * Dispatch a command to the registered handler.
     *
     * @param command Command to dispatch
     * @param args Command arguments (may be empty)
     * @return Dispatch result with new state and optional error message
     */
    public synchronized DispatchResult dispatch(Orchestrator.Command command, Struct args) {
        Common.ComponentState previousState = currentState;
        HandlerEntry entry = handlers.get(command);
        if (entry == null) {
            String errorMessage = "No handler registered for " + command;
            logger.log(Level.WARNING, errorMessage);
            lastErrorMessage = errorMessage;
            return new DispatchResult(previousState, errorMessage);
        }

        try {
            Common.ComponentState newState = entry.invoke(args);

            // If handler returns null, use default state transition
            if (newState == null) {
                newState = getDefaultStateTransition(command);
            }

            currentState = newState;
            lastErrorMessage = null;
            return new DispatchResult(newState, null);

        } catch (Exception e) {
            logger.log(Level.SEVERE, "Command handler failed: " + command, e);

            String errorMessage = e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName();
            boolean isHealthCheck = command == Orchestrator.Command.COMMAND_HEALTH_CHECK;
            Common.ComponentState errorState = isHealthCheck
                    ? previousState
                    : Common.ComponentState.COMPONENT_STATE_ERROR;

            if (errorHandler != null) {
                try {
                    Common.ComponentState handlerState = errorHandler.handleError(command, e, previousState);
                    if (!isHealthCheck && handlerState != null) {
                        errorState = handlerState;
                    }
                } catch (Exception handlerException) {
                    logger.log(Level.WARNING, "Error handler failed for command: " + command, handlerException);
                }
            }

            currentState = errorState;
            lastErrorMessage = errorMessage;
            return new DispatchResult(errorState, errorMessage);
        }
    }

    /**
     * Get the current component state.
     *
     * @return Current state
     */
    public Common.ComponentState getCurrentState() {
        return currentState;
    }

    /**
     * Set the current component state (for test setup).
     *
     * @param state State to set
     */
    public void setCurrentState(Common.ComponentState state) {
        this.currentState = state;
    }

    /**
     * Get the last error message (null if no error).
     *
     * @return Error message or null
     */
    public String getLastErrorMessage() {
        return lastErrorMessage;
    }

    /**
     * Get default state transition for a command.
     *
     * @param command Command
     * @return Default next state
     */
    private Common.ComponentState getDefaultStateTransition(Orchestrator.Command command) {
        switch (command) {
            case COMMAND_START:
                return Common.ComponentState.COMPONENT_STATE_ACTIVE;
            case COMMAND_STOP:
                return Common.ComponentState.COMPONENT_STATE_STOPPED;
            case COMMAND_PAUSE:
                return Common.ComponentState.COMPONENT_STATE_PAUSED;
            case COMMAND_RESUME:
                return Common.ComponentState.COMPONENT_STATE_ACTIVE;
            case COMMAND_RELOAD:
                return Common.ComponentState.COMPONENT_STATE_ACTIVE;
            case COMMAND_RECOVER:
                return Common.ComponentState.COMPONENT_STATE_ACTIVE;
            case COMMAND_HEALTH_CHECK:
                return currentState; // No state change
            default:
                return currentState;
        }
    }

    /**
     * Create a new builder for CommandDispatcher.
     *
     * @return Builder instance
     */
    public static Builder builder() {
        return new Builder();
    }

    /**
     * Result of command dispatch containing new state and optional error message.
     */
    public static class DispatchResult {
        public final Common.ComponentState state;
        public final String errorMessage;

        public DispatchResult(Common.ComponentState state, String errorMessage) {
            this.state = state;
            this.errorMessage = errorMessage;
        }

        public boolean hasError() {
            return errorMessage != null;
        }
    }

    /**
     * Builder for CommandDispatcher with type-safe handler registration.
     */
    public static class Builder {
        private final CommandDispatcher dispatcher = new CommandDispatcher();

        /**
         * Register a handler for the START command.
         *
         * @param handler Handler for START command with StartArgs
         * @return This builder
         */
        public Builder onStart(CommandHandler<StartArgs> handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_START,
                new TypedHandlerEntry<>(StartArgs.class, handler));
            return this;
        }

        /**
         * Register a handler for the STOP command.
         *
         * @param handler Handler for STOP command with StopArgs
         * @return This builder
         */
        public Builder onStop(CommandHandler<StopArgs> handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_STOP,
                new TypedHandlerEntry<>(StopArgs.class, handler));
            return this;
        }

        /**
         * Register a handler for the PAUSE command.
         *
         * @param handler Handler for PAUSE command (no args)
         * @return This builder
         */
        public Builder onPause(SimpleCommandHandler handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_PAUSE,
                new SimpleHandlerEntry(handler));
            return this;
        }

        /**
         * Register a handler for the RESUME command.
         *
         * @param handler Handler for RESUME command (no args)
         * @return This builder
         */
        public Builder onResume(SimpleCommandHandler handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_RESUME,
                new SimpleHandlerEntry(handler));
            return this;
        }

        /**
         * Register a handler for the RELOAD command.
         *
         * @param handler Handler for RELOAD command (no args)
         * @return This builder
         */
        public Builder onReload(SimpleCommandHandler handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_RELOAD,
                new SimpleHandlerEntry(handler));
            return this;
        }

        /**
         * Register a handler for the HEALTH_CHECK command.
         *
         * @param handler Handler for HEALTH_CHECK command with HealthCheckArgs
         * @return This builder
         */
        public Builder onHealthCheck(CommandHandler<HealthCheckArgs> handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_HEALTH_CHECK,
                new TypedHandlerEntry<>(HealthCheckArgs.class, handler));
            return this;
        }

        /**
         * Register a handler for the RECOVER command.
         *
         * @param handler Handler for RECOVER command with RecoverArgs
         * @return This builder
         */
        public Builder onRecover(CommandHandler<RecoverArgs> handler) {
            dispatcher.handlers.put(Orchestrator.Command.COMMAND_RECOVER,
                new TypedHandlerEntry<>(RecoverArgs.class, handler));
            return this;
        }

        /**
         * Register a global error handler for all commands.
         *
         * @param handler Error handler
         * @return This builder
         */
        public Builder onCommandError(CommandErrorHandler handler) {
            dispatcher.errorHandler = handler;
            return this;
        }

        /**
         * Build the CommandDispatcher.
         *
         * @return Configured dispatcher
         */
        public CommandDispatcher build() {
            return dispatcher;
        }
    }

    /**
     * Internal interface for handler invocation.
     */
    private interface HandlerEntry {
        Common.ComponentState invoke(Struct args) throws Exception;
    }

    /**
     * Handler entry for typed command arguments.
     */
    private static class TypedHandlerEntry<T extends CommandArgs> implements HandlerEntry {
        private final Class<T> argsClass;
        private final CommandHandler<T> handler;

        TypedHandlerEntry(Class<T> argsClass, CommandHandler<T> handler) {
            this.argsClass = argsClass;
            this.handler = handler;
        }

        @Override
        public Common.ComponentState invoke(Struct args) throws Exception {
            try {
                T typedArgs = argsClass.getConstructor(Struct.class).newInstance(args);
                return handler.handle(typedArgs);
            } catch (ReflectiveOperationException e) {
                throw new RuntimeException("Failed to instantiate args class: " + argsClass, e);
            }
        }
    }

    /**
     * Handler entry for simple commands without arguments.
     */
    private static class SimpleHandlerEntry implements HandlerEntry {
        private final SimpleCommandHandler handler;

        SimpleHandlerEntry(SimpleCommandHandler handler) {
            this.handler = handler;
        }

        @Override
        public Common.ComponentState invoke(Struct args) throws Exception {
            return handler.handle();
        }
    }
}
