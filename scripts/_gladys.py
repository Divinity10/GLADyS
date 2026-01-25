"""Shared configuration and utilities for GLADyS service management.

This module is used by local.py and docker.py to avoid code duplication.
"""

import socket
import sys
from dataclasses import dataclass
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent


@dataclass
class PortConfig:
    """Port configuration for an environment."""

    orchestrator: int
    memory_python: int
    memory_rust: int
    executive: int
    db: int


# Environment port configurations
LOCAL_PORTS = PortConfig(
    orchestrator=50050,
    memory_python=50051,
    memory_rust=50052,
    executive=50053,
    db=5432,
)

DOCKER_PORTS = PortConfig(
    orchestrator=50060,
    memory_python=50061,
    memory_rust=50062,
    executive=50063,
    db=5433,
)

# Service descriptions (shared between local and docker)
SERVICE_DESCRIPTIONS = {
    "memory": "Memory Storage + Salience Gateway",
    "memory-python": "Memory Storage (Python)",
    "memory-rust": "Salience Gateway (Rust)",
    "orchestrator": "Event routing and accumulation",
    "executive": "Executive stub (LLM planning)",
    "db": "PostgreSQL + pgvector",
}


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def format_status_line(
    name: str,
    running: bool,
    status: str,
    port: int,
    description: str,
    pid: int | str | None = None,
) -> str:
    """Format a status line for display."""
    status_icon = "[OK]" if running else "[--]"
    pid_str = str(pid) if pid else "-"
    if pid:
        return f"{name:<15} {status_icon:<6} {status:<10} {port:<8} {pid_str:<10} {description}"
    else:
        return f"{name:<18} {status_icon} {status:<15} {port:<8} {description}"


def get_test_env(ports: PortConfig) -> dict[str, str]:
    """Get environment variables for running tests against an environment."""
    return {
        "PYTHON_ADDRESS": f"localhost:{ports.memory_python}",
        "RUST_ADDRESS": f"localhost:{ports.memory_rust}",
        "ORCHESTRATOR_ADDRESS": f"localhost:{ports.orchestrator}",
        "EXECUTIVE_ADDRESS": f"localhost:{ports.executive}",
        "DB_HOST": "localhost",
        "DB_PORT": str(ports.db),
    }
