/**
 * Per-command typed arguments with lenient parsing.
 * Missing fields get defaults, wrong types get defaults, never throws.
 * Use raw() escape hatch for undocumented/sensor-specific fields.
 */

/** Base interface for all command argument types. */
export interface CommandArgs {
  /** Get raw value from args struct. Returns defaultValue if key doesn't exist. */
  raw(key: string, defaultValue?: unknown): unknown;
}

// --- Helpers for lenient parsing ---

function asBool(value: unknown, defaultValue: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value.toLowerCase() === "true") return true;
    if (value.toLowerCase() === "false") return false;
  }
  if (typeof value === "number") return value !== 0;
  return defaultValue;
}

function asNumber(value: unknown, defaultValue: number): number {
  if (typeof value === "number" && !isNaN(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (!isNaN(parsed)) return parsed;
  }
  return defaultValue;
}

function asString(value: unknown, defaultValue: string): string {
  if (typeof value === "string") return value;
  if (value !== null && value !== undefined) return String(value);
  return defaultValue;
}

// --- StartArgs ---

/** Arguments for START command. */
export interface StartArgs extends CommandArgs {
  /** If true, validate configuration but don't start. Default: false */
  readonly dryRun: boolean;
}

class StartArgsImpl implements StartArgs {
  readonly dryRun: boolean;
  private readonly fields: Record<string, unknown>;

  constructor(fields: Record<string, unknown>) {
    this.fields = fields;
    this.dryRun = asBool(fields["dryRun"] ?? fields["dry_run"], false);
  }

  raw(key: string, defaultValue?: unknown): unknown {
    return this.fields[key] ?? defaultValue;
  }

  /** Parse from struct with lenient coercion. */
  static fromStruct(struct: Record<string, unknown>): StartArgs {
    return new StartArgsImpl(struct ?? {});
  }

  /** Test factory with all defaults. */
  static testDefaults(): StartArgs {
    return new StartArgsImpl({});
  }

  /** Test factory with dryRun=true. */
  static testDryRun(): StartArgs {
    return new StartArgsImpl({ dryRun: true });
  }
}

/** Parse StartArgs from a plain object. */
export function parseStartArgs(struct: Record<string, unknown> | undefined): StartArgs {
  return StartArgsImpl.fromStruct(struct ?? {});
}

/** Create StartArgs with all defaults (for testing). */
export function startArgsDefaults(): StartArgs {
  return StartArgsImpl.testDefaults();
}

/** Create StartArgs with dryRun=true (for testing). */
export function startArgsDryRun(): StartArgs {
  return StartArgsImpl.testDryRun();
}

// --- StopArgs ---

/** Arguments for STOP command. */
export interface StopArgs extends CommandArgs {
  /** If true, force immediate shutdown without cleanup. Default: false */
  readonly force: boolean;
  /** Shutdown timeout in milliseconds. Default: 5000 */
  readonly timeoutMs: number;
}

class StopArgsImpl implements StopArgs {
  readonly force: boolean;
  readonly timeoutMs: number;
  private readonly fields: Record<string, unknown>;

  constructor(fields: Record<string, unknown>) {
    this.fields = fields;
    this.force = asBool(fields["force"], false);
    this.timeoutMs = asNumber(fields["timeoutMs"] ?? fields["timeout_ms"], 5000);
  }

  raw(key: string, defaultValue?: unknown): unknown {
    return this.fields[key] ?? defaultValue;
  }

  static fromStruct(struct: Record<string, unknown>): StopArgs {
    return new StopArgsImpl(struct ?? {});
  }

  static testDefaults(): StopArgs {
    return new StopArgsImpl({});
  }

  static testForce(): StopArgs {
    return new StopArgsImpl({ force: true });
  }
}

/** Parse StopArgs from a plain object. */
export function parseStopArgs(struct: Record<string, unknown> | undefined): StopArgs {
  return StopArgsImpl.fromStruct(struct ?? {});
}

/** Create StopArgs with all defaults (for testing). */
export function stopArgsDefaults(): StopArgs {
  return StopArgsImpl.testDefaults();
}

/** Create StopArgs with force=true (for testing). */
export function stopArgsForce(): StopArgs {
  return StopArgsImpl.testForce();
}

// --- RecoverArgs ---

/** Arguments for RECOVER command. */
export interface RecoverArgs extends CommandArgs {
  /** Recovery strategy identifier. Default: "default" */
  readonly strategy: string;
}

class RecoverArgsImpl implements RecoverArgs {
  readonly strategy: string;
  private readonly fields: Record<string, unknown>;

  constructor(fields: Record<string, unknown>) {
    this.fields = fields;
    this.strategy = asString(fields["strategy"], "default");
  }

  raw(key: string, defaultValue?: unknown): unknown {
    return this.fields[key] ?? defaultValue;
  }

  static fromStruct(struct: Record<string, unknown>): RecoverArgs {
    return new RecoverArgsImpl(struct ?? {});
  }

  static testDefaults(): RecoverArgs {
    return new RecoverArgsImpl({});
  }
}

/** Parse RecoverArgs from a plain object. */
export function parseRecoverArgs(struct: Record<string, unknown> | undefined): RecoverArgs {
  return RecoverArgsImpl.fromStruct(struct ?? {});
}

/** Create RecoverArgs with all defaults (for testing). */
export function recoverArgsDefaults(): RecoverArgs {
  return RecoverArgsImpl.testDefaults();
}

// --- HealthCheckArgs ---

/** Arguments for HEALTH_CHECK command. */
export interface HealthCheckArgs extends CommandArgs {
  /** If true, perform deep health check. Default: false */
  readonly deep: boolean;
}

class HealthCheckArgsImpl implements HealthCheckArgs {
  readonly deep: boolean;
  private readonly fields: Record<string, unknown>;

  constructor(fields: Record<string, unknown>) {
    this.fields = fields;
    this.deep = asBool(fields["deep"], false);
  }

  raw(key: string, defaultValue?: unknown): unknown {
    return this.fields[key] ?? defaultValue;
  }

  static fromStruct(struct: Record<string, unknown>): HealthCheckArgs {
    return new HealthCheckArgsImpl(struct ?? {});
  }

  static testDefaults(): HealthCheckArgs {
    return new HealthCheckArgsImpl({});
  }
}

/** Parse HealthCheckArgs from a plain object. */
export function parseHealthCheckArgs(struct: Record<string, unknown> | undefined): HealthCheckArgs {
  return HealthCheckArgsImpl.fromStruct(struct ?? {});
}

/** Create HealthCheckArgs with all defaults (for testing). */
export function healthCheckArgsDefaults(): HealthCheckArgs {
  return HealthCheckArgsImpl.testDefaults();
}
