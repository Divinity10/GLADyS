import { Event } from "./generated/common";

/** Strategy interface — called before every event publish. */
export interface FlowStrategy {
  shouldPublish(event: Event): boolean;
}

/** Passthrough strategy that always allows publishing. */
export class NoOpStrategy implements FlowStrategy {
  shouldPublish(_event: Event): boolean {
    return true;
  }
}

/** Token bucket rate limiter for event publishing. */
export class RateLimitStrategy implements FlowStrategy {
  private readonly maxEvents: number;
  private readonly refillRatePerMs: number;
  private tokens: number;
  private lastRefillMs: number;

  constructor(maxEvents: number, windowSeconds: number) {
    if (!Number.isInteger(maxEvents) || maxEvents <= 0) {
      throw new Error("maxEvents must be a positive integer");
    }
    if (!Number.isInteger(windowSeconds) || windowSeconds <= 0) {
      throw new Error("windowSeconds must be a positive integer");
    }

    this.maxEvents = maxEvents;
    this.refillRatePerMs = maxEvents / (windowSeconds * 1000);
    this.tokens = maxEvents;
    this.lastRefillMs = Date.now();
  }

  shouldPublish(_event: Event): boolean {
    const nowMs = Date.now();
    const elapsedMs = Math.max(0, nowMs - this.lastRefillMs);
    this.lastRefillMs = nowMs;

    this.tokens = Math.min(
      this.maxEvents,
      this.tokens + elapsedMs * this.refillRatePerMs
    );

    if (this.tokens >= 1) {
      this.tokens -= 1;
      return true;
    }

    return false;
  }
}

function readPositiveInteger(config: Record<string, unknown>, key: string): number {
  const value = config[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new Error(`${key} must be a positive integer`);
  }
  return value;
}

/** Create a flow control strategy from config. */
export function createStrategy(config: Record<string, unknown>): FlowStrategy {
  const rawStrategy = config.strategy;
  const strategyName =
    typeof rawStrategy === "string" ? rawStrategy.toLowerCase() : "none";

  if (strategyName === "none") {
    return new NoOpStrategy();
  }

  if (strategyName === "rate_limit") {
    const maxEvents = readPositiveInteger(config, "max_events");
    const windowSeconds = readPositiveInteger(config, "window_seconds");
    return new RateLimitStrategy(maxEvents, windowSeconds);
  }

  console.warn(
    `Unknown flow control strategy '${strategyName}', falling back to NoOpStrategy`
  );
  return new NoOpStrategy();
}
