#!/usr/bin/env python3
"""Manage GLADyS DOCKER services (start/stop/restart/status/test).

This script uses the Service Management framework (_service_base.py).
For local services, use: python scripts/local.py
"""

from _docker_backend import DockerBackend
from _gladys import DOCKER_PORTS, ROOT
from _service_base import ServiceDefinition, ServiceManager

# Define services
SERVICES = {
    "memory-python": ServiceDefinition(
        name="memory-python",
        description="Memory Storage (Python)",
        port=DOCKER_PORTS.memory_python,
        group="memory",
    ),
    "memory-rust": ServiceDefinition(
        name="memory-rust",
        description="Salience Gateway (Rust)",
        port=DOCKER_PORTS.memory_rust,
        group="memory",
    ),
    "orchestrator": ServiceDefinition(
        name="orchestrator",
        description="Event Router",
        port=DOCKER_PORTS.orchestrator,
    ),
    "executive-stub": ServiceDefinition(
        name="executive-stub",
        description="Executive Stub",
        port=DOCKER_PORTS.executive,
        group="executive",
    ),
    "db": ServiceDefinition(
        name="db",
        description="PostgreSQL + pgvector",
        port=DOCKER_PORTS.db,
    ),
}

def main():
    """Entry point for gladys-docker command."""
    backend = DockerBackend(ROOT / "src" / "integration" / "docker-compose.yml")
    manager = ServiceManager(backend, SERVICES)
    manager.run()


if __name__ == "__main__":
    main()