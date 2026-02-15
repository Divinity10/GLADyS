import { afterEach, describe, expect, it, vi } from "vitest";
import { EventBuilder } from "../src/EventBuilder";
import { EventDispatcher, type EmitResult } from "../src/EventDispatcher";
import { FlowStrategy, RateLimitStrategy } from "../src/FlowStrategy";
import { Event } from "../src/generated/common";

type MockClient = {
  publishEvent: ReturnType<typeof vi.fn>;
  publishEvents: ReturnType<typeof vi.fn>;
};

class BudgetStrategy implements FlowStrategy {
  private budget: number;
  availableCalls = 0;
  consumeCalls: number[] = [];

  constructor(budget: number) {
    this.budget = budget;
  }

  shouldPublish(_event: Event): boolean {
    return true;
  }

  availableTokens(): number {
    this.availableCalls += 1;
    return this.budget;
  }

  consume(n: number): void {
    this.consumeCalls.push(n);
    this.budget -= n;
  }
}

function makeClient(): MockClient {
  return {
    publishEvent: vi.fn().mockResolvedValue(undefined),
    publishEvents: vi.fn().mockResolvedValue(undefined),
  };
}

function makeEvent(
  label: string,
  options: { threat?: boolean; priority?: number } = {}
): Event {
  const event = new EventBuilder("sensor")
    .text(label)
    .structured({ priority: options.priority ?? 0 })
    .build();
  if (options.threat) {
    return new EventBuilder("sensor")
      .text(label)
      .structured({ priority: options.priority ?? 0 })
      .threat(true)
      .build();
  }
  return event;
}

function sentLabels(client: MockClient): string[] {
  const labels: string[] = [];
  for (const call of client.publishEvent.mock.calls) {
    labels.push((call[0] as Event).rawText ?? "");
  }
  for (const call of client.publishEvents.mock.calls) {
    labels.push(...(call[0] as Event[]).map((event) => event.rawText ?? ""));
  }
  return labels;
}

function expectResult(result: EmitResult, sent: number, suppressed: number): void {
  expect(result).toEqual({ sent, suppressed });
}

describe("EmitBatch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("test_emit_batch_empty_list", async () => {
    const strategy = new BudgetStrategy(10);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([]);

    expectResult(result, 0, 0);
    expect(strategy.availableCalls).toBe(0);
    expect(strategy.consumeCalls).toEqual([]);
    expect(client.publishEvent).not.toHaveBeenCalled();
    expect(client.publishEvents).not.toHaveBeenCalled();
  });

  it("test_emit_batch_all_threats", async () => {
    const strategy = new BudgetStrategy(0);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("t1", { threat: true }),
      makeEvent("t2", { threat: true }),
    ]);

    expectResult(result, 2, 0);
    expect(strategy.availableCalls).toBe(0);
    expect(strategy.consumeCalls).toEqual([]);
    expect(sentLabels(client)).toEqual(["t1", "t2"]);
  });

  it("test_emit_batch_all_within_budget", async () => {
    const strategy = new BudgetStrategy(3);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("a"),
      makeEvent("b"),
      makeEvent("c"),
    ]);

    expectResult(result, 3, 0);
    expect(strategy.consumeCalls).toEqual([3]);
    expect(sentLabels(client)).toEqual(["a", "b", "c"]);
  });

  it("test_emit_batch_zero_budget", async () => {
    const strategy = new BudgetStrategy(0);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("t", { threat: true }),
      makeEvent("a"),
      makeEvent("b"),
    ]);

    expectResult(result, 1, 2);
    expect(strategy.consumeCalls).toEqual([]);
    expect(dispatcher.eventsFiltered).toBe(2);
    expect(sentLabels(client)).toEqual(["t"]);
  });

  it("test_emit_batch_single_event", async () => {
    const strategy = new BudgetStrategy(1);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([makeEvent("single")]);

    expectResult(result, 1, 0);
    expect(strategy.consumeCalls).toEqual([1]);
    expect(client.publishEvent).toHaveBeenCalledTimes(1);
  });

  it("test_emit_batch_fifo_when_no_priority_fn", async () => {
    const strategy = new BudgetStrategy(2);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("a"),
      makeEvent("b"),
      makeEvent("c"),
    ]);

    expectResult(result, 2, 1);
    expect(sentLabels(client)).toEqual(["a", "b"]);
  });

  it("test_emit_batch_priority_fn_selects_top_n", async () => {
    const strategy = new BudgetStrategy(2);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy,
      priorityFn: (event) => Number((event.structured as any)?.priority ?? 0),
    });

    const result = await dispatcher.emitBatch([
      makeEvent("a", { priority: 1 }),
      makeEvent("b", { priority: 10 }),
      makeEvent("c", { priority: 5 }),
    ]);

    expectResult(result, 2, 1);
    expect(sentLabels(client)).toEqual(["b", "c"]);
  });

  it("test_emit_batch_priority_fn_preserves_order", async () => {
    const strategy = new BudgetStrategy(2);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy,
      priorityFn: (event) => Number((event.structured as any)?.priority ?? 0),
    });

    const result = await dispatcher.emitBatch([
      makeEvent("a", { priority: 5 }),
      makeEvent("b", { priority: 1 }),
      makeEvent("c", { priority: 10 }),
    ]);

    expectResult(result, 2, 1);
    expect(sentLabels(client)).toEqual(["a", "c"]);
  });

  it("test_emit_batch_equal_priority_preserves_order", async () => {
    const strategy = new BudgetStrategy(2);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", {
      strategy,
      priorityFn: () => 1,
    });

    const result = await dispatcher.emitBatch([
      makeEvent("a"),
      makeEvent("b"),
      makeEvent("c"),
    ]);

    expectResult(result, 2, 1);
    expect(sentLabels(client)).toEqual(["a", "b"]);
  });

  it("test_emit_batch_threats_bypass_budget", async () => {
    const strategy = new BudgetStrategy(0);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("t1", { threat: true }),
      makeEvent("a"),
      makeEvent("t2", { threat: true }),
      makeEvent("b"),
    ]);

    expectResult(result, 2, 2);
    expect(sentLabels(client)).toEqual(["t1", "t2"]);
  });

  it("test_emit_batch_threats_dont_consume_tokens", async () => {
    vi.spyOn(Date, "now").mockReturnValue(0);
    const strategy = new RateLimitStrategy(5, 10);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });
    const events = Array.from({ length: 10 }, (_, i) =>
      makeEvent(`t${i}`, { threat: true })
    );

    const before = strategy.availableTokens();
    const result = await dispatcher.emitBatch(events);
    const after = strategy.availableTokens();

    expectResult(result, 10, 0);
    expect(before).toBe(5);
    expect(after).toBe(5);
  });

  it("test_emit_batch_mixed_threats_and_candidates", async () => {
    const strategy = new BudgetStrategy(1);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("t1", { threat: true }),
      makeEvent("a"),
      makeEvent("b"),
      makeEvent("t2", { threat: true }),
    ]);

    expectResult(result, 3, 1);
    expect(sentLabels(client)).toEqual(["t1", "a", "t2"]);
  });

  it("test_emit_batch_updates_events_filtered", async () => {
    const strategy = new BudgetStrategy(1);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("a"),
      makeEvent("b"),
      makeEvent("c"),
    ]);

    expectResult(result, 1, 2);
    expect(dispatcher.eventsFiltered).toBe(2);
  });

  it("test_emit_batch_updates_events_published", async () => {
    const strategy = new BudgetStrategy(1);
    const client = makeClient();
    const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });

    const result = await dispatcher.emitBatch([
      makeEvent("t", { threat: true }),
      makeEvent("a"),
      makeEvent("b"),
    ]);

    expectResult(result, 2, 1);
    expect(dispatcher.eventsPublished).toBe(2);
  });

  it("test_emit_result_sent_plus_suppressed_equals_total", async () => {
    const scenarios: Array<{ budget: number; events: Event[] }> = [
      { budget: 0, events: [] },
      { budget: 0, events: [makeEvent("a"), makeEvent("b"), makeEvent("t", { threat: true })] },
      { budget: 2, events: [makeEvent("a"), makeEvent("b"), makeEvent("c")] },
      { budget: 1, events: [makeEvent("t", { threat: true }), makeEvent("a"), makeEvent("b")] },
    ];

    for (const scenario of scenarios) {
      const strategy = new BudgetStrategy(scenario.budget);
      const client = makeClient();
      const dispatcher = new EventDispatcher(client as any, "sensor", { strategy });
      const result = await dispatcher.emitBatch(scenario.events);
      expect(result.sent + result.suppressed).toBe(scenario.events.length);
    }
  });
});
