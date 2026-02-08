import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as grpc from "@grpc/grpc-js";
import { GladysClient } from "../src/GladysClient";
import { EventBuilder } from "../src/EventBuilder";
import {
  OrchestratorServiceService,
  OrchestratorServiceServer,
  PublishEventRequest,
  PublishEventResponse,
  PublishEventsRequest,
  PublishEventsResponse,
  RegisterRequest,
  RegisterResponse,
  HeartbeatRequest,
  HeartbeatResponse,
} from "../src/generated/orchestrator";
import { Event } from "../src/generated/common";

/**
 * Test gRPC server that returns canned responses.
 * Equivalent to Java SDK's InProcessServer pattern.
 */
function createTestHandlers(): Partial<OrchestratorServiceServer> {
  return {
    publishEvent(
      call: grpc.ServerUnaryCall<PublishEventRequest, PublishEventResponse>,
      callback: grpc.sendUnaryData<PublishEventResponse>
    ) {
      const eventId = call.request.event?.id ?? "";
      callback(null, {
        ack: {
          eventId,
          accepted: true,
          errorMessage: "",
          responseId: "",
          responseText: "",
          predictedSuccess: 0,
          predictionConfidence: 0,
          routedToLlm: false,
          matchedHeuristicId: "",
          queued: false,
        },
      });
    },
    publishEvents(
      call: grpc.ServerUnaryCall<PublishEventsRequest, PublishEventsResponse>,
      callback: grpc.sendUnaryData<PublishEventsResponse>
    ) {
      callback(null, {
        acceptedCount: call.request.events.length,
        errors: [],
      });
    },
    registerComponent(
      call: grpc.ServerUnaryCall<RegisterRequest, RegisterResponse>,
      callback: grpc.sendUnaryData<RegisterResponse>
    ) {
      callback(null, {
        success: true,
        errorMessage: "",
        assignedId: call.request.componentId,
      });
    },
    heartbeat(
      call: grpc.ServerUnaryCall<HeartbeatRequest, HeartbeatResponse>,
      callback: grpc.sendUnaryData<HeartbeatResponse>
    ) {
      callback(null, {
        acknowledged: true,
        pendingCommands: [],
      });
    },
  };
}

describe("GladysClient", () => {
  let server: grpc.Server;
  let client: GladysClient;
  let port: number;

  beforeAll(async () => {
    server = new grpc.Server();
    server.addService(
      OrchestratorServiceService,
      createTestHandlers() as grpc.UntypedServiceImplementation
    );

    port = await new Promise<number>((resolve, reject) => {
      server.bindAsync(
        "localhost:0",
        grpc.ServerCredentials.createInsecure(),
        (err, assignedPort) => {
          if (err) return reject(err);
          resolve(assignedPort);
        }
      );
    });

    client = new GladysClient("localhost", port);
  });

  afterAll(() => {
    client.close();
    server.forceShutdown();
  });

  it("publishEvent returns ack", async () => {
    const event = new EventBuilder("test-sensor")
      .text("Test event")
      .build();

    const ack = await client.publishEvent(event);

    expect(ack.eventId).toBe(event.id);
    expect(ack.accepted).toBe(true);
  });

  it("publishEvents returns summary receipt", async () => {
    const events = [
      new EventBuilder("test-sensor").text("Event 1").build(),
      new EventBuilder("test-sensor").text("Event 2").build(),
      new EventBuilder("test-sensor").text("Event 3").build(),
    ];

    const response = await client.publishEvents(events);

    expect(response.acceptedCount).toBe(3);
    expect(response.errors).toHaveLength(0);
  });
});
