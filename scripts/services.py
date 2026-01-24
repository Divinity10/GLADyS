#!/usr/bin/env python3
"""Manage GLADyS services (start/stop/restart/status).

Usage:
    python scripts/services.py start memory
    python scripts/services.py start all
    python scripts/services.py stop memory
    python scripts/services.py restart all
    python scripts/services.py status
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent

# Service definitions
SERVICES = {
    "memory": {
        "port": 50051,
        "cwd": ROOT / "src" / "memory" / "python",
        "cmd": ["uv", "run", "python", "-m", "gladys_memory.grpc_server"],
        "description": "Memory Storage + Salience Gateway",
    },
    "orchestrator": {
        "port": 50052,
        "cwd": ROOT / "src" / "orchestrator",
        "cmd": ["uv", "run", "python", "run.py", "start"],
        "description": "Event routing and accumulation",
    },
    "executive": {
        "port": 50053,
        "cwd": ROOT / "src" / "executive",
        "cmd": ["uv", "run", "python", "stub_server.py"],
        "description": "Executive stub (LLM planning)",
    },
}


def is_windows():
    return sys.platform == "win32"


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


def is_port_open(port: int) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


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
    if is_port_open(port):
        print(f"  {name}: Already running on port {port}")
        return True

    print(f"  Starting {name} ({svc['description']})...")

    # Start the process
    try:
        if is_windows():
            # Windows: use CREATE_NEW_PROCESS_GROUP to detach
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc["cwd"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
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
                if is_port_open(port):
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
            if not is_port_open(port):
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
    running = is_port_open(port)

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

    print("Starting services...")
    success = True
    for name in services:
        if not start_service(name, wait=not args.no_wait):
            success = False
    return 0 if success else 1


def cmd_stop(args):
    """Handle stop command."""
    services = list(SERVICES.keys()) if args.service == "all" else [args.service]

    print("Stopping services...")
    success = True
    for name in services:
        if not stop_service(name):
            success = False
    return 0 if success else 1


def cmd_restart(args):
    """Handle restart command."""
    services = list(SERVICES.keys()) if args.service == "all" else [args.service]

    print("Restarting services...")
    success = True
    for name in services:
        if not restart_service(name):
            success = False
    return 0 if success else 1


def cmd_status(args):
    """Handle status command."""
    print("Service Status")
    print("=" * 60)
    print(f"{'Service':<15} {'Status':<10} {'Port':<8} {'PID':<10} Description")
    print("-" * 60)

    for name in SERVICES:
        st = status_service(name)
        status_icon = "[OK]" if st["running"] else "[--]"
        pid_str = str(st["pid"]) if st["pid"] else "-"
        print(f"{name:<15} {status_icon:<6} {st['status']:<10} {st['port']:<8} {pid_str:<10} {st['description']}")

    print("=" * 60)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage GLADyS services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/services.py start memory     # Start memory service
    python scripts/services.py start all        # Start all services
    python scripts/services.py stop memory      # Stop memory service
    python scripts/services.py restart all      # Restart all services
    python scripts/services.py status           # Show status of all services
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

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
