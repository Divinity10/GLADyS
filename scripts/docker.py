#!/usr/bin/env python3
"""Manage GLADyS DOCKER services (start/stop/restart/status/test).

This script manages services running in Docker containers.
For local services, use: python scripts/local.py

Usage:
    python scripts/docker.py start memory
    python scripts/docker.py start all
    python scripts/docker.py stop memory
    python scripts/docker.py restart all
    python scripts/docker.py status
    python scripts/docker.py test test_td_learning.py
    python scripts/docker.py logs memory
    python scripts/docker.py psql
    python scripts/docker.py clean heuristics
    python scripts/docker.py clean all
    python scripts/docker.py reset
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from _gladys import (
    ROOT,
    DOCKER_PORTS,
    SERVICE_DESCRIPTIONS,
    is_port_open,
    get_test_env,
)

# Integration directory (where docker-compose.yml lives)
INTEGRATION_DIR = ROOT / "src" / "integration"

# Service groups (maps user-friendly names to docker-compose service names)
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
    "memory-python": DOCKER_PORTS.memory_python,
    "memory-rust": DOCKER_PORTS.memory_rust,
    "orchestrator": DOCKER_PORTS.orchestrator,
    "executive-stub": DOCKER_PORTS.executive,
    "db": DOCKER_PORTS.db,
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

    # Wait for db to be healthy before running migrations
    import time
    for _ in range(30):
        status = get_container_status(CONTAINERS["db"])
        if status.get("healthy"):
            break
        time.sleep(1)

    # Run migrations (idempotent, safe to run every time)
    if not args.no_migrate:
        print("\nRunning migrations...")
        migrate_args = argparse.Namespace()
        result = cmd_migrate(migrate_args)
        if result != 0:
            print("Warning: Some migrations failed. Continuing anyway...")

    print(f"\nStarting DOCKER {args.service}...")
    docker_compose("up", "-d", *services)

    if not args.no_wait:
        print("\nWaiting for services to be healthy...")
        result = docker_compose("ps", capture=True)
        print(result.stdout)

    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop services."""
    services = resolve_services(args.service)
    print(f"Stopping DOCKER {args.service}...")
    docker_compose("stop", *services)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart services."""
    services = resolve_services(args.service)
    print(f"Restarting DOCKER {args.service}...")
    docker_compose("restart", *services)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show service status."""
    print("Service Status (DOCKER)")
    print("=" * 70)
    print(f"{'Service':<18} {'Status':<20} {'Port':<8} Description")
    print("-" * 70)

    for service, container in CONTAINERS.items():
        st = get_container_status(container)
        status_icon = "[OK]" if st["healthy"] else ("[--]" if st["running"] else "[  ]")
        port = PORTS.get(service, "-")
        desc = SERVICE_DESCRIPTIONS.get(service, SERVICE_DESCRIPTIONS.get(service.replace("-stub", ""), ""))
        print(f"{service:<18} {status_icon} {st['status']:<15} {port:<8} {desc}")

    print("=" * 70)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Run tests against DOCKER environment."""
    test_env = get_test_env(DOCKER_PORTS)
    env = {**os.environ, **test_env}

    test_dir = ROOT / "src" / "integration"

    # Build command
    if args.test:
        cmd = ["uv", "run", "python", args.test]
    else:
        cmd = ["uv", "run", "pytest", "-v"]

    print(f"Running tests against DOCKER (ports {DOCKER_PORTS.memory_python}/{DOCKER_PORTS.memory_rust})...")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=test_dir, env=env)
    return result.returncode


def cmd_logs(args: argparse.Namespace) -> int:
    """Follow logs."""
    services = resolve_services(args.service)
    docker_compose("logs", "-f", *services)
    return 0


def cmd_psql(args: argparse.Namespace) -> int:
    """Open database shell or execute command."""
    container = CONTAINERS["db"]
    
    cmd = ["docker", "exec", "-e", "PGPASSWORD=gladys"]
    
    if args.command:
        # Non-interactive command
        cmd.extend([container, "psql", "-U", "gladys", "-d", "gladys", "-c", args.command])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr.strip()}")
            return result.returncode
        print(result.stdout.strip())
        return 0
    else:
        # Interactive shell
        cmd.extend(["-it", container, "psql", "-U", "gladys", "-d", "gladys"])
        subprocess.run(cmd)
        return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Execute a SQL query and print output."""
    # Reuse psql command logic but strictly non-interactive
    psql_args = argparse.Namespace(command=args.sql)
    return cmd_psql(psql_args)


def kill_stuck_connections(container: str) -> None:
    """Kill active connections to the database to release locks."""
    print("Clearing active database connections...")
    # Terminate all backends except our own
    sql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'gladys' AND pid <> pg_backend_pid();"
    subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=gladys", container,
         "psql", "-U", "gladys", "-d", "gladys", "-c", sql],
        capture_output=True,
        text=True
    )


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run database migrations.

    Migrations are safe to run multiple times - "already exists" errors are treated as OK.
    """
    container = CONTAINERS["db"]
    
    # Pre-flight: Kill stuck connections that might block DDL
    kill_stuck_connections(container)
    
    migrations_dir = ROOT / "src" / "memory" / "migrations"

    if not migrations_dir.exists():
        print(f"Migrations directory not found: {migrations_dir}")
        return 1

    # Get all .sql files sorted by name
    all_migrations = sorted(migrations_dir.glob("*.sql"))
    
    if args.file:
        # Run specific file
        migration_files = [m for m in all_migrations if args.file in m.name]
        if not migration_files:
            print(f"No migration matching '{args.file}' found.")
            return 1
    else:
        migration_files = all_migrations

    if not migration_files:
        print("No migration files found.")
        return 0

    print(f"Running {len(migration_files)} migrations...")
    errors = 0

    for migration in migration_files:
        print(f"Applying {migration.name}...")
        
        # Read the migration file
        sql = migration.read_text(encoding="utf-8")

        # Use Popen to stream output in real-time
        # This avoids timeouts and gives immediate feedback
        process = subprocess.Popen(
            ["docker", "exec", "-e", "PGPASSWORD=gladys", container,
             "psql", "-U", "gladys", "-d", "gladys", "-c", sql],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            encoding="utf-8"
        )

        # Stream output
        output_lines = []
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line:
                    output_lines.append(line)
                    # Optional: Print verbose output only if needed
                    # print(f"    {line}")

        return_code = process.wait()

        if return_code == 0:
            print(f"  [OK] Success")
        else:
            # Check if it was just "already exists"
            full_output = "\n".join(output_lines)
            if "already exists" in full_output or "skipping" in full_output:
                print(f"  [OK] Already applied")
            else:
                print(f"  [FAIL] Error details:")
                for line in output_lines:
                    print(f"    {line}")
                errors += 1

    if errors:
        print(f"\n{errors} migration(s) failed.")
        return 1

    print("\nAll migrations completed.")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean database tables."""
    container = CONTAINERS["db"]

    tables = {
        "heuristics": "TRUNCATE heuristics CASCADE;",
        "events": "TRUNCATE episodic_events CASCADE;",
        "all": "TRUNCATE heuristics, episodic_events CASCADE;",
    }

    sql = tables.get(args.table, tables["heuristics"])

    result = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=gladys", container,
         "psql", "-U", "gladys", "-d", "gladys", "-c", sql],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        print(f"Cleaned: {args.table}")
        print(result.stdout.strip())
    else:
        print(f"Error: {result.stderr}")
    return result.returncode


def cmd_reset(args: argparse.Namespace) -> int:
    """Full reset: clean all data and restart services."""
    print("Resetting GLADyS (DOCKER)...")

    # Stop app services
    print("\n1. Stopping services...")
    docker_compose("stop", *APP_SERVICES)

    # Clean database
    print("\n2. Cleaning database...")
    container = CONTAINERS["db"]
    result = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=gladys", container,
         "psql", "-U", "gladys", "-d", "gladys",
         "-c", "TRUNCATE heuristics, episodic_events CASCADE;"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        print("  Database cleaned.")
    else:
        print(f"  Warning: {result.stderr}")

    # Restart services
    if not args.no_start:
        print("\n3. Starting services...")
        docker_compose("up", "-d", *APP_SERVICES)

    print("\nReset complete.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage GLADyS DOCKER services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/docker.py start memory          # Start memory services (runs migrations)
    python scripts/docker.py start all             # Start all services (runs migrations)
    python scripts/docker.py stop memory           # Stop memory services
    python scripts/docker.py restart all           # Restart all services
    python scripts/docker.py status                # Show status of all services
    python scripts/docker.py migrate               # Run database migrations
    python scripts/docker.py test test_td_learning.py  # Run specific test
    python scripts/docker.py test                  # Run all tests
    python scripts/docker.py logs memory           # Follow memory logs
    python scripts/docker.py psql                  # Open database shell
    python scripts/docker.py clean heuristics      # Clear heuristics table
    python scripts/docker.py clean all             # Clear all data
    python scripts/docker.py reset                 # Full reset (clean + restart)
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
    start_parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="Skip running database migrations",
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

    # test
    test_parser = subparsers.add_parser("test", help="Run tests against DOCKER environment")
    test_parser.add_argument(
        "test",
        nargs="?",
        help="Specific test file to run (default: all tests)",
    )
    test_parser.set_defaults(func=cmd_test)

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
    psql_parser.add_argument(
        "-c", "--command",
        help="Run single SQL command and exit",
    )
    psql_parser.set_defaults(func=cmd_psql)

    # query
    query_parser = subparsers.add_parser("query", help="Run SQL query")
    query_parser.add_argument(
        "sql",
        help="SQL query to execute",
    )
    query_parser.set_defaults(func=cmd_query)

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument(
        "-f", "--file",
        help="Run only specific migration file (substring match)",
    )
    migrate_parser.set_defaults(func=cmd_migrate)

    # clean
    clean_parser = subparsers.add_parser("clean", help="Clean database tables")
    clean_parser.add_argument(
        "table",
        choices=["heuristics", "events", "all"],
        nargs="?",
        default="heuristics",
        help="Table(s) to clean (default: heuristics)",
    )
    clean_parser.set_defaults(func=cmd_clean)

    # reset
    reset_parser = subparsers.add_parser("reset", help="Full reset: clean data and restart")
    reset_parser.add_argument(
        "--no-start",
        action="store_true",
        help="Don't restart services after reset",
    )
    reset_parser.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
