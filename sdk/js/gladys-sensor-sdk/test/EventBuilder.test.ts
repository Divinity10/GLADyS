import { describe, it, expect } from "vitest";
import { EventBuilder } from "../src/EventBuilder";

describe("EventBuilder", () => {
  it("sets required fields", () => {
    const event = new EventBuilder("melvor")
      .text("Player completed Firemaking task")
      .build();

    // id is a UUID (36 chars with hyphens)
    expect(event.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
    // timestamp is set to approximately now
    expect(event.timestamp).toBeInstanceOf(Date);
    const diff = Date.now() - event.timestamp!.getTime();
    expect(diff).toBeLessThan(1000);
    // source matches constructor arg
    expect(event.source).toBe("melvor");
    // raw_text matches builder arg
    expect(event.rawText).toBe("Player completed Firemaking task");
    // metadata is populated
    expect(event.metadata).toBeDefined();
    expect(event.metadata!.requestId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
    expect(event.metadata!.timestampMs).toBeGreaterThan(0);
    expect(event.metadata!.sourceComponent).toBe("melvor");
  });

  it("converts structured data", () => {
    const event = new EventBuilder("test-sensor")
      .text("test event")
      .structured({
        event_type: "skill_complete",
        skill: "Firemaking",
        level: 45,
        active: true,
      })
      .build();

    expect(event.structured).toBeDefined();
    expect(event.structured!.event_type).toBe("skill_complete");
    expect(event.structured!.skill).toBe("Firemaking");
    expect(event.structured!.level).toBe(45);
    expect(event.structured!.active).toBe(true);
  });

  it("sets intent and evaluation data", () => {
    const event = new EventBuilder("sudoku")
      .text("Puzzle state changed")
      .intent("actionable")
      .evaluationData({
        solution: [[1, 2, 3], [4, 5, 6]],
        difficulty: "hard",
      })
      .build();

    expect(event.intent).toBe("actionable");
    expect(event.evaluationData).toBeDefined();
    expect(event.evaluationData!.difficulty).toBe("hard");
    expect(event.evaluationData!.solution).toEqual([[1, 2, 3], [4, 5, 6]]);
  });

  it("rejects empty source", () => {
    expect(() => new EventBuilder("")).toThrow("source is required");
  });
});
