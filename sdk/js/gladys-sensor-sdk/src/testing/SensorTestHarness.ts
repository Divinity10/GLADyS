import { ComponentState } from "../generated/common";
import { Command } from "../generated/orchestrator";
import {
  CommandDispatcher,
  type DispatchResult,
} from "../CommandDispatcher";
import {
  type StartArgs,
  type StopArgs,
  type RecoverArgs,
  type HealthCheckArgs,
  startArgsDefaults,
  stopArgsDefaults,
  recoverArgsDefaults,
  healthCheckArgsDefaults,
} from "../args";

/**
 * Test harness for sensor command handling.
 * Bypasses gRPC and heartbeat loop for direct command dispatch.
 *
 * @example
 * ```typescript
 * import { SensorTestHarness } from "gladys-sensor-sdk/testing";
 *
 * const harness = new SensorTestHarness(dispatcher);
 * const result = await harness.dispatchStart();
 * expect(result.state).toBe(ComponentState.COMPONENT_STATE_ACTIVE);
 * ```
 */
export class SensorTestHarness {
  readonly dispatcher: CommandDispatcher;

  constructor(dispatcher: CommandDispatcher) {
    this.dispatcher = dispatcher;
  }

  /** Dispatch START command with optional args override. */
  async dispatchStart(args?: Record<string, unknown>): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_START, args ?? {});
  }

  /** Dispatch STOP command with optional args override. */
  async dispatchStop(args?: Record<string, unknown>): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_STOP, args ?? {});
  }

  /** Dispatch PAUSE command. */
  async dispatchPause(): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_PAUSE);
  }

  /** Dispatch RESUME command. */
  async dispatchResume(): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_RESUME);
  }

  /** Dispatch RELOAD command. */
  async dispatchReload(): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_RELOAD);
  }

  /** Dispatch HEALTH_CHECK command with optional args override. */
  async dispatchHealthCheck(args?: Record<string, unknown>): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_HEALTH_CHECK, args ?? {});
  }

  /** Dispatch RECOVER command with optional args override. */
  async dispatchRecover(args?: Record<string, unknown>): Promise<DispatchResult> {
    return this.dispatcher.dispatch(Command.COMMAND_RECOVER, args ?? {});
  }

  /** Get current state from dispatcher. */
  getState(): ComponentState {
    return this.dispatcher.getState();
  }

  /** Set state directly for test arrangement. */
  setState(state: ComponentState): void {
    this.dispatcher.setState(state);
  }
}
