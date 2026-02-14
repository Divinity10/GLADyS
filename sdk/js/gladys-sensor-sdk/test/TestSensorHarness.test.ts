import { describe, it, expect, beforeEach } from "vitest";
import { TestSensorHarness } from "../src/testing/TestSensorHarness";
import { CommandDispatcher } from "../src/CommandDispatcher";
import { ComponentState } from "../src/generated/common";

describe("TestSensorHarness", () => {
  let dispatcher: CommandDispatcher;
  let harness: TestSensorHarness;

  beforeEach(() => {
    dispatcher = new CommandDispatcher()
      .onStart(async (args) => {
        if (args.dryRun) return ComponentState.COMPONENT_STATE_STARTING;
        return null;
      })
      .onStop(async () => null)
      .onPause(async () => null)
      .onResume(async () => null)
      .onReload(async () => null)
      .onHealthCheck(async () => null)
      .onRecover(async () => null);

    harness = new TestSensorHarness(dispatcher);
  });

  it("dispatches START", async () => {
    const result = await harness.dispatchStart();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches STOP", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_ACTIVE);

    const result = await harness.dispatchStop();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_STOPPED);
  });

  it("dispatches PAUSE", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_ACTIVE);

    const result = await harness.dispatchPause();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_PAUSED);
  });

  it("dispatches RESUME", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_PAUSED);

    const result = await harness.dispatchResume();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches RELOAD", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_ACTIVE);

    const result = await harness.dispatchReload();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches HEALTH_CHECK", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_ACTIVE);

    const result = await harness.dispatchHealthCheck();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("dispatches RECOVER", async () => {
    harness.setState(ComponentState.COMPONENT_STATE_ERROR);

    const result = await harness.dispatchRecover();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("get and set state", () => {
    expect(harness.getState()).toBe(ComponentState.COMPONENT_STATE_UNKNOWN);

    harness.setState(ComponentState.COMPONENT_STATE_ACTIVE);

    expect(harness.getState()).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
  });

  it("default args when none provided", async () => {
    // START with no args should use default dryRun=false, resulting in ACTIVE
    const result = await harness.dispatchStart();

    expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);

    // START with dryRun=true should return STARTING (handler override)
    harness.setState(ComponentState.COMPONENT_STATE_UNKNOWN);
    const result2 = await harness.dispatchStart({ dryRun: true });

    expect(result2.state).toBe(ComponentState.COMPONENT_STATE_STARTING);
  });
});
