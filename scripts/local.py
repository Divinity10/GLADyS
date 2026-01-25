#!/usr/bin/env python3
"""Manage GLADyS LOCAL services (start/stop/restart/status/test).

This script manages services running directly on your machine (not Docker).
For Docker services, use: python scripts/docker.py

Usage:
    python scripts/local.py start memory
    python scripts/local.py start all
    python scripts/local.py stop memory
    python scripts/local.py restart all
    python scripts/local.py status
    python scripts/local.py test test_td_learning.py
    python scripts/local.py psql
    python scripts/local.py clean heuristics
    python scripts/local.py clean all
    python scripts/local.py reset
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from _gladys import (
    ROOT,
    LOCAL_PORTS,
    SERVICE_DESCRIPTIONS,
    is_windows,
    is_port_open,
    get_test_env,
)

# Service definitions for local environment
# Note: Local dev uses Python memory only (no separate Rust service)
SERVICES = {
    "memory": {
        "port": LOCAL_PORTS.memory_python,
        "cwd": ROOT / "src" / "memory" / "python",
        "cmd": ["uv", "run", "python", "-m", "gladys_memory.grpc_server"],
        "description": SERVICE_DESCRIPTIONS["memory"],
    },
    "orchestrator": {
        "port": LOCAL_PORTS.orchestrator,
        "cwd": ROOT / "src" / "orchestrator",
        "cmd": ["uv", "run", "python", "run.py", "start"],
        "description": SERVICE_DESCRIPTIONS["orchestrator"],
    },
    "executive": {
        "port": LOCAL_PORTS.executive,
        "cwd": ROOT / "src" / "executive",
        "cmd": ["uv", "run", "python", "stub_server.py"],
        "description": SERVICE_DESCRIPTIONS["executive"],
    },
}


def find_pid_by_port(port: int) -> int | None:
    """Find the PID of a process listening on a port."""
    try:
        if is_windows():
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        else:
            result = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None


def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        if is_windows():
            subprocess.run(
                ["powershell", "-Command", f"Stop-Process -Id {pid} -Force"],
                capture_output=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True
    except Exception as e:
        print(f"  Error killing PID {pid}: {e}")
        return False


def start_service(name: str, wait: bool = True) -> bool:
    """Start a service."""
    if name not in SERVICES:
        print(f"Unknown service: {name}")
        return False

    svc = SERVICES[name]
    port = svc["port"]

    # Check if already running
    if is_port_open("localhost", port):
        print(f"  {name}: Already running on port {port}")
        return True

    print(f"  Starting {name} ({svc['description']})...")

    # Start the process
    try:
        if is_windows():
            # Windows: use CREATE_NO_WINDOW to prevent console popup
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc["cwd"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            )
        else:
            # Unix: use nohup-style detach
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc["cwd"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        # Wait for service to be ready
        if wait:
            for _ in range(30):  # 30 second timeout
                if is_port_open("localhost", port):
                    print(f"  {name}: Started (port {port}, PID {proc.pid})")
                    return True
                time.sleep(1)
            print(f"  {name}: Started but not responding on port {port}")
            return False
        else:
            print(f"  {name}: Started (PID {proc.pid})")
            return True

    except Exception as e:
        print(f"  {name}: Failed to start - {e}")
        return False


def stop_service(name: str) -> bool:
    """Stop a service."""
    if name not in SERVICES:
        print(f"Unknown service: {name}")
        return False

    svc = SERVICES[name]
    port = svc["port"]

    pid = find_pid_by_port(port)
    if not pid:
        print(f"  {name}: Not running")
        return True

    print(f"  Stopping {name} (PID {pid})...")
    if kill_process(pid):
        # Wait for port to be free
        for _ in range(10):
            if not is_port_open("localhost", port):
                print(f"  {name}: Stopped")
                return True
            time.sleep(0.5)
        print(f"  {name}: Killed but port {port} still in use")
        return False
    return False


def restart_service(name: str) -> bool:
    """Restart a service."""
    stop_service(name)
    time.sleep(1)
    return start_service(name)


def status_service(name: str) -> dict:
    """Get status of a service."""
    if name not in SERVICES:
        return {"name": name, "status": "unknown"}

    svc = SERVICES[name]
    port = svc["port"]
    pid = find_pid_by_port(port)
    running = is_port_open("localhost", port)

    return {
        "name": name,
        "description": svc["description"],
        "port": port,
        "pid": pid,
        "running": running,
        "status": "running" if running else "stopped",
    }


def cmd_start(args):
    """Handle start command."""
    services = list(SERVICES.keys()) if args.service == "all" else [args.service]

    print("Starting LOCAL services...")
    success = True
    for name in services:
        if not start_service(name, wait=not args.no_wait):
            success = False
    return 0 if success else 1


def cmd_stop(args):
    """Handle stop command."""
    services = list(SERVICES.keys()) if args.service == "all" else [args.service]

    print("Stopping LOCAL services...")
    success = True
    for name in services:
        if not stop_service(name):
            success = False
    return 0 if success else 1


def cmd_restart(args):
    """Handle restart command."""
    services = list(SERVICES.keys()) if args.service == "all" else [args.service]

    print("Restarting LOCAL services...")
    success = True
    for name in services:
        if not restart_service(name):
            success = False
    return 0 if success else 1


def cmd_status(args):
    """Handle status command."""
    print("Service Status (LOCAL)")
    print("=" * 70)
    print(f"{'Service':<15} {'Status':<10} {'Port':<8} {'PID':<10} Description")
    print("-" * 70)

    for name in SERVICES:
        st = status_service(name)
        status_icon = "[OK]" if st["running"] else "[--]"
        pid_str = str(st["pid"]) if st["pid"] else "-"
        print(f"{name:<15} {status_icon:<6} {st['status']:<10} {st['port']:<8} {pid_str:<10} {st['description']}")

    print("=" * 70)
    return 0


def cmd_test(args):
    """Run tests against LOCAL environment."""
    test_env = get_test_env(LOCAL_PORTS)
    env = {**os.environ, **test_env}

    test_dir = ROOT / "src" / "integration"

    # Build command
    if args.test:
        cmd = ["uv", "run", "python", args.test]
    else:
        cmd = ["uv", "run", "pytest", "-v"]

    print(f"Running tests against LOCAL (ports {LOCAL_PORTS.memory_python}/{LOCAL_PORTS.memory_rust})...")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=test_dir, env=env)
    return result.returncode


def cmd_psql(args):
    """Open database shell."""
    subprocess.run(["psql", "-h", "localhost", "-p", str(LOCAL_PORTS.db), "-U", "gladys", "-d", "gladys"])
    return 0


def cmd_clean(args):
    """Clean database tables."""
    import psycopg2

    tables = {
        "heuristics": "TRUNCATE heuristics CASCADE;",
        "events": "TRUNCATE episodic_events CASCADE;",
        "all": "TRUNCATE heuristics, episodic_events CASCADE;",
    }

    if args.table not in tables:
        print(f"Unknown table: {args.table}")
        return 1

    try:
        conn = psycopg2.connect(
            host="localhost",
            port=LOCAL_PORTS.db,
            database="gladys",
            user="gladys",
        )
        cur = conn.cursor()
        cur.execute(tables[args.table])
        conn.commit()
        cur.close()
        conn.close()
        print(f"Cleaned: {args.table}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_reset(args):
    """Full reset: clean all data and restart services."""
    print("Resetting GLADyS (LOCAL)...")

    # Stop all services
    print("\n1. Stopping services...")
    for name in SERVICES:
        stop_service(name)

    # Clean database
    print("\n2. Cleaning database...")
    import psycopg2
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=LOCAL_PORTS.db,
            database="gladys",
            user="gladys",
        )
        cur = conn.cursor()
        cur.execute("TRUNCATE heuristics, episodic_events CASCADE;")
        conn.commit()
        cur.close()
        conn.close()
        print("  Database cleaned.")
    except Exception as e:
        print(f"  Warning: Could not clean database - {e}")

    # Restart services
    if not args.no_start:
        print("\n3. Starting services...")
        time.sleep(1)
        for name in SERVICES:
            start_service(name)

    print("\nReset complete.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage GLADyS LOCAL services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/local.py start memory          # Start memory service
    python scripts/local.py start all             # Start all services
    python scripts/local.py stop memory           # Stop memory service
    python scripts/local.py restart all           # Restart all services
    python scripts/local.py status                # Show status of all services
    python scripts/local.py test test_td_learning.py  # Run specific test
    python scripts/local.py test                  # Run all tests
    python scripts/local.py psql                  # Open database shell
    python scripts/local.py clean heuristics      # Clear heuristics table
    python scripts/local.py clean all             # Clear all data
    python scripts/local.py reset                 # Full reset (clean + restart)
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    start_parser = subparsers.add_parser("start", help="Start service(s)")
    start_parser.add_argument(
        "service",
        choices=list(SERVICES.keys()) + ["all"],
        help="Service to start (or 'all')",
    )
    start_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for service to be ready",
    )
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop service(s)")
    stop_parser.add_argument(
        "service",
        choices=list(SERVICES.keys()) + ["all"],
        help="Service to stop (or 'all')",
    )
    stop_parser.set_defaults(func=cmd_stop)

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart service(s)")
    restart_parser.add_argument(
        "service",
        choices=list(SERVICES.keys()) + ["all"],
        help="Service to restart (or 'all')",
    )
    restart_parser.set_defaults(func=cmd_restart)

    # status
    status_parser = subparsers.add_parser("status", help="Show status of all services")
    status_parser.set_defaults(func=cmd_status)

    # test
    test_parser = subparsers.add_parser("test", help="Run tests against LOCAL environment")
    test_parser.add_argument(
        "test",
        nargs="?",
        help="Specific test file to run (default: all tests)",
    )
    test_parser.set_defaults(func=cmd_test)

    # psql
    psql_parser = subparsers.add_parser("psql", help="Open database shell")
    psql_parser.set_defaults(func=cmd_psql)

    # clean
    clean_parser = subparsers.add_parser("clean", help="Clean database tables")
    clean_parser.add_argument(
        "table",
        choices=["heuristics", "events", "all"],
        help="Table(s) to clean",
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
