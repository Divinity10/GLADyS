import { describe, it, expect } from "vitest";
import {
  parseStartArgs,
  parseStopArgs,
  parseRecoverArgs,
  parseHealthCheckArgs,
  startArgsDefaults,
  startArgsDryRun,
  stopArgsDefaults,
  stopArgsForce,
  recoverArgsDefaults,
  healthCheckArgsDefaults,
} from "../src/args";

describe("StartArgs", () => {
  it("defaults to dryRun=false", () => {
    const args = parseStartArgs(undefined);

    expect(args.dryRun).toBe(false);
  });

  it("fromStruct parses dryRun", () => {
    const args = parseStartArgs({ dryRun: true });

    expect(args.dryRun).toBe(true);
  });

  it("parses snake_case dry_run", () => {
    const args = parseStartArgs({ dry_run: true });

    expect(args.dryRun).toBe(true);
  });

  it("missing fields get defaults", () => {
    const args = parseStartArgs({});

    expect(args.dryRun).toBe(false);
  });

  it("wrong type gets default", () => {
    const args = parseStartArgs({ dryRun: "not-a-bool" });

    expect(args.dryRun).toBe(false);
  });

  it("string 'true' coerces to true", () => {
    const args = parseStartArgs({ dryRun: "true" });

    expect(args.dryRun).toBe(true);
  });

  it("number 1 coerces to true", () => {
    const args = parseStartArgs({ dryRun: 1 });

    expect(args.dryRun).toBe(true);
  });

  it("raw escape hatch returns field value", () => {
    const args = parseStartArgs({ dryRun: false, customField: "custom-value" });

    expect(args.raw("customField")).toBe("custom-value");
  });

  it("raw returns defaultValue for missing key", () => {
    const args = parseStartArgs({});

    expect(args.raw("missing", "fallback")).toBe("fallback");
  });

  it("testDefaults factory works", () => {
    const args = startArgsDefaults();

    expect(args.dryRun).toBe(false);
  });

  it("testDryRun factory works", () => {
    const args = startArgsDryRun();

    expect(args.dryRun).toBe(true);
  });
});

describe("StopArgs", () => {
  it("defaults to force=false, timeoutMs=5000", () => {
    const args = parseStopArgs(undefined);

    expect(args.force).toBe(false);
    expect(args.timeoutMs).toBe(5000);
  });

  it("parses force and timeoutMs", () => {
    const args = parseStopArgs({ force: true, timeoutMs: 3000 });

    expect(args.force).toBe(true);
    expect(args.timeoutMs).toBe(3000);
  });

  it("parses snake_case timeout_ms", () => {
    const args = parseStopArgs({ timeout_ms: 2000 });

    expect(args.timeoutMs).toBe(2000);
  });

  it("testDefaults factory works", () => {
    const args = stopArgsDefaults();

    expect(args.force).toBe(false);
    expect(args.timeoutMs).toBe(5000);
  });

  it("testForce factory works", () => {
    const args = stopArgsForce();

    expect(args.force).toBe(true);
  });
});

describe("RecoverArgs", () => {
  it("defaults to strategy='default'", () => {
    const args = parseRecoverArgs(undefined);

    expect(args.strategy).toBe("default");
  });

  it("parses strategy", () => {
    const args = parseRecoverArgs({ strategy: "restart" });

    expect(args.strategy).toBe("restart");
  });

  it("testDefaults factory works", () => {
    const args = recoverArgsDefaults();

    expect(args.strategy).toBe("default");
  });
});

describe("HealthCheckArgs", () => {
  it("defaults to deep=false", () => {
    const args = parseHealthCheckArgs(undefined);

    expect(args.deep).toBe(false);
  });

  it("parses deep", () => {
    const args = parseHealthCheckArgs({ deep: true });

    expect(args.deep).toBe(true);
  });

  it("testDefaults factory works", () => {
    const args = healthCheckArgsDefaults();

    expect(args.deep).toBe(false);
  });
});
