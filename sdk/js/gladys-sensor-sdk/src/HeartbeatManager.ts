import { GladysClient } from "./GladysClient";
import { ComponentState } from "./generated/common";

/**
 * Background heartbeat manager using setInterval.
 * Timer is unref'd so it doesn't prevent Node.js process exit.
 * Default state is COMPONENT_STATE_ACTIVE; call setState() to change.
 */
export class HeartbeatManager {
  private readonly client: GladysClient;
  private readonly componentId: string;
  private readonly intervalMs: number;
  private timer: ReturnType<typeof setInterval> | null = null;
  private running: boolean = false;
  private currentState: ComponentState = ComponentState.COMPONENT_STATE_ACTIVE;

  constructor(client: GladysClient, componentId: string, intervalSeconds: number) {
    this.client = client;
    this.componentId = componentId;
    this.intervalMs = intervalSeconds * 1000;
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

  private sendHeartbeat(): void {
    this.client.heartbeat(this.componentId, this.currentState).catch(() => {
      // Swallow errors — heartbeat failures shouldn't crash the sensor.
      // Orchestrator monitors heartbeat absence for dead sensor detection.
    });
  }
}
