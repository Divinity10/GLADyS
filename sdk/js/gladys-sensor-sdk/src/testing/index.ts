export { TestSensorHarness } from "./TestSensorHarness";

// Re-export commonly used types for test convenience
export { Command } from "../generated/orchestrator";
export { ComponentState } from "../generated/common";
export {
  type StartArgs,
  type StopArgs,
  type RecoverArgs,
  type HealthCheckArgs,
  startArgsDefaults,
  startArgsDryRun,
  stopArgsDefaults,
  stopArgsForce,
  recoverArgsDefaults,
  healthCheckArgsDefaults,
} from "../args";
export { type DispatchResult } from "../CommandDispatcher";
