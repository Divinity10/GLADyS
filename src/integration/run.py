#!/usr/bin/env python3
"""Manage GLADyS services in Docker (start/stop/restart/status).

This is the Docker equivalent of scripts/services.py.
Use this when running services in Docker containers.
Use scripts/services.py when running services locally.

Usage:
    python run.py start memory        # Start memory services (Python + Rust)
    python run.py start all           # Start all services
    python run.py stop memory         # Stop memory services
    python run.py restart all         # Restart all services
    python run.py status              # Show status of all services
    python run.py logs memory         # Follow memory service logs
    python run.py psql                # Open database shell
    python run.py clean-test          # Delete test data from database
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Integration directory (where docker-compose.yml lives)
INTEGRATION_DIR = Path(__file__).parent

# Service groups (matching scripts/services.py naming)
# Maps user-friendly names to docker-compose service names
SERVICE_GROUPS = {
    "memory": ["memory-python", "memory-rust"],
    "orchestrator": ["orchestrator"],
    "executive": ["executive-stub"],
}

# All app services (excludes db which is infrastructure)
APP_SERVICES = ["memory-python", "memory-rust", "orchestrator", "executive-stub"]

# Container names for direct docker commands
CONTAINERS = {
    "memory-python": "gladys-integration-memory-python",
    "memory-rust": "gladys-integration-memory-rust",
    "orchestrator": "gladys-integration-orchestrator",
    "executive-stub": "gladys-integration-executive-stub",
    "db": "gladys-integration-db",
}

# Ports for status display
PORTS = {
    "memory-python": 50051,
    "memory-rust": 50052,
    "orchestrator": 50050,
    "executive-stub": 50053,
    "db": 5433,
}

DESCRIPTIONS = {
    "memory-python": "Memory Storage (Python)",
    "memory-rust": "Salience Gateway (Rust)",
    "orchestrator": "Event routing",
    "executive-stub": "Executive stub",
    "db": "PostgreSQL + pgvector",
}


def docker_compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run docker-compose command."""
    cmd = ["docker-compose", "-f", str(INTEGRATION_DIR / "docker-compose.yml")] + list(args)
    return subprocess.run(cmd, capture_output=capture, text=True)


def get_container_status(container_name: str) -> dict:
    """Get status of a container."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}|{{.State.Health.Status}}", container_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"running": False, "status": "not found", "healthy": False}

    parts = result.stdout.strip().split("|")
    status = parts[0] if parts else "unknown"
    health = parts[1] if len(parts) > 1 else ""

    return {
        "running": status == "running",
        "status": f"{status}" + (f" ({health})" if health else ""),
        "healthy": health == "healthy",
    }


def resolve_services(name: str) -> list[str]:
    """Resolve service name to docker-compose service names."""
    if name == "all":
        return APP_SERVICES
    elif name in SERVICE_GROUPS:
        return SERVICE_GROUPS[name]
    else:
        print(f"Unknown service: {name}")
        print(f"Valid services: {', '.join(SERVICE_GROUPS.keys())} or 'all'")
        sys.exit(1)


def cmd_start(args: argparse.Namespace) -> int:
    """Start services."""
    services = resolve_services(args.service)

    # Ensure db is running first
    print("Ensuring database is running...")
    docker_compose("up", "-d", "postgres")

    print(f"Starting {args.service}...")
    docker_compose("up", "-d", *services)

    if not args.no_wait:
        print("\nWaiting for services to be healthy...")
        # Wait for health checks
        result = docker_compose("ps", capture=True)
        print(result.stdout)

    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop services."""
    services = resolve_services(args.service)
    print(f"Stopping {args.service}...")
    docker_compose("stop", *services)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart services."""
    services = resolve_services(args.service)
    print(f"Restarting {args.service}...")
    docker_compose("restart", *services)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show service status."""
    print("Service Status (Docker)")
    print("=" * 70)
    print(f"{'Service':<18} {'Status':<20} {'Port':<8} Description")
    print("-" * 70)

    for service, container in CONTAINERS.items():
        st = get_container_status(container)
        status_icon = "[OK]" if st["healthy"] else ("[--]" if st["running"] else "[  ]")
        port = PORTS.get(service, "-")
        desc = DESCRIPTIONS.get(service, "")
        print(f"{service:<18} {status_icon} {st['status']:<15} {port:<8} {desc}")

    print("=" * 70)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Follow logs."""
    services = resolve_services(args.service)
    docker_compose("logs", "-f", *services)
    return 0


def cmd_psql(args: argparse.Namespace) -> int:
    """Open database shell."""
    container = CONTAINERS["db"]
    subprocess.run(["docker", "exec", "-it", container, "psql", "-U", "gladys", "-d", "gladys"])
    return 0


def cmd_clean_test(args: argparse.Namespace) -> int:
    """Delete test data from database."""
    container = CONTAINERS["db"]
    result = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "gladys", "-d", "gladys",
         "-c", "DELETE FROM heuristics WHERE name LIKE 'Test:%';"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Test data cleaned.")
        print(result.stdout.strip())
    else:
        print(f"Error: {result.stderr}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage GLADyS services in Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py start memory        # Start memory services
    python run.py start all           # Start all services
    python run.py stop memory         # Stop memory services
    python run.py restart all         # Restart all services
    python run.py status              # Show status of all services
    python run.py logs memory         # Follow memory logs
    python run.py psql                # Open database shell
    python run.py clean-test          # Delete test data
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    start_parser = subparsers.add_parser("start", help="Start service(s)")
    start_parser.add_argument(
        "service",
        choices=list(SERVICE_GROUPS.keys()) + ["all"],
        help="Service to start (or 'all')",
    )
    start_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for service to be healthy",
    )
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop service(s)")
    stop_parser.add_argument(
        "service",
        choices=list(SERVICE_GROUPS.keys()) + ["all"],
        help="Service to stop (or 'all')",
    )
    stop_parser.set_defaults(func=cmd_stop)

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart service(s)")
    restart_parser.add_argument(
        "service",
        choices=list(SERVICE_GROUPS.keys()) + ["all"],
        help="Service to restart (or 'all')",
    )
    restart_parser.set_defaults(func=cmd_restart)

    # status
    status_parser = subparsers.add_parser("status", help="Show status of all services")
    status_parser.set_defaults(func=cmd_status)

    # logs
    logs_parser = subparsers.add_parser("logs", help="Follow service logs")
    logs_parser.add_argument(
        "service",
        choices=list(SERVICE_GROUPS.keys()) + ["all"],
        help="Service logs to follow",
    )
    logs_parser.set_defaults(func=cmd_logs)

    # psql
    psql_parser = subparsers.add_parser("psql", help="Open database shell")
    psql_parser.set_defaults(func=cmd_psql)

    # clean-test
    clean_parser = subparsers.add_parser("clean-test", help="Delete test data from database")
    clean_parser.set_defaults(func=cmd_clean_test)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
