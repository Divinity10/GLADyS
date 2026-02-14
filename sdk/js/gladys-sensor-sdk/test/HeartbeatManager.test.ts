import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import * as grpc from "@grpc/grpc-js";
import { GladysClient } from "../src/GladysClient";
import { HeartbeatManager } from "../src/HeartbeatManager";
import { ComponentState } from "../src/generated/common";
import {
  OrchestratorServiceService,
  OrchestratorServiceServer,
  HeartbeatRequest,
  HeartbeatResponse,
  PublishEventRequest,
  PublishEventResponse,
  PublishEventsRequest,
  PublishEventsResponse,
  RegisterRequest,
  RegisterResponse,
} from "../src/generated/orchestrator";

describe("HeartbeatManager", () => {
  let server: grpc.Server;
  let client: GladysClient;
  let port: number;
  let heartbeatCount: number;
  let lastReceivedState: ComponentState;

  const handlers: Partial<OrchestratorServiceServer> = {
    heartbeat(
      call: grpc.ServerUnaryCall<HeartbeatRequest, HeartbeatResponse>,
      callback: grpc.sendUnaryData<HeartbeatResponse>
    ) {
      heartbeatCount++;
      lastReceivedState = call.request.state;
      callback(null, {
        acknowledged: true,
        pendingCommands: [],
      });
    },
    // Stub handlers required by the service definition
    publishEvent(
      call: grpc.ServerUnaryCall<PublishEventRequest, PublishEventResponse>,
      callback: grpc.sendUnaryData<PublishEventResponse>
    ) {
      callback(null, { ack: undefined });
    },
    publishEvents(
      call: grpc.ServerUnaryCall<PublishEventsRequest, PublishEventsResponse>,
      callback: grpc.sendUnaryData<PublishEventsResponse>
    ) {
      callback(null, { acks: [] });
    },
    registerComponent(
      call: grpc.ServerUnaryCall<RegisterRequest, RegisterResponse>,
      callback: grpc.sendUnaryData<RegisterResponse>
    ) {
      callback(null, { success: true, errorMessage: "", assignedId: "" });
    },
  };

  beforeAll(async () => {
    heartbeatCount = 0;
    lastReceivedState = ComponentState.COMPONENT_STATE_UNKNOWN;

    server = new grpc.Server();
    server.addService(
      OrchestratorServiceService,
      handlers as grpc.UntypedServiceImplementation
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

  it("sends periodic heartbeats", async () => {
    heartbeatCount = 0;
    const hb = new HeartbeatManager(client, "test-sensor", 1); // 1s interval

    hb.start();
    expect(hb.isRunning()).toBe(true);

    // Wait for initial heartbeat + at least one periodic heartbeat
    await new Promise((r) => setTimeout(r, 2500));

    hb.stop();
    expect(heartbeatCount).toBeGreaterThanOrEqual(2);
  });

  it("stops cleanly", async () => {
    heartbeatCount = 0;
    const hb = new HeartbeatManager(client, "test-sensor", 1);

    hb.start();
    expect(hb.isRunning()).toBe(true);

    // Wait for initial heartbeat
    await new Promise((r) => setTimeout(r, 200));

    hb.stop();
    expect(hb.isRunning()).toBe(false);

    const countAtStop = heartbeatCount;
    // Wait to verify no more heartbeats fire
    await new Promise((r) => setTimeout(r, 1500));
    expect(heartbeatCount).toBe(countAtStop);
  });

  it("sends current state with heartbeat", async () => {
    heartbeatCount = 0;
    lastReceivedState = ComponentState.COMPONENT_STATE_UNKNOWN;
    const hb = new HeartbeatManager(client, "test-sensor", 1);

    // Default state should be ACTIVE
    hb.start();
    await new Promise((r) => setTimeout(r, 200));
    expect(lastReceivedState).toBe(ComponentState.COMPONENT_STATE_ACTIVE);

    // Change state to PAUSED
    hb.setState(ComponentState.COMPONENT_STATE_PAUSED);
    expect(hb.getState()).toBe(ComponentState.COMPONENT_STATE_PAUSED);

    // Wait for next heartbeat with new state
    await new Promise((r) => setTimeout(r, 1200));
    expect(lastReceivedState).toBe(ComponentState.COMPONENT_STATE_PAUSED);

    hb.stop();
  });

  it("error message survives heartbeat failure", async () => {
    vi.useFakeTimers();
    let hb: HeartbeatManager | null = null;
    try {
      const heartbeat = vi
        .fn()
        .mockRejectedValueOnce(new Error("network"))
        .mockResolvedValue({ acknowledged: true, pendingCommands: [] });

      const mockClient = { heartbeat } as unknown as GladysClient;
      hb = new HeartbeatManager(mockClient, "test-sensor", 1);
      hb.setErrorMessage("dispatch failed");

      hb.start();
      await Promise.resolve();

      expect(heartbeat).toHaveBeenNthCalledWith(
        1,
        "test-sensor",
        ComponentState.COMPONENT_STATE_ACTIVE,
        "dispatch failed"
      );

      await vi.advanceTimersByTimeAsync(1000);
      expect(heartbeat).toHaveBeenNthCalledWith(
        2,
        "test-sensor",
        ComponentState.COMPONENT_STATE_ACTIVE,
        "dispatch failed"
      );

      await vi.advanceTimersByTimeAsync(1000);
      expect(heartbeat).toHaveBeenNthCalledWith(
        3,
        "test-sensor",
        ComponentState.COMPONENT_STATE_ACTIVE,
        undefined
      );

    } finally {
      hb?.stop();
      vi.useRealTimers();
    }
  });
});
