#!/usr/bin/env python3
"""Verify local development environment (no Docker).

Usage:
    python scripts/verify_local.py

Checks:
1. PostgreSQL is accessible on localhost:5432
2. pgvector extension is installed
3. gladys database exists with required tables
4. (Optional) gRPC services if running
"""

import subprocess
import sys

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Expected tables from migration
REQUIRED_TABLES = [
    "episodic_events",
    "entities",
    "user_profile",
    "heuristics",
    "feedback_events",
]


def run_psql(query: str) -> tuple[bool, str]:
    """Run a psql query and return (success, output)."""
    cmd = [
        "psql",
        "-U", "gladys",
        "-h", "localhost",
        "-d", "gladys",
        "-t",  # tuples only
        "-c", query,
    ]
    env = {"PGPASSWORD": "gladys_dev"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            env={**dict(__import__("os").environ), **env},
        )
        return result.returncode == 0, result.stdout.strip()
    except FileNotFoundError:
        return False, "psql not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "Connection timeout"


def check_postgres() -> bool:
    """Check PostgreSQL is accessible."""
    print(f"{BLUE}Checking PostgreSQL...{RESET}")
    ok, output = run_psql("SELECT version();")
    if ok:
        # Extract just the version part
        version = output.split(",")[0] if output else "unknown"
        print(f"  {GREEN}OK{RESET}: {version}")
        return True
    else:
        print(f"  {RED}FAIL{RESET}: Cannot connect to PostgreSQL")
        print(f"  {YELLOW}Ensure PostgreSQL is running on localhost:5432{RESET}")
        print(f"  {YELLOW}Check: .env file has correct credentials{RESET}")
        return False


def check_pgvector() -> bool:
    """Check pgvector extension is installed."""
    print(f"{BLUE}Checking pgvector...{RESET}")
    ok, output = run_psql("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    if ok and output:
        print(f"  {GREEN}OK{RESET}: pgvector v{output}")
        return True
    else:
        print(f"  {RED}FAIL{RESET}: pgvector extension not installed")
        print(f"  {YELLOW}See memory.md for installation instructions{RESET}")
        return False


def check_tables() -> bool:
    """Check required tables exist."""
    print(f"{BLUE}Checking database tables...{RESET}")
    ok, output = run_psql(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
    )
    if not ok:
        print(f"  {RED}FAIL{RESET}: Cannot query tables")
        return False

    existing = set(line.strip() for line in output.split("\n") if line.strip())
    missing = [t for t in REQUIRED_TABLES if t not in existing]

    if missing:
        print(f"  {RED}FAIL{RESET}: Missing tables: {', '.join(missing)}")
        print(f"  {YELLOW}Run migration: psql -U gladys -d gladys -f src/memory/migrations/001_initial_schema.sql{RESET}")
        return False

    print(f"  {GREEN}OK{RESET}: All {len(REQUIRED_TABLES)} tables exist")
    return True


def check_grpc_services() -> None:
    """Check if gRPC services are running (informational only)."""
    print(f"{BLUE}Checking gRPC services (optional)...{RESET}")

    services = {
        "Memory": 50051,
        "Orchestrator": 50050,
        "Executive": 50053,
    }

    try:
        import grpc
    except ImportError:
        print(f"  {YELLOW}SKIP{RESET}: grpc module not available")
        return

    for name, port in services.items():
        try:
            channel = grpc.insecure_channel(f"localhost:{port}")
            grpc.channel_ready_future(channel).result(timeout=1)
            print(f"  {GREEN}OK{RESET}: {name} (port {port})")
            channel.close()
        except Exception:
            print(f"  {YELLOW}NOT RUNNING{RESET}: {name} (port {port})")


def main() -> int:
    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BLUE}GLADyS Local Environment Check{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}\n")

    # Required checks
    if not check_postgres():
        return 1

    if not check_pgvector():
        return 1

    if not check_tables():
        return 1

    # Informational check
    print()
    check_grpc_services()

    # Summary
    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{GREEN}Local environment OK{RESET}")
    print(f"\n{BLUE}To start services:{RESET}")
    print("  Terminal 1: cd src/memory/python && uv run python -m gladys_memory.grpc_server")
    print("  Terminal 2: cd src/orchestrator && uv run python run.py start")
    print("  Terminal 3: cd src/executive && uv run python stub_server.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
