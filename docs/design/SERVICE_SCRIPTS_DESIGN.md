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
| `health [service]` | Detailed health with diagnostics | ✅ | ✅ |
| `logs <service>` | View/follow service logs | ✅ | ✅ |
| `test [file]` | Run integration tests | ✅ | ✅ |
| `psql [-c cmd]` | Database shell or command | ✅ | ✅ |
| `query <sql>` | Execute SQL and return output | ✅ | ✅ |
| `migrate [-f file]` | Run database migrations | ✅ | ✅ |
| `clean <target>` | Clear database tables | ✅ | ✅ |
| `reset` | Full reset (stop, clean, start) | ✅ | ✅ |
| `sync-check` | Verify environment is in sync | ✅ | ✅ |
| `cache stats` | Show cache statistics | ✅ | ✅ |
| `cache list` | List cached heuristics | ✅ | ✅ |
| `cache flush` | Clear entire cache | ✅ | ✅ |
| `cache evict <id>` | Remove single heuristic from cache | ✅ | ✅ |

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

## 4. Health Endpoints

Each service exposes health information via gRPC. The admin scripts query these endpoints to provide detailed status.

### Health Command

```
$ python scripts/docker.py health [service]

Service Health Report
=====================

memory-python (localhost:50061):
  Status: HEALTHY
  Database: connected (5432)
  Tables: heuristics(142), events(1203), heuristic_fires(89)
  Uptime: 2h 34m

memory-rust (localhost:50062):
  Status: HEALTHY
  Cache: 48/1000 entries, 4.8% full
  Hit rate: 87.3% (last 1000 queries)
  Python backend: connected (50061)
  Uptime: 2h 34m

orchestrator (localhost:50060):
  Status: HEALTHY
  Dependencies:
    - memory-rust: connected
    - memory-python: connected
    - executive: connected
  Events processed: 1203 (0 errors)
  Uptime: 2h 34m

executive-stub (localhost:50063):
  Status: HEALTHY
  Memory backend: connected (50061)
  LLM: not configured
  Uptime: 2h 34m
```

### gRPC Health Proto

Each service implements a Health RPC (standard gRPC health checking pattern):

```protobuf
// In each service's proto file
service Health {
    rpc Check(HealthCheckRequest) returns (HealthCheckResponse);
    rpc GetDetails(HealthDetailsRequest) returns (HealthDetailsResponse);
}

message HealthCheckRequest {}

message HealthCheckResponse {
    enum Status {
        UNKNOWN = 0;
        HEALTHY = 1;
        UNHEALTHY = 2;
        DEGRADED = 3;
    }
    Status status = 1;
}

message HealthDetailsRequest {}

message HealthDetailsResponse {
    HealthCheckResponse.Status status = 1;
    int64 uptime_seconds = 2;
    map<string, string> details = 3;  // Service-specific key-value pairs
}
```

### Service-Specific Details

| Service | Details Reported |
|---------|------------------|
| memory-python | `db_status`, `table_counts`, `connection_pool` |
| memory-rust | `cache_size`, `cache_capacity`, `hit_rate`, `backend_status` |
| orchestrator | `events_processed`, `error_count`, `dependency_status` |
| executive-stub | `memory_status`, `llm_configured`, `llm_status` |

---

## 5. Cache Management

The Rust salience gateway maintains an LRU cache. Admin tools provide cache inspection and control.

### Cache Commands

```bash
# View cache statistics
$ python scripts/docker.py cache stats
Cache Statistics (memory-rust):
  Entries: 48/1000 (4.8% full)
  Hit rate: 87.3% (last 1000 queries)
  Oldest entry: 2h 15m ago
  Memory: ~2.4 MB

# List cached heuristics
$ python scripts/docker.py cache list
Cached Heuristics:
  abc123... "Morning greeting pattern" (hits: 42, age: 15m)
  def456... "Task reminder trigger" (hits: 28, age: 45m)
  ...
  [48 entries total]

# Flush entire cache
$ python scripts/docker.py cache flush
Flushed 48 entries from cache.

# Evict specific heuristic
$ python scripts/docker.py cache evict abc123
Evicted heuristic abc123 from cache.
```

### Cache Management Proto

```protobuf
// In salience.proto (SalienceGateway service)
service SalienceGateway {
    // Existing RPCs...

    // Cache management
    rpc FlushCache(FlushCacheRequest) returns (FlushCacheResponse);
    rpc EvictFromCache(EvictFromCacheRequest) returns (EvictFromCacheResponse);
    rpc GetCacheStats(GetCacheStatsRequest) returns (GetCacheStatsResponse);
    rpc ListCachedHeuristics(ListCachedHeuristicsRequest) returns (ListCachedHeuristicsResponse);
}

message FlushCacheRequest {}
message FlushCacheResponse {
    int32 entries_flushed = 1;
}

message EvictFromCacheRequest {
    string heuristic_id = 1;
}
message EvictFromCacheResponse {
    bool found = 1;
}

message GetCacheStatsRequest {}
message GetCacheStatsResponse {
    int32 current_size = 1;
    int32 max_capacity = 2;
    float hit_rate = 3;
    int64 total_hits = 4;
    int64 total_misses = 5;
}

message ListCachedHeuristicsRequest {
    int32 limit = 1;  // 0 = all
}
message CachedHeuristicInfo {
    string heuristic_id = 1;
    string name = 2;
    int32 hit_count = 3;
    int64 cached_at_unix = 4;
    int64 last_hit_unix = 5;
}
message ListCachedHeuristicsResponse {
    repeated CachedHeuristicInfo heuristics = 1;
}
```

### Use Cases

| Command | When to Use |
|---------|-------------|
| `cache stats` | Monitoring, performance tuning |
| `cache list` | Debugging, understanding what's cached |
| `cache flush` | After schema changes, bulk heuristic updates |
| `cache evict <id>` | After updating single heuristic, debugging |

---

## 6. Authorization (Placeholder)

Current scope: local-only admin tools, no authorization needed.

Future scope: if admin tools are exposed remotely (e.g., via REST gateway), add:

```yaml
# ~/.gladys/admin.yaml
admin:
  enabled: true
  auth:
    type: local  # Options: local, token, mtls
    # token: <generated-token>  # For remote access
```

For now, this is **design only** — no implementation until remote access is needed.

---

## 7. Sync-Check Command

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

## 8. Implementation Plan

### Phase 1: Core Framework
- Create `_service_base.py` with abstractions
- Implement `ServiceManager` with command dispatch
- Unit tests for core logic

### Phase 2: Docker Backend
- Create `_docker_backend.py`
- Migrate existing docker.py logic
- Verify all commands work

### Phase 3: Local Backend
- Create `_local_backend.py`
- Migrate existing local.py logic
- Add `logs` command (needs log file handling)
- Add `query` command

### Phase 4: Sync-Check
- Implement proto hash comparison
- Implement migration count check
- Implement stub freshness check

### Phase 5: Health Endpoints
- Add Health service to each proto file
- Implement Health RPC in memory-python
- Implement Health RPC in memory-rust
- Implement Health RPC in orchestrator
- Implement Health RPC in executive-stub
- Add `health` command to admin scripts

### Phase 6: Cache Management
- Add cache management RPCs to salience.proto
- Implement FlushCache, EvictFromCache, GetCacheStats, ListCachedHeuristics in Rust
- Add `cache` subcommand group to admin scripts

### Phase 7: Cleanup
- Remove duplicated code
- Update documentation
- Commit

---

## 9. Open Questions

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

## 10. Assignment Recommendation

| Phase | Recommended Owner | Rationale |
|-------|-------------------|-----------|
| Phase 1 (Framework) | Claude | Local environment, can iterate quickly |
| Phase 2 (Docker) | Gemini | Already familiar with Docker env |
| Phase 3 (Local) | Claude | Local environment expertise |
| Phase 4 (Sync-Check) | Either | Standalone feature |
| Phase 5 (Health) | Split | Each agent implements for their env |
| Phase 6 (Cache) | Gemini | Rust implementation in Docker |
| Phase 7 (Cleanup) | Whoever finishes first | |

**Alternative**: Single owner does all phases sequentially to maintain consistency.

**Recommended priority order**: Phase 1 → Phase 4 → Phase 2 → Phase 3 → Phase 5 → Phase 6 → Phase 7

Rationale: Framework first enables all other work. Sync-check early to catch drift. Health and cache are enhancements after core functionality works.

---

## 11. Decision Needed

Please review and decide:

1. **Architecture**: Is this the right approach?
2. **Scope**: Any commands to add/remove?
3. **Assignment**: Who implements what?
4. **Priority**: Do this now or after other work?
