package com.gladys.sensor;

import gladys.v1.Common;
import gladys.v1.Orchestrator;

/**
 * Functional interface for global command error handling.
 * Called when any command handler throws an exception.
 */
@FunctionalInterface
public interface CommandErrorHandler {

    /**
     * Handle a command error.
     * Return null to accept the default ERROR state.
     * Return a specific state to override (e.g., ACTIVE for recoverable errors).
     *
     * @param command The command that failed
     * @param exception The exception thrown by the handler
     * @param currentState The component state before the error
     * @return New component state (null = accept ERROR state)
     */
    Common.ComponentState handleError(Orchestrator.Command command, Exception exception,
                                       Common.ComponentState currentState);
}
