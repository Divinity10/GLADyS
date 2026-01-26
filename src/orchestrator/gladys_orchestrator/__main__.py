#!/usr/bin/env python3
"""
GLADyS Orchestrator - Entry point.

Usage:
    python -m gladys_orchestrator start [--host HOST] [--port PORT] [--moment-window MS]
    python -m gladys_orchestrator generate-proto

Commands:
    start           Start the Orchestrator gRPC server
    generate-proto  Generate Python code from proto files
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from gladys_common import setup_logging as gladys_setup_logging

from .config import OrchestratorConfig
from .server import serve


def setup_logging(verbose: bool = False) -> None:
    """Configure logging using gladys_common."""
    if verbose:
        os.environ.setdefault("LOG_LEVEL", "DEBUG")
    gladys_setup_logging("orchestrator")


def generate_proto() -> int:
    """Generate Python code from proto files."""
    # Find proto dir relative to package
    package_dir = Path(__file__).parent.parent
    proto_dir = package_dir / "proto"
    out_dir = Path(__file__).parent / "generated"

    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)

    # Find proto files
    proto_files = list(proto_dir.glob("*.proto"))
    if not proto_files:
        print(f"No .proto files found in {proto_dir}")
        return 1

    print(f"Generating Python code from {len(proto_files)} proto files...")

    # Run protoc
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        f"--pyi_out={out_dir}",
    ]
    cmd.extend(str(f) for f in proto_files)

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error generating proto: {result.stderr}")
        return result.returncode

    # Create __init__.py in generated directory
    init_file = out_dir / "__init__.py"
    init_file.write_text('"""Generated gRPC code from proto files."""\n')

    print(f"Generated code in {out_dir}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """Start the Orchestrator server."""
    setup_logging(args.verbose)

    # Start with env vars / defaults, then override with explicit CLI args
    config = OrchestratorConfig()
    if args.host != "0.0.0.0":
        config = config.model_copy(update={"host": args.host})
    if args.port is not None:
        config = config.model_copy(update={"port": args.port})
    if args.salience_address:
        config = config.model_copy(update={"salience_memory_address": args.salience_address})
    if args.moment_window != 100:
        config = config.model_copy(update={"moment_window_ms": args.moment_window})
    if args.salience_threshold != 0.7:
        config = config.model_copy(update={"high_salience_threshold": args.salience_threshold})

    print(f"Starting GLADyS Orchestrator on {config.host}:{config.port}")
    print(f"  Salience Service: {config.salience_memory_address}")
    print(f"  Memory Service:   {config.memory_storage_address}")
    print(f"  Executive Service: {config.executive_address}")

    # DEBUG: Check environment variable visibility
    print(f"  [DEBUG] Environment variables:")
    print(f"    SALIENCE_MEMORY_ADDRESS = {os.environ.get('SALIENCE_MEMORY_ADDRESS', 'NOT_SET')}")
    print(f"    MEMORY_STORAGE_ADDRESS  = {os.environ.get('MEMORY_STORAGE_ADDRESS', 'NOT_SET')}")
    print(f"    EXECUTIVE_ADDRESS       = {os.environ.get('EXECUTIVE_ADDRESS', 'NOT_SET')}")

    print(f"  Moment window: {config.moment_window_ms}ms")
    print(f"  High salience threshold: {config.high_salience_threshold}")

    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0

    return 0


def cmd_generate_proto(args: argparse.Namespace) -> int:
    """Generate proto code."""
    return generate_proto()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="GLADyS Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start the Orchestrator server")
    start_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    start_parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 50050)")
    start_parser.add_argument(
        "--salience-address",
        help="Address of Salience+Memory service (e.g., localhost:50051 for Python, localhost:50052 for Rust)",
    )
    start_parser.add_argument(
        "--moment-window",
        type=int,
        default=100,
        help="Moment accumulation window in milliseconds (default: 100)",
    )
    start_parser.add_argument(
        "--salience-threshold",
        type=float,
        default=0.7,
        help="Salience threshold for immediate routing (default: 0.7)",
    )
    start_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    start_parser.set_defaults(func=cmd_start)

    # generate-proto command
    proto_parser = subparsers.add_parser("generate-proto", help="Generate Python from proto files")
    proto_parser.set_defaults(func=cmd_generate_proto)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
