import { describe, it, expect, beforeEach } from "vitest";
import { CommandDispatcher } from "../src/CommandDispatcher";
import { ComponentState } from "../src/generated/common";
import { Command } from "../src/generated/orchestrator";

describe("CommandDispatcher", () => {
  let dispatcher: CommandDispatcher;

  beforeEach(() => {
    dispatcher = new CommandDispatcher();
  });

  it("dispatches START and sets ACTIVE", async () => {
    dispatcher.onStart(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_START, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
    expect(result.errorMessage).toBeUndefined();
  });

  it("dispatches STOP and sets STOPPED", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher.onStop(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_STOP, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_STOPPED);
  });

  it("dispatches PAUSE and sets PAUSED", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher.onPause(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_PAUSE);

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_PAUSED);
  });

  it("dispatches RESUME and sets ACTIVE", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_PAUSED);
    dispatcher.onResume(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_RESUME);

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches HEALTH_CHECK without state change", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher.onHealthCheck(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_HEALTH_CHECK, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
    expect(dispatcher.getState()).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches RECOVER and sets ACTIVE", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ERROR);
    dispatcher.onRecover(async () => null);

    const result = await dispatcher.dispatch(Command.COMMAND_RECOVER, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("handler override state is respected", async () => {
    dispatcher.onStart(async () => {
      return ComponentState.COMPONENT_STATE_STARTING;
    });

    const result = await dispatcher.dispatch(Command.COMMAND_START, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_STARTING);
  });

  it("handler exception sets ERROR", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher.onStop(async () => {
      throw new Error("shutdown failed");
    });

    const result = await dispatcher.dispatch(Command.COMMAND_STOP, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ERROR);
    expect(result.errorMessage).toBe("shutdown failed");
  });

  it("HEALTH_CHECK exception preserves state", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher.onHealthCheck(async () => {
      throw new Error("check failed");
    });

    const result = await dispatcher.dispatch(Command.COMMAND_HEALTH_CHECK, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
    expect(result.errorMessage).toBe("check failed");
  });

  it("unregistered command keeps state and returns error message", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_PAUSED);
    const result = await dispatcher.dispatch(Command.COMMAND_RELOAD);

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_PAUSED);
    expect(result.errorMessage).toBe(
      `No handler registered for ${Command.COMMAND_RELOAD}`
    );
  });

  it("error handler is called on exception", async () => {
    let errorHandlerCalled = false;
    let capturedCommand: Command | undefined;
    let capturedError: Error | undefined;
    let capturedState: ComponentState | undefined;

    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher
      .onStop(async () => {
        throw new Error("stop broke");
      })
      .onCommandError((cmd, err, state) => {
        errorHandlerCalled = true;
        capturedCommand = cmd;
        capturedError = err;
        capturedState = state;
        return null; // Accept ERROR
      });

    const result = await dispatcher.dispatch(Command.COMMAND_STOP, {});

    expect(errorHandlerCalled).toBe(true);
    expect(capturedCommand).toBe(Command.COMMAND_STOP);
    expect(capturedError?.message).toBe("stop broke");
    expect(capturedState).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ERROR);
  });

  it("error handler can override ERROR state", async () => {
    dispatcher.setState(ComponentState.COMPONENT_STATE_ACTIVE);
    dispatcher
      .onStop(async () => {
        throw new Error("stop broke");
      })
      .onCommandError((_cmd, _err, currentState) => {
        return currentState; // Stay in current state instead of ERROR
      });

    const result = await dispatcher.dispatch(Command.COMMAND_STOP, {});

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });
});
