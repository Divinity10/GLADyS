/**
 * gRPC timeout configuration for GladysClient operations.
 * All values in milliseconds. Use NO_TIMEOUT constant for testing.
 */
export interface TimeoutConfig {
  /** Timeout for PublishEvent RPC. Default: 100ms */
  readonly publishEventMs: number;
  /** Timeout for Heartbeat RPC. Default: 5000ms */
  readonly heartbeatMs: number;
  /** Timeout for RegisterComponent RPC. Default: 10000ms */
  readonly registerMs: number;
}

/**
 * Default production timeout values per ADR-0005.
 */
export const DEFAULT_TIMEOUTS: TimeoutConfig = {
  publishEventMs: 100,
  heartbeatMs: 5000,
  registerMs: 10000,
} as const;

/**
 * Constant for disabling timeouts in test environments.
 * All timeout values set to 0 (gRPC interprets as no timeout).
 */
export const NO_TIMEOUT: TimeoutConfig = {
  publishEventMs: 0,
  heartbeatMs: 0,
  registerMs: 0,
} as const;

/**
 * Standard intent values for event classification.
 * Use these constants for consistency across sensors.
 */
export const Intent = {
  /** Event requires action/response */
  ACTIONABLE: "actionable",
  /** Event is informational only */
  INFORMATIONAL: "informational",
  /** Intent cannot be determined */
  UNKNOWN: "unknown",
} as const;

/**
 * Type alias for intent values.
 */
export type IntentValue = (typeof Intent)[keyof typeof Intent];
