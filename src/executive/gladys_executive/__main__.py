#!/usr/bin/env python3
"""
GLADyS Executive Stub - Entry point.

Usage:
    python -m gladys_executive start [--port PORT] [--memory-address ADDRESS]

Commands:
    start   Start the Executive stub gRPC server

Note: This is a test stub. The real Executive will be implemented in C#/.NET.
"""

import argparse
import asyncio
import logging
import os
import sys

# Load .env file (searches up directory tree to find project root .env)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass  # dotenv not installed, rely on environment variables


def resolve_ollama_endpoint() -> None:
    """Resolve OLLAMA_URL and OLLAMA_MODEL from named endpoints.

    Supports named endpoints like:
        OLLAMA_ENDPOINT_LOCAL=http://localhost:11434
        OLLAMA_ENDPOINT_LOCAL_MODEL=gemma3:1b
        OLLAMA_ENDPOINT=local
    """
    endpoint_name = os.environ.get("OLLAMA_ENDPOINT", "").strip().upper()
    if not endpoint_name:
        return

    endpoint_url = os.environ.get(f"OLLAMA_ENDPOINT_{endpoint_name}")
    if endpoint_url:
        os.environ["OLLAMA_URL"] = endpoint_url
        model_name = os.environ.get(f"OLLAMA_ENDPOINT_{endpoint_name}_MODEL")
        if model_name:
            os.environ["OLLAMA_MODEL"] = model_name


resolve_ollama_endpoint()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_start(args: argparse.Namespace) -> int:
    """Start the Executive stub server."""
    setup_logging(args.verbose)

    # Import here to avoid import errors if dependencies missing
    from .server import serve

    # Environment variables override CLI args
    ollama_url = os.environ.get("OLLAMA_URL", args.ollama_url)
    ollama_model = os.environ.get("OLLAMA_MODEL", args.ollama_model) or "gemma:2b"
    memory_address = os.environ.get("MEMORY_ADDRESS", args.memory_address)
    heuristic_store_path = os.environ.get("HEURISTIC_STORE_PATH", args.heuristic_store)

    print(f"Starting GLADyS Executive Stub on port {args.port}")
    if ollama_url:
        print(f"  Ollama: {ollama_url} (model: {ollama_model})")
    else:
        print("  Ollama: not configured (no LLM responses)")
    if memory_address:
        print(f"  Memory: {memory_address}")
    else:
        print(f"  Memory: file storage ({heuristic_store_path})")
    print("  (This is a test stub - the real Executive will be C#/.NET)")

    try:
        asyncio.run(serve(
            port=args.port,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            memory_address=memory_address,
            heuristic_store_path=heuristic_store_path,
        ))
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="GLADyS Executive Stub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start the Executive stub server")
    start_parser.add_argument("--port", type=int, default=50053, help="Port to listen on")
    start_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    start_parser.add_argument(
        "--ollama-url",
        type=str,
        default=None,
        help="Ollama server URL (or set OLLAMA_URL env var)",
    )
    start_parser.add_argument(
        "--ollama-model",
        type=str,
        default=None,
        help="Ollama model name (or set OLLAMA_MODEL env var)",
    )
    start_parser.add_argument(
        "--memory-address",
        type=str,
        default=None,
        help="Memory service address (e.g., localhost:50051)",
    )
    start_parser.add_argument(
        "--heuristic-store",
        type=str,
        default="heuristics.json",
        help="Path to heuristics JSON file (fallback storage)",
    )
    start_parser.set_defaults(func=cmd_start)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
