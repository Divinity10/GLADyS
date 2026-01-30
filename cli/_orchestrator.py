#!/usr/bin/env python
"""gRPC client for the Orchestrator service — queue inspection and event publishing.

Usage (CLI):
    python _orchestrator.py --address localhost:50050 stats
    python _orchestrator.py --address localhost:50050 list
    python _orchestrator.py --address localhost:50050 watch

Library:
    from _orchestrator import get_stub, publish_event, load_fixture
"""
import sys
import argparse
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

# Add orchestrator to sys.path to find generated protos
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "src" / "orchestrator"))

import json

import grpc
from gladys_orchestrator.generated import common_pb2, orchestrator_pb2, orchestrator_pb2_grpc


def get_stub(address: str) -> orchestrator_pb2_grpc.OrchestratorServiceStub:
    channel = grpc.insecure_channel(address)
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)


def cmd_stats(args) -> int:
    stub = get_stub(args.address)
    try:
        response = stub.GetQueueStats(orchestrator_pb2.GetQueueStatsRequest())
        print(f"Event Queue Statistics ({args.address}):")
        print(f"  Queue Size:      {response.queue_size}")
        print(f"  Total Queued:    {response.total_queued}")
        print(f"  Total Processed: {response.total_processed}")
        print(f"  Total Timed Out: {response.total_timed_out}")
        return 0
    except grpc.RpcError as e:
        print(f"Error: {e.details() if hasattr(e, 'details') else e}")
        return 1


def cmd_list(args) -> int:
    stub = get_stub(args.address)
    try:
        request = orchestrator_pb2.ListQueuedEventsRequest(limit=args.limit)
        response = stub.ListQueuedEvents(request)

        if response.total_count == 0:
            print("Queue is empty.")
            return 0

        showing = len(response.events)
        if showing < response.total_count:
            print(f"Showing {showing} of {response.total_count} queued events:\n")
        else:
            print(f"Queued events ({response.total_count}):\n")

        # Header
        print(f"{'Event ID':<40} {'Source':<15} {'Salience':>8} {'Age (ms)':>10} {'Heuristic'}")
        print("-" * 95)

        for ev in response.events:
            heuristic_str = f"{ev.matched_heuristic_id[:20]}... ({ev.heuristic_confidence:.0%})" if ev.matched_heuristic_id else "-"
            print(f"{ev.event_id:<40} {ev.source:<15} {ev.salience:>8.2f} {ev.age_ms:>10} {heuristic_str}")

        return 0
    except grpc.RpcError as e:
        print(f"Error: {e.details() if hasattr(e, 'details') else e}")
        return 1


def cmd_watch(args) -> int:
    """Watch queue activity in real-time. Ctrl+C to stop."""
    address = args.address
    poll_interval = args.interval
    stub = get_stub(address)

    # Track known event IDs to detect additions/removals
    known_ids: set[str] = set()

    def _timestamp():
        return datetime.now().strftime("%H:%M:%S")

    def _response_listener():
        """Background thread: subscribe to responses and print when events are processed."""
        try:
            subscriber_id = f"watch-{uuid.uuid4().hex[:8]}"
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=True,
            )
            for resp in stub.SubscribeResponses(req):
                path = {1: "IMMEDIATE", 2: "QUEUED"}.get(resp.routing_path, "?")
                text_preview = resp.response_text[:60].replace("\n", " ") if resp.response_text else "(empty)"
                print(f"  [{_timestamp()}] ✅ RESPONSE  {resp.event_id[:12]}  path={path}  {text_preview}")
        except grpc.RpcError:
            pass  # channel closed on exit
        except Exception as e:
            print(f"  [watch] subscription error: {e}")

    # Start response listener in background
    listener = threading.Thread(target=_response_listener, daemon=True)
    listener.start()

    print(f"Watching event queue at {address} (poll every {poll_interval}s, Ctrl+C to stop)\n")

    try:
        while True:
            try:
                resp = stub.ListQueuedEvents(orchestrator_pb2.ListQueuedEventsRequest(limit=0))
                current_ids = {ev.event_id for ev in resp.events}

                # Detect new events
                added = current_ids - known_ids
                for ev in resp.events:
                    if ev.event_id in added:
                        print(f"  [{_timestamp()}] ➕ QUEUED    {ev.event_id[:12]}  src={ev.source}  sal={ev.salience:.2f}")

                # Detect removed events (processed or timed out)
                removed = known_ids - current_ids
                for eid in removed:
                    print(f"  [{_timestamp()}] ➖ REMOVED   {eid[:12]}")

                known_ids = current_ids

            except grpc.RpcError as e:
                print(f"  [{_timestamp()}] ⚠️  poll error: {e.details() if hasattr(e, 'details') else e}")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print(f"\n[{_timestamp()}] Watch stopped.")
        return 0


## Library functions — used by dashboard routers and CLI


def publish_event(stub, event_id: str, source: str, text: str,
                  salience=None) -> dict:
    """Publish a single event to the orchestrator. Blocks until processed.

    Returns dict with event_id and either status or error.
    """
    event = common_pb2.Event(id=event_id, source=source, raw_text=text)
    if salience is not None:
        event.salience.CopyFrom(salience)

    try:
        def gen():
            yield event
        for ack in stub.PublishEvents(gen()):
            return {
                "event_id": ack.event_id,
                "status": "queued" if ack.queued else "immediate",
            }
            break
        return {"event_id": event_id, "error": "no_ack"}
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


## CLI entry point


def main():
    parser = argparse.ArgumentParser(description="Event queue stats client")
    parser.add_argument(
        "--address",
        default="localhost:50050",
        help="Orchestrator gRPC address (default: localhost:50050)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("stats", help="Show queue statistics")

    list_parser = subparsers.add_parser("list", help="List events in the queue")
    list_parser.add_argument("--limit", type=int, default=0, help="Max events to show (0=all)")

    watch_parser = subparsers.add_parser("watch", help="Watch queue activity in real-time (Ctrl+C to stop)")
    watch_parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")

    args = parser.parse_args()

    cmds = {
        "stats": cmd_stats,
        "list": cmd_list,
        "watch": cmd_watch,
    }

    sys.exit(cmds[args.command](args))


if __name__ == "__main__":
    main()
