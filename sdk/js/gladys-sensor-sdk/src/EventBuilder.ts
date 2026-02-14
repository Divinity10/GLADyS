import { randomUUID } from "crypto";
import { Event, RequestMetadata } from "./generated/common";

/**
 * Fluent builder for GLADyS Event messages.
 * Populates adapter-responsibility fields (1-5, 11-12, 15).
 * Fields 6-10 are populated downstream and must not be set by adapters.
 */
export class EventBuilder {
  private readonly source: string;
  private rawText: string = "";
  private structuredData: { [key: string]: any } | undefined;
  private intentValue: string = "";
  private evaluationDataValue: { [key: string]: any } | undefined;
  private threatValue: number = 0;

  constructor(source: string) {
    if (!source) {
      throw new Error("source is required");
    }
    this.source = source;
  }

  text(rawText: string): this {
    this.rawText = rawText;
    return this;
  }

  structured(data: { [key: string]: any }): this {
    this.structuredData = data;
    return this;
  }

  intent(intent: string): this {
    this.intentValue = intent;
    return this;
  }

  evaluationData(data: { [key: string]: any }): this {
    this.evaluationDataValue = data;
    return this;
  }

  threat(isThreat: boolean): this {
    this.threatValue = isThreat ? 1.0 : 0;
    return this;
  }

  build(): Event {
    const now = new Date();
    const salience =
      this.threatValue > 0
        ? {
            threat: this.threatValue,
            salience: 0,
            habituation: 0,
            vector: {},
            modelId: "",
          }
        : undefined;

    return {
      id: randomUUID(),
      timestamp: now,
      source: this.source,
      rawText: this.rawText,
      structured: this.structuredData,
      intent: this.intentValue,
      evaluationData: this.evaluationDataValue,
      // Downstream-populated fields — leave at defaults
      salience,
      entityIds: [],
      tokens: [],
      tokenizerId: "",
      matchedHeuristicId: "",
      appStatus: "",
      // Request metadata
      metadata: {
        requestId: randomUUID(),
        timestampMs: now.getTime(),
        sourceComponent: this.source,
        traceId: "",
        spanId: "",
      },
    };
  }
}
