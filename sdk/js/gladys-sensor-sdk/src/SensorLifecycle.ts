import { GladysClient } from "./GladysClient";
import { HeartbeatManager } from "./HeartbeatManager";
import { CommandDispatcher } from "./CommandDispatcher";
import { ComponentState } from "./generated/common";
import { type PendingCommand } from "./generated/orchestrator";

/**
 * Configuration options for SensorLifecycle.
 */
export interface SensorLifecycleOptions {
  /** GladysClient instance */
  readonly client: GladysClient;
  /** Component identifier */
  readonly componentId: string;
  /** Component type descriptor */
  readonly componentType: string;
  /** CommandDispatcher instance (configured with handlers) */
  readonly dispatcher: CommandDispatcher;
  /** Heartbeat interval in seconds. Default: 5 */
  readonly heartbeatIntervalSeconds?: number;
}

/**
 * High-level lifecycle manager composing heartbeat, command dispatch, and state.
 *
 * Handles:
 * - Background heartbeat loop via HeartbeatManager
 * - Processing pending commands from heartbeat responses
 * - State management via CommandDispatcher
 * - Error message propagation to orchestrator
 *
 * @example
 * ```typescript
 * const lifecycle = createSensorLifecycle({
 *   client,
 *   componentId: "game-state-sensor",
 *   componentType: "game-monitor",
 *   dispatcher: new CommandDispatcher()
 *     .onStart(async (args) => { ... })
 *     .onStop(async (args) => { ... }),
 * });
 *
 * await lifecycle.start();
 * // Heartbeat runs in background, commands dispatched automatically
 * ```
 */
export interface SensorLifecycle {
  /** Start lifecycle: begin heartbeat loop with command processing. */
  start(): Promise<void>;
  /** Stop lifecycle: stop heartbeat loop. */
  stop(): Promise<void>;
  /** Check if lifecycle is running. */
  isRunning(): boolean;
  /** Get current component state. */
  getState(): ComponentState;
  /** Set component state manually. */
  setState(state: ComponentState): void;
}

class SensorLifecycleImpl implements SensorLifecycle {
  private readonly heartbeatManager: HeartbeatManager;
  private readonly dispatcher: CommandDispatcher;
  private errorMessage: string = "";

  constructor(options: SensorLifecycleOptions) {
    this.dispatcher = options.dispatcher;

    const intervalSeconds = options.heartbeatIntervalSeconds ?? 5;

    this.heartbeatManager = new HeartbeatManager(
      options.client,
      options.componentId,
      intervalSeconds,
      async (cmd: PendingCommand) => {
        await this.handleCommand(cmd);
      }
    );
  }

  async start(): Promise<void> {
    this.heartbeatManager.start();
  }

  async stop(): Promise<void> {
    this.heartbeatManager.stop();
    this.dispatcher.setState(ComponentState.COMPONENT_STATE_STOPPED);
    this.heartbeatManager.setState(ComponentState.COMPONENT_STATE_STOPPED);
  }

  isRunning(): boolean {
    return this.heartbeatManager.isRunning();
  }

  getState(): ComponentState {
    return this.dispatcher.getState();
  }

  setState(state: ComponentState): void {
    this.dispatcher.setState(state);
    this.heartbeatManager.setState(state);
  }

  private async handleCommand(cmd: PendingCommand): Promise<void> {
    const result = await this.dispatcher.dispatch(
      cmd.command,
      cmd.args as Record<string, unknown> | undefined
    );

    // Sync state to heartbeat manager
    this.heartbeatManager.setState(result.state);

    if (result.errorMessage) {
      this.heartbeatManager.setErrorMessage(result.errorMessage);
    }
  }
}

/**
 * Factory function for creating SensorLifecycle.
 * Preferred over direct construction for clarity.
 */
export function createSensorLifecycle(options: SensorLifecycleOptions): SensorLifecycle {
  return new SensorLifecycleImpl(options);
}
