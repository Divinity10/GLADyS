#!/usr/bin/env python3
"""
GLADyS Memory Storage - Entry point.

Usage:
    python -m gladys_memory start [--host HOST] [--port PORT]
    python -m gladys_memory status

Commands:
    start   Start the Memory Storage gRPC server
    status  Show current configuration
"""

import argparse
import asyncio
import logging
import sys

from .config import settings
from .grpc_server import serve


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_start(args: argparse.Namespace) -> int:
    """Start the Memory Storage server."""
    setup_logging(args.verbose)

    # Use config defaults, override with CLI args if provided
    host = args.host if args.host != "0.0.0.0" else settings.server.host
    port = args.port if args.port is not None else settings.server.port

    print(f"Starting GLADyS Memory Storage on {host}:{port}")
    print(f"  Database: {settings.storage.host}:{settings.storage.port}/{settings.storage.database}")
    print(f"  Embedding model: {settings.embedding.model_name}")

    try:
        asyncio.run(serve(host=host, port=port))
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current configuration."""
    print("GLADyS Memory Storage Configuration")
    print("=" * 40)
    print(f"Server:")
    print(f"  Host: {settings.server.host}")
    print(f"  Port: {settings.server.port}")
    print(f"  Max workers: {settings.server.max_workers}")
    print()
    print(f"Storage:")
    print(f"  Host: {settings.storage.host}")
    print(f"  Port: {settings.storage.port}")
    print(f"  Database: {settings.storage.database}")
    print(f"  User: {settings.storage.user}")
    print()
    print(f"Embedding:")
    print(f"  Model: {settings.embedding.model_name}")
    print(f"  Dimensions: {settings.embedding.dimensions}")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="GLADyS Memory Storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start the Memory Storage server")
    start_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    start_parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 50051)")
    start_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    start_parser.set_defaults(func=cmd_start)

    # status command
    status_parser = subparsers.add_parser("status", help="Show configuration")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
