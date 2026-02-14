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
import { type TimeoutConfig } from "./types";

/**
 * gRPC client for communicating with the GLADyS orchestrator.
 * Wraps the generated OrchestratorServiceClient with Promise-based methods.
 * Supports optional TimeoutConfig for deadline enforcement per ADR-0005.
 */
export class GladysClient {
  private readonly stub: InstanceType<typeof OrchestratorServiceClient>;
  private readonly timeouts: TimeoutConfig | undefined;

  constructor(host: string, port: number, timeouts?: TimeoutConfig);
  constructor(address: string, credentials: grpc.ChannelCredentials, timeouts?: TimeoutConfig);
  constructor(
    hostOrAddress: string,
    portOrCredentials: number | grpc.ChannelCredentials,
    timeouts?: TimeoutConfig
  ) {
    this.timeouts = timeouts;
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
    const deadline = this.deadlineOptions(this.timeouts?.publishEventMs);
    return new Promise((resolve, reject) => {
      if (deadline) {
        this.stub.publishEvent(request, new grpc.Metadata(), deadline, (err, response) => {
          if (err) return reject(err);
          resolve(response!.ack!);
        });
      } else {
        this.stub.publishEvent(request, (err, response) => {
          if (err) return reject(err);
          resolve(response!.ack!);
        });
      }
    });
  }

  async publishEvents(events: Event[]): Promise<PublishEventsResponse> {
    const request: PublishEventsRequest = {
      events,
      metadata: this.createMetadata(),
    };
    const deadline = this.deadlineOptions(this.timeouts?.publishEventMs);
    return new Promise((resolve, reject) => {
      if (deadline) {
        this.stub.publishEvents(request, new grpc.Metadata(), deadline, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      } else {
        this.stub.publishEvents(request, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      }
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
    const deadline = this.deadlineOptions(this.timeouts?.registerMs);
    return new Promise((resolve, reject) => {
      if (deadline) {
        this.stub.registerComponent(request, new grpc.Metadata(), deadline, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      } else {
        this.stub.registerComponent(request, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      }
    });
  }

  async heartbeat(
    componentId: string,
    state: ComponentState = ComponentState.COMPONENT_STATE_ACTIVE,
    errorMessage?: string
  ): Promise<HeartbeatResponse> {
    const request: HeartbeatRequest = {
      componentId,
      state,
      metadata: this.createMetadata(componentId),
    };

    // errorMessage field exists in proto (field 3) but may not be in generated types yet.
    // Assign it directly; protobuf wire format will include it if the field is defined.
    if (errorMessage) {
      (request as unknown as Record<string, unknown>)["errorMessage"] = errorMessage;
    }

    const deadline = this.deadlineOptions(this.timeouts?.heartbeatMs);
    return new Promise((resolve, reject) => {
      if (deadline) {
        this.stub.heartbeat(request, new grpc.Metadata(), deadline, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      } else {
        this.stub.heartbeat(request, (err, response) => {
          if (err) return reject(err);
          resolve(response!);
        });
      }
    });
  }

  close(): void {
    this.stub.close();
  }

  /**
   * Create gRPC call options with deadline if timeout > 0.
   * Returns undefined when no deadline is needed.
   */
  private deadlineOptions(timeoutMs?: number): Partial<grpc.CallOptions> | undefined {
    if (timeoutMs && timeoutMs > 0) {
      return { deadline: new Date(Date.now() + timeoutMs) };
    }
    return undefined;
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
