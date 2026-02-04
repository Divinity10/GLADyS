#!/usr/bin/env python3
"""Manage GLADyS LOCAL services (start/stop/restart/status/test).

This script uses the Service Management framework (_service_base.py).
For Docker services, use: python scripts/docker.py
"""

from _local_backend import LocalBackend
from _gladys import LOCAL_PORTS
from _service_base import ServiceDefinition, ServiceManager

# Define services
SERVICES = {
    "memory-python": ServiceDefinition(
        name="memory-python",
        description="Memory Storage (Python)",
        port=LOCAL_PORTS.memory_python,
        group="memory",
    ),
    "memory-rust": ServiceDefinition(
        name="memory-rust",
        description="Salience Gateway (Rust)",
        port=LOCAL_PORTS.memory_rust,
        group="memory",
    ),
    "orchestrator": ServiceDefinition(
        name="orchestrator",
        description="Event Router",
        port=LOCAL_PORTS.orchestrator,
    ),
    "executive-stub": ServiceDefinition(
        name="executive-stub",
        description="Executive Stub",
        port=LOCAL_PORTS.executive,
        group="executive",
    ),
    # Dashboard excluded - started separately via `make dashboard` (uvicorn with --reload)
}

def main():
    """Entry point for gladys-local command."""
    backend = LocalBackend()
    manager = ServiceManager(backend, SERVICES)
    manager.run()


if __name__ == "__main__":
    main()
