// Existing SDK classes
export { GladysClient } from "./GladysClient";
export { EventBuilder } from "./EventBuilder";
export { SensorRegistration } from "./SensorRegistration";
export { HeartbeatManager } from "./HeartbeatManager";

// Command handling
export {
  CommandDispatcher,
  type CommandHandler,
  type SimpleCommandHandler,
  type CommandErrorHandler,
  type DispatchResult,
} from "./CommandDispatcher";

// Event dispatch
export { EventDispatcher } from "./EventDispatcher";
export {
  NoOpStrategy,
  RateLimitStrategy,
  createStrategy,
  type FlowStrategy,
} from "./FlowStrategy";

// Sensor lifecycle
export {
  createSensorLifecycle,
  type SensorLifecycle,
  type SensorLifecycleOptions,
} from "./SensorLifecycle";

// Typed command args
export {
  type CommandArgs,
  type StartArgs,
  type StopArgs,
  type RecoverArgs,
  type HealthCheckArgs,
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
} from "./args";

// Timeout configuration
export {
  type TimeoutConfig,
  DEFAULT_TIMEOUTS,
  NO_TIMEOUT,
  Intent,
  type IntentValue,
} from "./types";

// Re-export commonly used generated types
export { Event, ComponentState, RequestMetadata } from "./generated/common";
export {
  EventAck,
  ComponentCapabilities,
  RegisterResponse,
  HeartbeatResponse,
  TransportMode,
  InstancePolicy,
  Command,
  type PendingCommand,
} from "./generated/orchestrator";
