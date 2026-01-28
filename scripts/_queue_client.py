#!/usr/bin/env python
"""gRPC client for Orchestrator event queue stats.

Usage:
    python _queue_client.py --address localhost:50050 stats
"""
import sys
import argparse
from pathlib import Path

# Add orchestrator to sys.path to find generated protos
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT / "src" / "orchestrator"))

import grpc
from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc


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

    args = parser.parse_args()

    cmds = {
        "stats": cmd_stats,
        "list": cmd_list,
    }

    sys.exit(cmds[args.command](args))


if __name__ == "__main__":
    main()
