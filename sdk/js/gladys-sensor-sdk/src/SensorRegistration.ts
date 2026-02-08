import { GladysClient } from "./GladysClient";
import {
  ComponentCapabilities,
  RegisterResponse,
} from "./generated/orchestrator";

/**
 * One-shot registration helper for sensors.
 */
export class SensorRegistration {
  static async register(
    client: GladysClient,
    sensorId: string,
    sensorType: string,
    capabilities: ComponentCapabilities
  ): Promise<RegisterResponse> {
    return client.register(sensorId, sensorType, capabilities);
  }
}
