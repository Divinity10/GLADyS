# Service Scripts Work Log

Coordination log for Claude and Gemini implementing the service scripts refactor.

**Design Doc**: [SERVICE_SCRIPTS_DESIGN.md](../design/SERVICE_SCRIPTS_DESIGN.md)

---

## Status Summary

| Phase | Description | Owner | Status |
|-------|-------------|-------|--------|
| 1 | Core Framework (`_service_base.py`) | Gemini | ✅ Complete |
| 2 | Docker Backend (`_docker_backend.py`) | Gemini | ✅ Complete |
| 3 | Local Backend (`_local_backend.py`) | Claude | ✅ Complete |
| 4 | Sync-Check Command | Claude | ✅ Complete |
| 5 | Health Endpoints | Claude | ✅ Complete |
| 6 | Cache Management | Gemini | ✅ Complete |
| 7 | Cleanup | Claude | ✅ Complete |

---

## Completed Work

### 2026-01-26 - Phase 1 & 2 (Gemini)

Created the core framework:
- `scripts/_service_base.py` - ServiceDefinition, ServiceBackend, ServiceManager
- `scripts/_docker_backend.py` - Docker-specific implementations
- `scripts/docker.py` - Converted to use framework

### 2026-01-26 - Phase 6: Cache Management (Gemini)

Implemented cache management for the Rust salience gateway (`memory-rust`):
- **Proto**: Added `FlushCache`, `EvictFromCache`, `GetCacheStats`, and `ListCachedHeuristics` to `SalienceGateway` service.
- **Rust**:
    - Enhanced `MemoryCache` to track total hits/misses.
    - Updated `CachedHeuristic` to include `hit_count` and `last_hit_ms`.
    - Implemented gRPC handlers for all cache management RPCs in `SalienceService`.
    - Updated `evaluate_salience` to record cache performance stats.
- **CLI**:
    - Created `scripts/_cache_client.py` as a Python gRPC helper for cache operations.
    - Added `cache` subcommand with `stats`, `list`, `flush`, and `evict` sub-commands to `ServiceManager`.
    - Implemented backend methods in `DockerBackend` and `LocalBackend` to use the cache helper.

### 2026-01-26 - Phase 3 & 4 (Claude)

Completed local backend and sync-check:
- `scripts/_local_backend.py` - Local process management (start/stop/status via port detection)
- `scripts/local.py` - Converted to use framework
- `scripts/_sync_check.py` - Environment sync checking (proto hashes, stub freshness, migrations)
- `scripts/pyproject.toml` - Proper uv-based dependency management

**Sync-check now detects**:
- Proto file drift between memory/proto and orchestrator/proto
- Stale generated stubs
- Missing migrations in either local or Docker database

### 2026-01-26 - Standardize __main__.py Pattern (Claude)

Standardized all Python service entry points to use `python -m <package> start` pattern:

**memory-python**:
- Created `gladys_memory/__main__.py` with `start` and `status` commands
- Old: `python -m gladys_memory.grpc_server`
- New: `python -m gladys_memory start`

**executive-stub**:
- Restructured as proper `gladys_executive` package
- Created `gladys_executive/__init__.py`, `__main__.py`, `server.py`
- Old: `python stub_server.py`
- New: `python -m gladys_executive start`

**orchestrator**: Already had `__main__.py` with `start` command (no changes needed)

**Updated**:
- `scripts/_local_backend.py` - Uses new standardized commands
- `src/memory/python/Dockerfile` - Uses `ENTRYPOINT ["python", "-m", "gladys_memory"] CMD ["start"]`
- `src/executive/Dockerfile` - Uses `ENTRYPOINT ["python", "-m", "gladys_executive"] CMD ["start"]`

### 2026-01-26 - Windows Encoding Fix (Claude)

Fixed UnicodeEncodeError on Windows by replacing emoji status icons with ASCII:
- `scripts/_service_base.py` - Changed 🟢🔴🟡 to `[OK]`, `[--]`, `[!!]` in `cmd_status()`
- `scripts/_sync_check.py` - Changed ✅❌⚠️ to `[OK]`, `[X]`, `[!]` (done earlier)

### 2026-01-26 - Integration Tests for Cache Management (Claude)

Fixed and added integration tests:
- **Fixed `test_orchestrator_memory.py`**:
  - Added separate addresses for MemoryStorage (50051) and SalienceGateway (50052)
  - Fixed `test_salience_evaluation_directly()` to use correct Rust gateway port
  - Added pytest fixture to ensure test heuristic exists before salience tests

- **Created `test_cache_management.py`** with 8 tests covering:
  - `TestCacheStats`: GetCacheStats RPC returns valid statistics
  - `TestCacheList`: ListCachedHeuristics on empty and populated cache
  - `TestCacheFlush`: FlushCache clears all entries
  - `TestCacheEvict`: EvictFromCache removes specific heuristics
  - `TestCacheHitTracking`: Hit rate increases on repeated queries

### 2026-01-26 - Phase 5: Health Endpoints (Claude)

Implemented gRPC health check endpoints for all services:

**Shared Proto** (`proto/`):
- Created shared `proto/` directory at project root (single source of truth)
- Added `GetHealth` and `GetHealthDetails` RPCs to `types.proto`
- Added Health RPCs to all service definitions (memory.proto, orchestrator.proto, executive.proto)
- Created `scripts/proto_gen.py` to regenerate stubs (replaces proto_sync.py - no more syncing needed)

**Service Implementations**:
- **memory-python**: Added Health RPCs to `MemoryStorageServicer` with db_connected, embedding_model details
- **memory-rust**: Added Health RPCs to `SalienceService` with cache stats (size, hit_rate, etc.)
- **orchestrator**: Added Health RPCs to `OrchestratorServicer` with connected service status
- **executive-stub**: Added Health RPCs to `ExecutiveServicer` with ollama/memory connection status

**CLI**:
- Added `health` command to `_service_base.py` ServiceManager
- Added `get_service_health()` method to ServiceBackend (implemented in both backends)
- Created `scripts/_health_client.py` - gRPC client for health checks

**Usage**:
```bash
python scripts/local.py health              # Check all services
python scripts/local.py health memory-rust  # Check specific service
python scripts/local.py health -d           # Detailed output with uptime/metrics
```

### 2026-01-26 - Phase 7: Cleanup (Claude)

Cleaned up legacy proto structure:

**Removed:**
- `src/memory/proto/` - Legacy proto directory (replaced by shared `proto/`)
- `src/orchestrator/proto/` - Legacy proto directory (replaced by shared `proto/`)
- `scripts/proto_sync.py` - Replaced by `proto_gen.py`

**Documentation Updated:**
- `CONTRIBUTING.md` - Updated proto regeneration instructions
- `docs/GETTING_STARTED.md` - Updated proto paths and references
- `scripts/README.md` - Added health command, updated file list
- `src/memory/README.md` - Updated proto references
- `src/orchestrator/README.md` - Updated proto dependency section
- `CODEBASE_MAP.md` - Already updated in Phase 5

---

## How to Use This Log

1. **Before starting work**: Read this file to see current status
2. **After completing work**: Update the status table and add entry to "Completed Work"
3. **If you hit blockers**: Add to "Blockers/Issues" section below

---

## Blockers/Issues

_None currently._

---

## Next Steps

All phases complete! The service scripts refactor is finished.

### Post-Refactor Notes

- Proto source of truth is now `proto/` at project root
- Use `python scripts/proto_gen.py` to regenerate stubs
- Use `python scripts/local.py health` to verify gRPC endpoints
- Legacy `src/memory/proto/` and `src/orchestrator/proto/` have been removed
- `proto_sync.py` removed (replaced by `proto_gen.py`)

---

## Testing Commands

```bash
# Test local.py with framework
cd scripts
python local.py status
python local.py health
python local.py health -d
python local.py cache stats
python local.py cache list

# Test docker.py with framework
python docker.py status
python docker.py health
python docker.py health -d

# Regenerate proto stubs after editing proto/
python proto_gen.py

# Integration tests (from src/integration)
cd src/integration
uv run pytest test_orchestrator_memory.py -v
uv run pytest test_cache_management.py -v
```
