export { GladysClient } from "./GladysClient";
export { EventBuilder } from "./EventBuilder";
export { SensorRegistration } from "./SensorRegistration";
export { HeartbeatManager } from "./HeartbeatManager";

// Re-export commonly used generated types
export { Event, ComponentState, RequestMetadata } from "./generated/common";
export {
  EventAck,
  ComponentCapabilities,
  RegisterResponse,
  HeartbeatResponse,
  TransportMode,
  InstancePolicy,
} from "./generated/orchestrator";
