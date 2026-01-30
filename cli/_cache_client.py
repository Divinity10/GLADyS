#!/usr/bin/env python
import sys
import argparse
from pathlib import Path

# Add gladys_client to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_client"))

from gladys_client.cache import get_stub

# Proto types needed by CLI commands (gladys_client.cache already added memory to sys.path)
from gladys_memory import memory_pb2, memory_pb2_grpc


def cmd_stats(args):
    stub = get_stub(args.address)
    try:
        response = stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        print(f"Cache Statistics for {args.address}:")
        print(f"  Size: {response.current_size} / {response.max_capacity}")
        print(f"  Hit Rate: {response.hit_rate:.2%}")
        print(f"  Total Hits: {response.total_hits}")
        print(f"  Total Misses: {response.total_misses}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_list(args):
    stub = get_stub(args.address)
    try:
        response = stub.ListCachedHeuristics(memory_pb2.ListCachedHeuristicsRequest(limit=args.limit))
        if not response.heuristics:
            print("Cache is empty.")
            return 0

        print(f"{'ID':<36} {'Hits':<6} {'Name':<30}")
        print("-" * 80)
        for h in response.heuristics:
            print(f"{h.heuristic_id:<36} {h.hit_count:<6} {h.name:<30}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_flush(args):
    stub = get_stub(args.address)
    try:
        response = stub.FlushCache(memory_pb2.FlushCacheRequest())
        print(f"Flushed {response.entries_flushed} entries from cache.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_evict(args):
    stub = get_stub(args.address)
    try:
        response = stub.EvictFromCache(memory_pb2.EvictFromCacheRequest(heuristic_id=args.id))
        if response.found:
            print(f"Heuristic {args.id} evicted.")
        else:
            print(f"Heuristic {args.id} not found in cache.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="localhost:50052", help="memory-rust gRPC address")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("stats")

    list_p = subparsers.add_parser("list")
    list_p.add_argument("--limit", type=int, default=0)

    subparsers.add_parser("flush")

    evict_p = subparsers.add_parser("evict")
    evict_p.add_argument("id")

    args = parser.parse_args()

    cmds = {
        "stats": cmd_stats,
        "list": cmd_list,
        "flush": cmd_flush,
        "evict": cmd_evict,
    }

    sys.exit(cmds[args.command](args))


if __name__ == "__main__":
    main()
