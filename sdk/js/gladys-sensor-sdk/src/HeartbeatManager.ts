import { GladysClient } from "./GladysClient";
import { ComponentState } from "./generated/common";
import { type PendingCommand } from "./generated/orchestrator";

/**
 * Callback invoked for each pending command received in heartbeat response.
 */
export type OnCommandCallback = (cmd: PendingCommand) => Promise<void>;

/**
 * Background heartbeat manager using setInterval.
 * Timer is unref'd so it doesn't prevent Node.js process exit.
 * Default state is COMPONENT_STATE_ACTIVE; call setState() to change.
 *
 * Optionally accepts an onCommand callback that is invoked for each
 * pending command in the heartbeat response.
 */
export class HeartbeatManager {
  private readonly client: GladysClient;
  private readonly componentId: string;
  private readonly intervalMs: number;
  private readonly onCommand: OnCommandCallback | null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private running: boolean = false;
  private currentState: ComponentState = ComponentState.COMPONENT_STATE_ACTIVE;
  private errorMessage: string = "";

  constructor(
    client: GladysClient,
    componentId: string,
    intervalSeconds: number,
    onCommand?: OnCommandCallback
  ) {
    this.client = client;
    this.componentId = componentId;
    this.intervalMs = intervalSeconds * 1000;
    this.onCommand = onCommand ?? null;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.sendHeartbeat();
    this.timer = setInterval(() => this.sendHeartbeat(), this.intervalMs);
    this.timer.unref();
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  isRunning(): boolean {
    return this.running;
  }

  setState(state: ComponentState): void {
    this.currentState = state;
  }

  getState(): ComponentState {
    return this.currentState;
  }

  /**
   * Set error message to include in next heartbeat.
   * Cleared after a successful heartbeat send.
   */
  setErrorMessage(message: string): void {
    this.errorMessage = message;
  }

  private sendHeartbeat(): void {
    const errorMsg = this.errorMessage;

    this.client
      .heartbeat(this.componentId, this.currentState, errorMsg || undefined)
      .then((response) => {
        this.errorMessage = "";
        if (this.onCommand && response.pendingCommands?.length > 0) {
          // Process pending commands sequentially
          this.processCommands(response.pendingCommands);
        }
      })
      .catch(() => {
        // Swallow errors -- heartbeat failures shouldn't crash the sensor.
        // Orchestrator monitors heartbeat absence for dead sensor detection.
      });
  }

  private async processCommands(commands: PendingCommand[]): Promise<void> {
    for (const cmd of commands) {
      try {
        await this.onCommand!(cmd);
      } catch {
        // Command processing errors are handled by CommandDispatcher.
        // Don't let one command failure prevent processing the rest.
      }
    }
  }
}
