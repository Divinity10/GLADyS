import { afterEach, describe, expect, it, vi } from "vitest";
import { EventBuilder } from "../src/EventBuilder";
import { EventDispatcher } from "../src/EventDispatcher";
import {
  FlowStrategy,
  NoOpStrategy,
  RateLimitStrategy,
  createStrategy,
} from "../src/FlowStrategy";

describe("FlowStrategy", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("test_noop_always_allows", () => {
    const strategy = new NoOpStrategy();
    const event = new EventBuilder("sensor").text("test").build();
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
  });

  it("test_noop_available_tokens_returns_max", () => {
    const strategy = new NoOpStrategy();
    expect(strategy.availableTokens()).toBe(Number.MAX_SAFE_INTEGER);
  });

  it("test_noop_consume_is_noop", () => {
    const strategy = new NoOpStrategy();
    const before = strategy.availableTokens();
    strategy.consume(10);
    expect(strategy.availableTokens()).toBe(before);
  });

  it("test_rate_limit_allows_within_budget", () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const strategy = new RateLimitStrategy(5, 1);
    const event = new EventBuilder("sensor").text("test").build();

    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
  });

  it("test_rate_limit_blocks_over_budget", () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const strategy = new RateLimitStrategy(5, 1);
    const event = new EventBuilder("sensor").text("test").build();

    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(false);
  });

  it("test_rate_limit_refills_over_time", () => {
    const times = [0, 0, 0, 0, 1100];
    vi.spyOn(Date, "now").mockImplementation(() => times.shift() ?? 1100);

    const strategy = new RateLimitStrategy(2, 2);
    const event = new EventBuilder("sensor").text("test").build();

    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(true);
    expect(strategy.shouldPublish(event)).toBe(false);
    expect(strategy.shouldPublish(event)).toBe(true);
  });

  it("test_rate_limit_available_tokens_reflects_budget", () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const strategy = new RateLimitStrategy(5, 1);
    const event = new EventBuilder("sensor").text("test").build();

    strategy.shouldPublish(event);
    strategy.shouldPublish(event);
    expect(strategy.availableTokens()).toBe(3);
  });

  it("test_rate_limit_consume_decrements_tokens", () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const strategy = new RateLimitStrategy(10, 1);
    strategy.consume(5);
    expect(strategy.availableTokens()).toBe(5);
  });

  it("test_rate_limit_rejects_zero_max_events", () => {
    expect(() => new RateLimitStrategy(0, 1)).toThrow();
  });

  it("test_rate_limit_rejects_zero_window", () => {
    expect(() => new RateLimitStrategy(1, 0)).toThrow();
  });

  it("test_rate_limit_rejects_negative_values", () => {
    expect(() => new RateLimitStrategy(-1, 1)).toThrow();
    expect(() => new RateLimitStrategy(1, -1)).toThrow();
  });

  it("test_create_none_strategy", () => {
    const strategy = createStrategy({ strategy: "none" });
    expect(strategy).toBeInstanceOf(NoOpStrategy);
  });

  it("test_create_rate_limit_strategy", () => {
    const strategy = createStrategy({
      strategy: "rate_limit",
      max_events: 5,
      window_seconds: 1,
    });
    expect(strategy).toBeInstanceOf(RateLimitStrategy);
  });

  it("test_create_unknown_falls_back_to_noop", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const strategy = createStrategy({ strategy: "mystery" });
    expect(strategy).toBeInstanceOf(NoOpStrategy);
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("test_create_default_is_noop", () => {
    const strategy = createStrategy({});
    expect(strategy).toBeInstanceOf(NoOpStrategy);
  });

  it("test_emit_with_noop_strategy_publishes", async () => {
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new NoOpStrategy(),
    });

    const event = new EventBuilder("sensor").text("first").build();
    const result = await dispatcher.emit(event);

    expect(result).toBe(true);
    expect(client.publishEvent).toHaveBeenCalledTimes(1);
    expect(client.publishEvent).toHaveBeenCalledWith(event);
  });

  it("test_emit_with_rate_limit_blocks_excess", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new RateLimitStrategy(1, 10),
    });

    const first = await dispatcher.emit(
      new EventBuilder("sensor").text("first").build()
    );
    const second = await dispatcher.emit(
      new EventBuilder("sensor").text("second").build()
    );

    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(client.publishEvent).toHaveBeenCalledTimes(1);
  });

  it("test_emit_threat_bypasses_rate_limit", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new RateLimitStrategy(1, 10),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("normal").build());
    const threat = new EventBuilder("sensor").text("danger").threat(true).build();
    const result = await dispatcher.emit(threat);

    expect(result).toBe(true);
    expect(client.publishEvent).toHaveBeenCalledTimes(2);
  });

  it("test_emit_returns_true_when_published", async () => {
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new NoOpStrategy(),
    });

    const result = await dispatcher.emit(
      new EventBuilder("sensor").text("first").build()
    );
    expect(result).toBe(true);
  });

  it("test_emit_returns_false_when_suppressed", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new RateLimitStrategy(1, 10),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("first").build());
    const result = await dispatcher.emit(
      new EventBuilder("sensor").text("blocked").build()
    );
    expect(result).toBe(false);
  });

  it("test_emit_threat_returns_true_when_rate_limited", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new RateLimitStrategy(1, 10),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("first").build());
    const threat = new EventBuilder("sensor").text("danger").threat(true).build();
    const result = await dispatcher.emit(threat);
    expect(result).toBe(true);
  });

  it("test_events_filtered_increments_on_suppression", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new RateLimitStrategy(1, 10),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("first").build());
    await dispatcher.emit(new EventBuilder("sensor").text("blocked").build());
    expect(dispatcher.eventsFiltered).toBe(1);
  });

  it("test_events_published_increments_on_send", async () => {
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new NoOpStrategy(),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("first").build());
    expect(dispatcher.eventsPublished).toBe(1);
  });

  it("test_counters_zero_initially", () => {
    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new NoOpStrategy(),
    });
    expect(dispatcher.eventsFiltered).toBe(0);
    expect(dispatcher.eventsPublished).toBe(0);
  });

  it("test_set_strategy_replaces_strategy", async () => {
    class DenyStrategy implements FlowStrategy {
      shouldPublish(): boolean {
        return false;
      }

      availableTokens(): number {
        return 0;
      }

      consume(_n: number): void {}
    }

    const client = {
      publishEvent: vi.fn().mockResolvedValue(undefined),
      publishEvents: vi.fn().mockResolvedValue(undefined),
    };
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy: new DenyStrategy(),
    });

    await dispatcher.emit(new EventBuilder("sensor").text("blocked").build());
    dispatcher.setStrategy(new NoOpStrategy());
    const allowed = new EventBuilder("sensor").text("allowed").build();
    await dispatcher.emit(allowed);

    expect(client.publishEvent).toHaveBeenCalledTimes(1);
    expect(client.publishEvent).toHaveBeenCalledWith(allowed);
  });
});
