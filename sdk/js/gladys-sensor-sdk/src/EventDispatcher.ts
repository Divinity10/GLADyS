import { GladysClient } from "./GladysClient";
import { Event } from "./generated/common";
import { FlowStrategy, NoOpStrategy } from "./FlowStrategy";

export interface EmitResult {
  sent: number;
  suppressed: number;
}

type IndexedEvent = {
  index: number;
  event: Event;
};

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
  private readonly priorityFn?: (event: Event) => number;
  private strategy: FlowStrategy;
  private buffer: Event[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private eventsFilteredValue = 0;
  private eventsPublishedValue = 0;

  constructor(
    client: GladysClient,
    source: string,
    options?: {
      flushIntervalMs?: number;
      immediateOnThreat?: boolean;
      strategy?: FlowStrategy;
      priorityFn?: (event: Event) => number;
    }
  ) {
    this.client = client;
    this.source = source;
    this.flushIntervalMs = options?.flushIntervalMs ?? 0;
    this.immediateOnThreat = options?.immediateOnThreat ?? true;
    this.strategy = options?.strategy ?? new NoOpStrategy();
    this.priorityFn = options?.priorityFn;

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
  async emit(event: Event): Promise<boolean> {
    const isThreat = this.isThreatEvent(event);

    if (this.immediateOnThreat && isThreat && this.flushIntervalMs > 0) {
      // Hybrid mode: threat events bypass buffer
      await this.client.publishEvent(event);
      this.eventsPublishedValue += 1;
      return true;
    }

    // Threat events always bypass strategy checks.
    if (!isThreat && !this.strategy.shouldPublish(event)) {
      this.eventsFilteredValue += 1;
      return false;
    }

    if (this.flushIntervalMs === 0) {
      // Immediate mode: send every event now
      await this.client.publishEvent(event);
      this.eventsPublishedValue += 1;
      return true;
    }

    // Scheduled mode: buffer for timer flush
    this.buffer.push(event);
    this.eventsPublishedValue += 1;
    return true;
  }

  async emitBatch(events: Event[]): Promise<EmitResult> {
    if (events.length === 0) {
      return { sent: 0, suppressed: 0 };
    }

    const { threats, candidates } = this.partitionThreats(events);

    if (candidates.length === 0) {
      const toSend = this.reorderOriginal(events, threats, []);
      await this.sendEvents(toSend);
      this.eventsPublishedValue += toSend.length;
      return { sent: toSend.length, suppressed: 0 };
    }

    const budget = this.strategy.availableTokens();
    let kept: IndexedEvent[];
    let suppressed = 0;

    if (budget >= candidates.length) {
      this.strategy.consume(candidates.length);
      kept = [...candidates];
    } else if (budget <= 0) {
      kept = [];
      suppressed = candidates.length;
      this.eventsFilteredValue += suppressed;
    } else {
      kept = this.selectByPriority(candidates, budget);
      this.strategy.consume(kept.length);
      suppressed = candidates.length - kept.length;
      this.eventsFilteredValue += suppressed;
    }

    const toSend = this.reorderOriginal(events, threats, kept);
    await this.sendEvents(toSend);
    this.eventsPublishedValue += toSend.length;
    return { sent: toSend.length, suppressed };
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

  /** Replace the active flow control strategy. */
  setStrategy(strategy: FlowStrategy): void {
    this.strategy = strategy;
  }

  get eventsFiltered(): number {
    return this.eventsFilteredValue;
  }

  get eventsPublished(): number {
    return this.eventsPublishedValue;
  }

  private partitionThreats(events: Event[]): {
    threats: IndexedEvent[];
    candidates: IndexedEvent[];
  } {
    const threats: IndexedEvent[] = [];
    const candidates: IndexedEvent[] = [];

    events.forEach((event, index) => {
      if (this.isThreatEvent(event)) {
        threats.push({ index, event });
        return;
      }
      candidates.push({ index, event });
    });

    return { threats, candidates };
  }

  private selectByPriority(
    candidates: IndexedEvent[],
    budget: number
  ): IndexedEvent[] {
    if (!this.priorityFn) {
      return candidates.slice(0, budget);
    }

    const scored = candidates.map(({ index, event }) => ({
      index,
      event,
      priority: this.priorityFn!(event),
    }));
    scored.sort((a, b) => b.priority - a.priority || a.index - b.index);
    const selected = scored.slice(0, budget);
    selected.sort((a, b) => a.index - b.index);
    return selected.map(({ index, event }) => ({ index, event }));
  }

  private reorderOriginal(
    original: Event[],
    threats: IndexedEvent[],
    kept: IndexedEvent[]
  ): Event[] {
    const selectedIndices = new Set<number>([
      ...threats.map((item) => item.index),
      ...kept.map((item) => item.index),
    ]);

    return original.filter((_, index) => selectedIndices.has(index));
  }

  private async sendEvents(events: Event[]): Promise<void> {
    if (events.length === 0) {
      return;
    }

    if (this.flushIntervalMs === 0) {
      if (events.length === 1) {
        await this.client.publishEvent(events[0]);
        return;
      }
      await this.client.publishEvents(events);
      return;
    }

    if (this.immediateOnThreat) {
      const buffered: Event[] = [];
      for (const event of events) {
        if (this.isThreatEvent(event)) {
          await this.client.publishEvent(event);
        } else {
          buffered.push(event);
        }
      }
      this.buffer.push(...buffered);
      return;
    }

    this.buffer.push(...events);
  }

  /** Check if an event has threat > 0 in its salience. */
  private isThreatEvent(event: Event): boolean {
    return (event.salience?.threat ?? 0) > 0;
  }
}
