#!/usr/bin/env python3
"""
GLADyS Orchestrator - Entry point.

Usage:
    python run.py start [--host HOST] [--port PORT] [--moment-window MS]
    python run.py generate-proto

Commands:
    start           Start the Orchestrator gRPC server
    generate-proto  Generate Python code from proto files
"""

import argparse
import asyncio
import logging
import subprocess
import sys
from pathlib import Path

# Add package to path for development
sys.path.insert(0, str(Path(__file__).parent))

from gladys_orchestrator.config import OrchestratorConfig
from gladys_orchestrator.server import serve


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def generate_proto() -> int:
    """Generate Python code from proto files."""
    proto_dir = Path(__file__).parent / "proto"
    out_dir = Path(__file__).parent / "gladys_orchestrator" / "generated"

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

    config = OrchestratorConfig(
        host=args.host,
        port=args.port,
        moment_window_ms=args.moment_window,
        high_salience_threshold=args.salience_threshold,
    )

    print(f"Starting GLADyS Orchestrator on {config.host}:{config.port}")
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
    start_parser.add_argument("--port", type=int, default=50051, help="Port to listen on")
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
