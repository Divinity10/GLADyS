"""gRPC client for the Orchestrator service — stub creation and event publishing.

Library usage:
    from gladys_client.orchestrator import get_stub, publish_event, load_fixture
"""

import sys
import uuid
import json
from pathlib import Path

# Add orchestrator to sys.path to find generated protos
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.append(str(ROOT / "src" / "services" / "orchestrator"))

import grpc
from gladys_orchestrator.generated import common_pb2, orchestrator_pb2, orchestrator_pb2_grpc


def get_stub(address: str) -> orchestrator_pb2_grpc.OrchestratorServiceStub:
    channel = grpc.insecure_channel(address)
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)


def publish_event(stub, event_id: str, source: str, text: str,
                  salience=None) -> dict:
    """Publish a single event to the orchestrator. Blocks until processed.

    Returns dict with event_id and either status or error.
    """
    event = common_pb2.Event(id=event_id, source=source, raw_text=text)
    if salience is not None:
        event.salience.CopyFrom(salience)

    try:
        response = stub.PublishEvent(orchestrator_pb2.PublishEventRequest(event=event))
        ack = response.ack
        return {
            "event_id": ack.event_id,
            "status": "queued" if ack.queued else "immediate",
        }
    except grpc.RpcError as e:
        return {"event_id": event_id, "error": e.code().name}


def load_fixture(stub, json_path: str) -> list[dict]:
    """Load events from a JSON file and publish them sequentially.

    JSON format: [{"source": "...", "text": "...", "id": "..."(optional)}, ...]
    Returns list of result dicts from publish_event.
    """
    with open(json_path) as f:
        events = json.load(f)

    if not isinstance(events, list):
        raise ValueError("Fixture file must contain a JSON array")

    results = []
    for item in events:
        event_id = item.get("id", str(uuid.uuid4()))
        result = publish_event(
            stub,
            event_id=event_id,
            source=item.get("source", "fixture"),
            text=item.get("text", ""),
        )
        results.append(result)

    return results
