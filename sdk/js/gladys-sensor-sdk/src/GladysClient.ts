import * as grpc from "@grpc/grpc-js";
import { randomUUID } from "crypto";
import { Event, ComponentState, RequestMetadata } from "./generated/common";
import {
  OrchestratorServiceClient as GrpcClient,
  OrchestratorServiceClient,
  EventAck,
  PublishEventRequest,
  PublishEventsRequest,
  PublishEventsResponse,
  RegisterRequest,
  RegisterResponse,
  HeartbeatRequest,
  HeartbeatResponse,
  ComponentCapabilities,
} from "./generated/orchestrator";

/**
 * gRPC client for communicating with the GLADyS orchestrator.
 * Wraps the generated OrchestratorServiceClient with Promise-based methods.
 */
export class GladysClient {
  private readonly stub: InstanceType<typeof OrchestratorServiceClient>;

  constructor(host: string, port: number);
  constructor(address: string, credentials: grpc.ChannelCredentials);
  constructor(
    hostOrAddress: string,
    portOrCredentials: number | grpc.ChannelCredentials
  ) {
    if (typeof portOrCredentials === "number") {
      this.stub = new GrpcClient(
        `${hostOrAddress}:${portOrCredentials}`,
        grpc.credentials.createInsecure()
      );
    } else {
      this.stub = new GrpcClient(hostOrAddress, portOrCredentials);
    }
  }

  async publishEvent(event: Event): Promise<EventAck> {
    const request: PublishEventRequest = {
      event,
      metadata: this.createMetadata(),
    };
    return new Promise((resolve, reject) => {
      this.stub.publishEvent(request, (err, response) => {
        if (err) return reject(err);
        resolve(response!.ack!);
      });
    });
  }

  async publishEvents(events: Event[]): Promise<PublishEventsResponse> {
    const request: PublishEventsRequest = {
      events,
      metadata: this.createMetadata(),
    };
    return new Promise((resolve, reject) => {
      this.stub.publishEvents(request, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  async register(
    sensorId: string,
    sensorType: string,
    capabilities: ComponentCapabilities,
    address: string = ""
  ): Promise<RegisterResponse> {
    const request: RegisterRequest = {
      componentId: sensorId,
      componentType: sensorType,
      address,
      capabilities,
      metadata: this.createMetadata(sensorId),
    };
    return new Promise((resolve, reject) => {
      this.stub.registerComponent(request, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  async heartbeat(
    componentId: string,
    state: ComponentState = ComponentState.COMPONENT_STATE_ACTIVE
  ): Promise<HeartbeatResponse> {
    const request: HeartbeatRequest = {
      componentId,
      state,
      metrics: {},
      metadata: this.createMetadata(componentId),
    };
    return new Promise((resolve, reject) => {
      this.stub.heartbeat(request, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  close(): void {
    this.stub.close();
  }

  private createMetadata(sourceComponent: string = ""): RequestMetadata {
    return {
      requestId: randomUUID(),
      timestampMs: Date.now(),
      sourceComponent,
      traceId: "",
      spanId: "",
    };
  }
}
