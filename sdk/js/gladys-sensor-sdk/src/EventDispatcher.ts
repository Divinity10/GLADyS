import { GladysClient } from "./GladysClient";
import { Event } from "./generated/common";

/**
 * Configurable event dispatch strategy.
 *
 * Three modes:
 * - **Immediate** (flushIntervalMs=0, default): every emit() calls publishEvent() now
 * - **Scheduled** (flushIntervalMs>0): collect events, flush on timer via publishEvents()
 * - **Hybrid** (flushIntervalMs>0, immediateOnThreat=true): scheduled + threat bypass
 *
 * @example
 * ```typescript
 * // Immediate mode (default)
 * const events = new EventDispatcher(client, "email-sensor-1");
 *
 * // Scheduled mode (game tick alignment)
 * const events = new EventDispatcher(client, "game-sensor-1", {
 *   flushIntervalMs: 600,
 * });
 *
 * // Hybrid mode (scheduled + threat bypass)
 * const events = new EventDispatcher(client, "game-sensor-1", {
 *   flushIntervalMs: 600,
 *   immediateOnThreat: true,
 * });
 * ```
 */
export class EventDispatcher {
  private readonly client: GladysClient;
  private readonly source: string;
  private readonly flushIntervalMs: number;
  private readonly immediateOnThreat: boolean;
  private buffer: Event[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(
    client: GladysClient,
    source: string,
    options?: {
      flushIntervalMs?: number;
      immediateOnThreat?: boolean;
    }
  ) {
    this.client = client;
    this.source = source;
    this.flushIntervalMs = options?.flushIntervalMs ?? 0;
    this.immediateOnThreat = options?.immediateOnThreat ?? true;

    if (this.flushIntervalMs > 0) {
      this.timer = setInterval(() => {
        this.flush().catch(() => {
          // Swallow flush errors; heartbeat absence detects dead sensors
        });
      }, this.flushIntervalMs);
      this.timer.unref();
    }
  }

  /**
   * Emit an event. Dispatch strategy determines whether it sends immediately or buffers.
   *
   * - Immediate mode (flushIntervalMs=0): sends via publishEvent() now
   * - Scheduled mode: buffers event for next timer flush
   * - Hybrid: threat events bypass buffer, others are buffered
   */
  async emit(event: Event): Promise<void> {
    const isThreat = this.isThreatEvent(event);

    if (this.immediateOnThreat && isThreat && this.flushIntervalMs > 0) {
      // Hybrid mode: threat events bypass buffer
      await this.client.publishEvent(event);
      return;
    }

    if (this.flushIntervalMs === 0) {
      // Immediate mode: send every event now
      await this.client.publishEvent(event);
      return;
    }

    // Scheduled mode: buffer for timer flush
    this.buffer.push(event);
  }

  /**
   * Force-flush all buffered events immediately.
   * Call this in STOP handlers before shutdown to ensure no events are lost.
   */
  async flush(): Promise<void> {
    if (this.buffer.length === 0) return;

    const events = this.buffer;
    this.buffer = [];

    if (events.length === 1) {
      await this.client.publishEvent(events[0]);
      return;
    }

    await this.client.publishEvents(events);
  }

  /**
   * Stop the flush timer. Call this during shutdown.
   * Does NOT flush remaining buffered events -- call flush() first if needed.
   */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  /** Check if an event has threat > 0 in its salience. */
  private isThreatEvent(event: Event): boolean {
    return (event.salience?.threat ?? 0) > 0;
  }
}
