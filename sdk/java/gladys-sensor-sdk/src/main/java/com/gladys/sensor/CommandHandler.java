package com.gladys.sensor;

import gladys.v1.Common;

/**
 * Functional interface for command handlers with typed arguments.
 * Handlers execute on the heartbeat thread and should complete quickly.
 *
 * @param <T> Typed command arguments class (e.g., StartArgs, StopArgs)
 */
@FunctionalInterface
public interface CommandHandler<T extends CommandArgs> {

    /**
     * Handle a command with typed arguments.
     *
     * @param args Typed command arguments
     * @return New component state (null = use default state transition)
     * @throws Exception If command handling fails (will set ERROR state)
     */
    Common.ComponentState handle(T args) throws Exception;
}
