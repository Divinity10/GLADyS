# Service Management Scripts - Design Document

**Created**: 2026-01-26
**Status**: Draft - Awaiting Review
**Owner**: TBD (Claude/Gemini/Both)

---

## 1. Problem Statement

The `scripts/docker.py` and `scripts/local.py` files are admin tools that manage GLADyS services. As the system grows, these scripts will need more functionality. The current implementation has:

- Duplicated logic between scripts
- Inconsistent interfaces
- No shared abstraction for common operations
- Maintenance burden when adding features

---

## 2. Requirements

### Functional Requirements

| Command | Description | Docker | Local |
|---------|-------------|--------|-------|
| `start <service>` | Start one or more services | ✅ | ✅ |
| `stop <service>` | Stop one or more services | ✅ | ✅ |
| `restart <service>` | Restart one or more services | ✅ | ✅ |
| `status` | Show all service status | ✅ | ✅ |
| `logs <service>` | View/follow service logs | ✅ | ✅ |
| `test [file]` | Run integration tests | ✅ | ✅ |
| `psql [-c cmd]` | Database shell or command | ✅ | ✅ |
| `query <sql>` | Execute SQL and return output | ✅ | ✅ |
| `migrate [-f file]` | Run database migrations | ✅ | ✅ |
| `clean <target>` | Clear database tables | ✅ | ✅ |
| `reset` | Full reset (stop, clean, start) | ✅ | ✅ |
| `sync-check` | Verify environment is in sync | ✅ | ✅ |

### Service Names

Both scripts must accept the same service identifiers:

| Identifier | Resolves To |
|------------|-------------|
| `all` | All app services |
| `memory` | `memory-python` + `memory-rust` |
| `memory-python` | Memory storage (Python) |
| `memory-rust` | Salience gateway (Rust) |
| `orchestrator` | Event router |
| `executive` | Executive stub |

### Non-Functional Requirements

1. **Single source of truth** - Common logic lives in one place
2. **Extensible** - Easy to add new commands without editing multiple files
3. **Consistent UX** - Same interface regardless of environment
4. **Testable** - Core logic can be unit tested
5. **Self-documenting** - Help text generated from definitions

---

## 3. Proposed Architecture

### File Structure

```
scripts/
  _gladys.py              # Existing: ports, constants
  _service_base.py        # NEW: Abstract base, command registry
  _docker_backend.py      # NEW: Docker-specific implementations
  _local_backend.py       # NEW: Local-specific implementations
  docker.py               # Thin entry point
  local.py                # Thin entry point
  proto_sync.py           # Existing: proto management
```

### Core Abstractions

```python
# _service_base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

@dataclass
class ServiceDefinition:
    """Definition of a manageable service."""
    name: str
    description: str
    port: int
    group: str | None = None  # e.g., "memory" for memory-python

@dataclass
class Command:
    """Definition of a CLI command."""
    name: str
    help: str
    handler: str  # Method name on backend
    args: list[dict]  # Argparse argument definitions

class ServiceBackend(ABC):
    """Abstract base for environment-specific operations."""

    @abstractmethod
    def start_service(self, name: str, wait: bool = True) -> bool:
        """Start a service. Returns True on success."""
        pass

    @abstractmethod
    def stop_service(self, name: str) -> bool:
        """Stop a service. Returns True on success."""
        pass

    @abstractmethod
    def get_service_status(self, name: str) -> dict:
        """Get service status. Returns {running, healthy, status_text}."""
        pass

    @abstractmethod
    def get_logs(self, name: str, follow: bool = True) -> None:
        """Stream service logs."""
        pass

    @abstractmethod
    def run_sql(self, sql: str) -> tuple[int, str]:
        """Run SQL, return (exit_code, output)."""
        pass

    @abstractmethod
    def run_migration(self, file: str | None = None) -> int:
        """Run migrations. Returns exit code."""
        pass

class ServiceManager:
    """Main entry point for service management."""

    def __init__(self, backend: ServiceBackend, services: dict[str, ServiceDefinition]):
        self.backend = backend
        self.services = services
        self.groups = self._build_groups()

    def resolve_services(self, name: str) -> list[str]:
        """Resolve 'all', groups, or individual service names."""
        if name == "all":
            return list(self.services.keys())
        if name in self.groups:
            return self.groups[name]
        if name in self.services:
            return [name]
        raise ValueError(f"Unknown service: {name}")

    def cmd_start(self, args) -> int:
        """Start command implementation."""
        # Shared logic here
        pass

    def cmd_status(self, args) -> int:
        """Status command implementation."""
        # Shared logic here
        pass

    # ... other commands

    def run(self):
        """Parse args and dispatch to command handler."""
        # Build argparse from COMMANDS registry
        # Call appropriate handler
        pass
```

### Backend Implementations

```python
# _docker_backend.py

class DockerBackend(ServiceBackend):
    """Docker-specific service operations."""

    def __init__(self, compose_file: Path):
        self.compose_file = compose_file

    def start_service(self, name: str, wait: bool = True) -> bool:
        result = subprocess.run(
            ["docker-compose", "-f", str(self.compose_file), "up", "-d", name],
            capture_output=True
        )
        return result.returncode == 0

    def get_logs(self, name: str, follow: bool = True) -> None:
        args = ["docker-compose", "-f", str(self.compose_file), "logs"]
        if follow:
            args.append("-f")
        args.append(name)
        subprocess.run(args)

    # ... other methods
```

```python
# _local_backend.py

class LocalBackend(ServiceBackend):
    """Local process service operations."""

    def __init__(self, services: dict):
        self.services = services
        self.processes = {}  # Track spawned processes

    def start_service(self, name: str, wait: bool = True) -> bool:
        svc = self.services[name]
        # Spawn subprocess
        # Optionally wait for port
        pass

    def get_logs(self, name: str, follow: bool = True) -> None:
        # Local services log to files or stdout
        # Could tail log file or show process output
        pass

    # ... other methods
```

### Entry Points

```python
# docker.py (simplified)

from _service_base import ServiceManager
from _docker_backend import DockerBackend
from _gladys import ROOT, DOCKER_PORTS

SERVICES = {
    "memory-python": ServiceDefinition("memory-python", "Memory Storage", DOCKER_PORTS.memory_python, group="memory"),
    "memory-rust": ServiceDefinition("memory-rust", "Salience Gateway", DOCKER_PORTS.memory_rust, group="memory"),
    "orchestrator": ServiceDefinition("orchestrator", "Event Router", DOCKER_PORTS.orchestrator),
    "executive-stub": ServiceDefinition("executive-stub", "Executive", DOCKER_PORTS.executive),
}

if __name__ == "__main__":
    backend = DockerBackend(ROOT / "src" / "integration" / "docker-compose.yml")
    manager = ServiceManager(backend, SERVICES)
    manager.run()
```

---

## 4. Sync-Check Command

New command to detect environment drift:

```
$ python scripts/docker.py sync-check

Checking environment sync status...

Proto Files:
  ✅ memory.proto: in sync (hash: abc123)
  ✅ types.proto: in sync (hash: def456)
  ❌ common.proto: OUT OF SYNC
     - memory/proto: hash xyz789
     - orchestrator/proto: hash xyz788 (stale)

Migrations:
  ✅ Local DB: 9 migrations applied
  ✅ Docker DB: 9 migrations applied

Generated Stubs:
  ⚠️  memory_pb2.py may be stale (proto newer than stub)

Action needed:
  1. Run: python scripts/proto_sync.py
  2. Restart memory-python service
```

Implementation checks:
- Proto file hashes between locations
- Migration count in each database
- Stub file timestamps vs proto timestamps

---

## 5. Implementation Plan

### Phase 1: Core Framework (2-3 hours)
- Create `_service_base.py` with abstractions
- Implement `ServiceManager` with command dispatch
- Unit tests for core logic

### Phase 2: Docker Backend (1-2 hours)
- Create `_docker_backend.py`
- Migrate existing docker.py logic
- Verify all commands work

### Phase 3: Local Backend (1-2 hours)
- Create `_local_backend.py`
- Migrate existing local.py logic
- Add `logs` command (needs log file handling)
- Add `query` command

### Phase 4: Sync-Check (1 hour)
- Implement proto hash comparison
- Implement migration count check
- Implement stub freshness check

### Phase 5: Cleanup (30 min)
- Remove duplicated code
- Update documentation
- Commit

---

## 6. Open Questions

1. **Log handling for local services**: Local services run as background processes. Options:
   - Write to log files, `logs` command tails them
   - Keep process handles, stream stdout
   - Use a proper process manager (supervisord, etc.)

2. **Sync-check scope**: Should it also check:
   - Python package versions?
   - Rust build status?
   - Docker image freshness?

3. **Error handling**: Should commands fail fast or continue on partial failure?

---

## 7. Assignment Recommendation

| Phase | Recommended Owner | Rationale |
|-------|-------------------|-----------|
| Phase 1 (Framework) | Claude | Local environment, can iterate quickly |
| Phase 2 (Docker) | Gemini | Already familiar with Docker env |
| Phase 3 (Local) | Claude | Local environment expertise |
| Phase 4 (Sync-Check) | Either | Standalone feature |
| Phase 5 (Cleanup) | Whoever finishes first | |

**Alternative**: Single owner does all phases sequentially to maintain consistency.

---

## 8. Decision Needed

Please review and decide:

1. **Architecture**: Is this the right approach?
2. **Scope**: Any commands to add/remove?
3. **Assignment**: Who implements what?
4. **Priority**: Do this now or after other work?
