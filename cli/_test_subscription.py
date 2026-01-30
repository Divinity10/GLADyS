#!/usr/bin/env python
"""Test subscription delivery for debugging."""
import sys
import time
import threading
import uuid
from pathlib import Path

# Add orchestrator to sys.path to find generated protos
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "src" / "orchestrator"))

import grpc
from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
from gladys_orchestrator.generated import common_pb2


def subscriber_thread(address: str, received: list):
    """Background thread to subscribe to responses."""
    try:
        print(f"[Subscriber] Connecting to {address}...")
        channel = grpc.insecure_channel(address)
        stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

        subscriber_id = f"test-{uuid.uuid4().hex[:8]}"
        print(f"[Subscriber] Subscribing as {subscriber_id}")

        req = orchestrator_pb2.SubscribeResponsesRequest(
            subscriber_id=subscriber_id,
            include_immediate=True
        )

        responses = stub.SubscribeResponses(req)
        print(f"[Subscriber] Stream established, waiting for responses...")

        for resp in responses:
            print(f"[Subscriber] RECEIVED: event_id={resp.event_id}, text={resp.response_text[:50]}...")
            received.append(resp)

    except Exception as e:
        print(f"[Subscriber] Error: {e}")


def send_event(address: str, text: str, low_salience: bool = False):
    """Send a test event."""
    channel = grpc.insecure_channel(address)
    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

    event_id = str(uuid.uuid4())
    event = common_pb2.Event(
        id=event_id,
        source="test-subscription",
        raw_text=text,
    )

    if low_salience:
        event.salience.novelty = 0.1  # Force low salience -> queue path

    print(f"[Sender] Sending event {event_id[:8]}... (low_salience={low_salience})")

    def event_generator():
        yield event

    for ack in stub.PublishEvents(event_generator()):
        print(f"[Sender] Ack: accepted={ack.accepted}, queued={ack.queued}, response_text={ack.response_text[:50] if ack.response_text else '(none)'}...")
        return ack

    return None


def main():
    address = "localhost:50050"
    received = []

    # Start subscriber thread
    thread = threading.Thread(target=subscriber_thread, args=(address, received), daemon=True)
    thread.start()

    # Wait for subscription to establish
    time.sleep(1)

    # Send a low-salience event (goes through queue)
    print("\n=== Sending LOW salience event (queue path) ===")
    send_event(address, "Test subscription delivery", low_salience=True)

    # Wait for response to arrive
    print("\n[Main] Waiting for subscription to receive response...")
    for i in range(30):  # Wait up to 30 seconds
        if received:
            print(f"\n[Main] SUCCESS! Received {len(received)} response(s)")
            for r in received:
                print(f"  - event_id={r.event_id}, routing_path={r.routing_path}")
            return 0
        time.sleep(1)
        print(f"[Main] Still waiting... ({i+1}s)")

    print("\n[Main] TIMEOUT: No response received after 30 seconds")
    return 1


if __name__ == "__main__":
    sys.exit(main())
