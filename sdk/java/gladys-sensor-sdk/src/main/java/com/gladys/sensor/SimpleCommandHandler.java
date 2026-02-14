package com.gladys.sensor;

import gladys.v1.Common;

/**
 * Functional interface for simple command handlers without arguments.
 * Used for PAUSE, RESUME, and RELOAD commands which don't take arguments.
 * Handlers execute on the heartbeat thread and should complete quickly.
 */
@FunctionalInterface
public interface SimpleCommandHandler {

    /**
     * Handle a command without arguments.
     *
     * @return New component state (null = use default state transition)
     * @throws Exception If command handling fails (will set ERROR state)
     */
    Common.ComponentState handle() throws Exception;
}
