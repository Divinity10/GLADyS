"""Shared configuration and utilities for GLADyS service management.

This module is used by local.py and docker.py to avoid code duplication.
"""

import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent

# Log directory for local services
LOG_DIR = Path.home() / ".gladys" / "logs"


def ensure_log_dir() -> Path:
    """Ensure log directory exists and return path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def get_log_file(service_name: str) -> Path:
    """Get log file path for a service."""
    ensure_log_dir()
    return LOG_DIR / f"{service_name}.log"


def load_env_file(env_path: Path | None = None) -> None:
    """Load environment variables from .env file.

    Simple loader that doesn't require python-dotenv dependency.
    Reads the .env file and sets variables that aren't already set.
    """
    if env_path is None:
        env_path = ROOT / ".env"

    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Don't override existing env vars
                if key and key not in os.environ:
                    os.environ[key] = value


def resolve_ollama_endpoint() -> None:
    """Resolve OLLAMA_URL and OLLAMA_MODEL from named endpoints.

    Supports named endpoints like:
        OLLAMA_ENDPOINT_LOCAL=http://localhost:11434
        OLLAMA_ENDPOINT_LOCAL_MODEL=gemma3:1b
        OLLAMA_ENDPOINT_REMOTE=http://server:11435
        OLLAMA_ENDPOINT_REMOTE_MODEL=gemma3:4b
        OLLAMA_ENDPOINT=local

    The OLLAMA_ENDPOINT value (case-insensitive) selects which
    OLLAMA_ENDPOINT_<name> to use as OLLAMA_URL and which
    OLLAMA_ENDPOINT_<name>_MODEL to use as OLLAMA_MODEL.

    Falls back to OLLAMA_URL/OLLAMA_MODEL if OLLAMA_ENDPOINT is not set.
    """
    endpoint_name = os.environ.get("OLLAMA_ENDPOINT", "").strip().upper()

    if not endpoint_name:
        # No named endpoint configured, use OLLAMA_URL directly (backward compat)
        return

    # Look for OLLAMA_ENDPOINT_<name>
    endpoint_key = f"OLLAMA_ENDPOINT_{endpoint_name}"
    endpoint_url = os.environ.get(endpoint_key)

    if endpoint_url:
        os.environ["OLLAMA_URL"] = endpoint_url

        # Also check for endpoint-specific model
        model_key = f"OLLAMA_ENDPOINT_{endpoint_name}_MODEL"
        model_name = os.environ.get(model_key)
        if model_name:
            os.environ["OLLAMA_MODEL"] = model_name
    else:
        # Named endpoint not found - warn but don't fail
        print(f"Warning: OLLAMA_ENDPOINT={endpoint_name} but {endpoint_key} not defined")


# Load .env file on module import
load_env_file()

# Resolve named Ollama endpoint
resolve_ollama_endpoint()


@dataclass
class PortConfig:
    """Port configuration for an environment."""

    orchestrator: int
    memory_python: int
    memory_rust: int
    executive: int
    db: int
    dashboard: int


# Environment port configurations
LOCAL_PORTS = PortConfig(
    orchestrator=int(os.environ.get("ORCHESTRATOR_PORT", 50050)),
    memory_python=int(os.environ.get("MEMORY_PYTHON_PORT", 50051)),
    memory_rust=int(os.environ.get("MEMORY_RUST_PORT", 50052)),
    executive=int(os.environ.get("EXECUTIVE_PORT", 50053)),
    db=int(os.environ.get("DB_PORT", 5432)),
    dashboard=int(os.environ.get("DASHBOARD_PORT", 8502)),
)

DOCKER_PORTS = PortConfig(
    orchestrator=50060,
    memory_python=50061,
    memory_rust=50062,
    executive=50063,
    db=5433,
    dashboard=8502,
)

# Service descriptions (shared between local and docker)
SERVICE_DESCRIPTIONS = {
    "memory": "Memory Storage + Salience Gateway",
    "memory-python": "Memory Storage (Python)",
    "memory-rust": "Salience Gateway (Rust)",
    "orchestrator": "Event routing and priority queue",
    "executive": "Executive stub (LLM planning)",
    "db": "PostgreSQL + pgvector",
    "dashboard": "Web Dashboard (FastAPI + htmx)",
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
