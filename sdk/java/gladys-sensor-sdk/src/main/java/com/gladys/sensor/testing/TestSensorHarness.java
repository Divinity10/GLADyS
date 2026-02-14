package com.gladys.sensor.testing;

import com.gladys.sensor.CommandDispatcher;
import com.google.protobuf.Struct;
import gladys.v1.Common;
import gladys.v1.Orchestrator;

/**
 * Test harness for sensor command handling.
 * Bypasses heartbeat and gRPC to directly test command handlers.
 *
 * Usage in JUnit tests:
 * <pre>
 * CommandDispatcher dispatcher = CommandDispatcher.builder()
 *     .onStart(args -> {
 *         // handler logic
 *         return null; // or return specific state
 *     })
 *     .build();
 *
 * TestSensorHarness harness = new TestSensorHarness(dispatcher);
 *
 * harness.sendStart(StartArgs.testArgs(false));
 * assertEquals(COMPONENT_STATE_ACTIVE, harness.getState());
 * </pre>
 */
public class TestSensorHarness {

    private final CommandDispatcher dispatcher;

    /**
     * Create a test harness wrapping a command dispatcher.
     *
     * @param dispatcher Configured dispatcher with handlers
     */
    public TestSensorHarness(CommandDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    /**
     * Send a START command.
     *
     * @param args START command arguments (use StartArgs.testArgs())
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchStart(Struct args) {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_START, args);
    }

    /**
     * Send a START command with default args.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchStart() {
        return dispatchStart(Struct.getDefaultInstance());
    }

    /**
     * Send a STOP command.
     *
     * @param args STOP command arguments (use StopArgs.testArgs())
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchStop(Struct args) {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_STOP, args);
    }

    /**
     * Send a STOP command with default args.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchStop() {
        return dispatchStop(Struct.getDefaultInstance());
    }

    /**
     * Send a PAUSE command.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchPause() {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_PAUSE, Struct.getDefaultInstance());
    }

    /**
     * Send a RESUME command.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchResume() {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_RESUME, Struct.getDefaultInstance());
    }

    /**
     * Send a RELOAD command.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchReload() {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_RELOAD, Struct.getDefaultInstance());
    }

    /**
     * Send a HEALTH_CHECK command.
     *
     * @param args HEALTH_CHECK command arguments (use HealthCheckArgs.testArgs())
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchHealthCheck(Struct args) {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_HEALTH_CHECK, args);
    }

    /**
     * Send a HEALTH_CHECK command with default args.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchHealthCheck() {
        return dispatchHealthCheck(Struct.getDefaultInstance());
    }

    /**
     * Send a RECOVER command.
     *
     * @param args RECOVER command arguments (use RecoverArgs.testArgs())
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchRecover(Struct args) {
        return dispatcher.dispatch(Orchestrator.Command.COMMAND_RECOVER, args);
    }

    /**
     * Send a RECOVER command with default args.
     *
     * @return Dispatch result
     */
    public CommandDispatcher.DispatchResult dispatchRecover() {
        return dispatchRecover(Struct.getDefaultInstance());
    }

    /**
     * Get the current component state.
     *
     * @return Current state from dispatcher
     */
    public Common.ComponentState getState() {
        return dispatcher.getCurrentState();
    }

    /**
     * Set the current component state (for test arrangement).
     *
     * @param state State to set
     */
    public void setState(Common.ComponentState state) {
        dispatcher.setCurrentState(state);
    }

    /**
     * Get the last error message.
     *
     * @return Error message or null
     */
    public String getLastErrorMessage() {
        return dispatcher.getLastErrorMessage();
    }
}
