#!/usr/bin/env python3
"""Verify GLADyS development environment is working.

Usage:
    python scripts/verify_env.py              # Check status and exit
    python scripts/verify_env.py --wait       # Wait for services to become healthy (default 120s)
    python scripts/verify_env.py --wait 180   # Wait up to 180 seconds
    python scripts/verify_env.py --quick      # Skip gRPC checks (fast)

This script checks:
1. Docker daemon is running
2. All required containers are running
3. Container health status
4. gRPC services are responding

IMPORTANT: After 'make up', containers take 30-60 seconds to become healthy.
Use --wait to automatically wait for them.

Run this BEFORE attempting any development work to catch environment issues early.
"""

import argparse
import subprocess
import sys
import time

# ANSI colors for output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Required containers (from docker-compose.yml)
REQUIRED_CONTAINERS = [
    "gladys-integration-db",
    "gladys-integration-memory-python",
    "gladys-integration-memory-rust",
    "gladys-integration-orchestrator",
    "gladys-integration-executive-stub",
]

# gRPC service ports to check
GRPC_SERVICES = {
    "orchestrator": ("localhost", 50050),
    "memory-python": ("localhost", 50051),
    "memory-rust": ("localhost", 50052),
    "executive": ("localhost", 50053),
}

# Typical startup times
STARTUP_TIMES = """
Typical container startup times:
  - postgres: 5-10s
  - memory-python: 20-40s (loads embedding model)
  - memory-rust: 5-10s
  - orchestrator: 10-15s
  - executive: 10-15s

Total time to healthy: ~60s after 'make up'
"""


def run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except FileNotFoundError:
        return -2, "", f"Command not found: {cmd[0]}"


def check_docker_daemon() -> bool:
    """Check if Docker daemon is running."""
    code, stdout, stderr = run_cmd(["docker", "info"])
    return code == 0


def get_container_status() -> dict[str, str]:
    """Get status of all containers. Returns {name: status}."""
    code, stdout, stderr = run_cmd([
        "docker", "ps", "-a",
        "--format", "{{.Names}}\t{{.Status}}"
    ])
    if code != 0:
        return {}

    result = {}
    for line in stdout.strip().split("\n"):
        if not line or "\t" not in line:
            continue
        name, status = line.split("\t", 1)
        result[name] = status
    return result


def is_container_healthy(status: str) -> bool:
    """Check if container status indicates healthy."""
    status_lower = status.lower()
    # Container is healthy if:
    # - Status contains "healthy" OR
    # - Status is "Up" without any health issues
    if "unhealthy" in status_lower:
        return False
    if "starting" in status_lower:
        return False
    if "health:" in status_lower and "healthy" not in status_lower:
        return False
    return "up" in status_lower


def print_status(verbose: bool = True) -> tuple[bool, list[str], list[str]]:
    """Print and return current status. Returns (all_ok, missing, unhealthy)."""
    statuses = get_container_status()
    missing = []
    unhealthy = []

    for container in REQUIRED_CONTAINERS:
        status = statuses.get(container, "")
        if not status:
            missing.append(container)
            if verbose:
                print(f"  {RED}MISSING{RESET}: {container}")
        elif not is_container_healthy(status):
            unhealthy.append(container)
            if verbose:
                print(f"  {YELLOW}NOT READY{RESET}: {container} ({status})")
        else:
            if verbose:
                print(f"  {GREEN}OK{RESET}: {container}")

    return (not missing and not unhealthy), missing, unhealthy


def check_grpc_service(host: str, port: int, timeout: float = 3) -> bool:
    """Check if a gRPC service is responding."""
    try:
        import grpc
        channel = grpc.insecure_channel(f"{host}:{port}")
        try:
            grpc.channel_ready_future(channel).result(timeout=timeout)
            return True
        except grpc.FutureTimeoutError:
            return False
        finally:
            channel.close()
    except ImportError:
        return True  # Skip if grpc not installed
    except Exception:
        return False


def wait_for_healthy(timeout_seconds: int = 120) -> bool:
    """Wait for all containers to become healthy."""
    print(f"\n{BLUE}Waiting for containers (timeout: {timeout_seconds}s)...{RESET}")
    print(STARTUP_TIMES)

    start = time.time()
    last_print = 0
    check_interval = 5

    while time.time() - start < timeout_seconds:
        elapsed = int(time.time() - start)

        # Print status every 10 seconds
        if elapsed - last_print >= 10 or elapsed == 0:
            print(f"\n{BLUE}[{elapsed}s] Checking status...{RESET}")
            all_ok, missing, unhealthy = print_status(verbose=True)
            last_print = elapsed

            if all_ok:
                return True
        else:
            all_ok, missing, unhealthy = print_status(verbose=False)
            if all_ok:
                print(f"\n{BLUE}[{elapsed}s] All containers healthy!{RESET}")
                print_status(verbose=True)
                return True

        time.sleep(check_interval)

    print(f"\n{RED}Timeout after {timeout_seconds}s{RESET}")
    print(f"\n{BLUE}Final status:{RESET}")
    print_status(verbose=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify GLADyS development environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=STARTUP_TIMES,
    )
    parser.add_argument(
        "--wait",
        nargs="?",
        const=120,
        type=int,
        metavar="SECONDS",
        help="Wait for containers to become healthy (default: 120s)",
    )
    parser.add_argument("--quick", action="store_true", help="Skip gRPC checks")
    args = parser.parse_args()

    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BLUE}GLADyS Environment Verification{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}\n")

    # Step 1: Docker daemon
    print(f"{BLUE}Checking Docker daemon...{RESET}")
    if not check_docker_daemon():
        print(f"  {RED}FAIL{RESET}: Docker daemon is not running")
        print(f"\n{RED}FATAL: Start Docker Desktop and try again.{RESET}")
        return 1
    print(f"  {GREEN}OK{RESET}: Docker daemon is running")

    # Step 2: Check/wait for containers
    print(f"\n{BLUE}Checking containers...{RESET}")
    all_ok, missing, unhealthy = print_status(verbose=True)

    if not all_ok:
        if args.wait:
            # Start/restart containers (handles both missing and stopped)
            print(f"\n{BLUE}Starting containers...{RESET}")
            subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd="src/integration",
                capture_output=True,
            )
            time.sleep(2)

            # Wait for healthy
            if not wait_for_healthy(args.wait):
                return 1
            all_ok = True
        else:
            print(f"\n  {YELLOW}Containers not running. To start and wait:{RESET}")
            print(f"  {YELLOW}  python scripts/verify_env.py --wait{RESET}")
            print(f"  {YELLOW}Or manually: make up && sleep 60{RESET}")
            return 1

    # Step 3: gRPC services (only if containers are healthy and not --quick)
    if not args.quick:
        print(f"\n{BLUE}Checking gRPC services...{RESET}")
        try:
            import grpc
            grpc_ok = True
            for name, (host, port) in GRPC_SERVICES.items():
                if check_grpc_service(host, port):
                    print(f"  {GREEN}OK{RESET}: {name} ({host}:{port})")
                else:
                    print(f"  {RED}FAIL{RESET}: {name} ({host}:{port})")
                    grpc_ok = False

            if not grpc_ok:
                print(f"\n  {YELLOW}Check container logs: docker compose -f src/integration/docker-compose.yml logs{RESET}")
                return 1
        except ImportError:
            print(f"  {YELLOW}SKIP{RESET}: grpc module not installed")

    # Summary
    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{GREEN}Environment OK - ready for development{RESET}")
    print(f"\n{BLUE}Quick reference:{RESET}")
    print(f"  make benchmark    - Run performance benchmark")
    print(f"  make test         - Run tests")
    print(f"  make down         - Stop services")
    return 0


if __name__ == "__main__":
    sys.exit(main())
