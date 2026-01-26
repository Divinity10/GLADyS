# Technical Debt: Service Architecture & Developer Experience

**Created**: 2026-01-26
**Status**: Open
**Priority**: High (blocking parallel AI development)

---

## Problems

### 1. Inconsistent Service Entry Points

Each Python service uses a different pattern:

| Service | Entry Point | Pattern |
|---------|-------------|---------|
| Memory | `python -m gladys_memory.grpc_server` | Direct module |
| Orchestrator | `python -m gladys_orchestrator start` | `__main__.py` + CLI |
| Executive | `python stub_server.py` | Script file |

**Impact**: Confusing, error-prone, hard to document.

**Solution**: Standardize on `__main__.py` pattern for all services:
```
python -m gladys_memory [start|status]
python -m gladys_orchestrator [start|status]
python -m gladys_executive [start|status]
```

### 2. Service Management Scripts (`scripts/docker.py`, `scripts/local.py`)

**Current Issues**:
- `docker.py restart memory-rust` fails (only accepts group names, not individual services)
- Inconsistent commands between docker.py and local.py
- No unified interface for "restart just this one service"

**What the scripts SHOULD support**:

| Command | docker.py | local.py | Notes |
|---------|-----------|----------|-------|
| `start all` | ✅ | ✅ | Start all app services |
| `start <service>` | ✅ groups only | ✅ | Start specific service |
| `stop all` | ✅ | ✅ | |
| `stop <service>` | ✅ groups only | ❓ | |
| `restart all` | ✅ | ❓ | |
| `restart <service>` | ❌ individual | ❓ | **NEEDED** |
| `status` | ✅ | ✅ | |
| `logs <service>` | ✅ | ❓ | |
| `clean [heuristics\|events\|all]` | ✅ | ✅ | |
| `migrate` | ✅ | ✅ | |
| `test <file>` | ✅ | ✅ | |
| `psql` | ✅ | ✅ | |

**Solution**: Audit both scripts, create parity, support individual service names.

### 3. Parallel AI Development (Claude + Gemini)

**Current Setup** (working well for isolation):

| Agent | Environment | Ports | Database |
|-------|-------------|-------|----------|
| Claude | Local | 50050-50053 | localhost:5432 |
| Gemini | Docker | 50060-50063 | localhost:5433 |

**What's NOT the problem**: Isolation. The local/Docker split keeps agents from stepping on each other.

**What IS the problem**: Synchronization when one agent makes changes that affect both environments:

1. **Proto changes** - Claude modifies protos locally → Gemini's Docker needs rebuild or volume pickup
2. **Migration changes** - Either agent adds migration → both databases need it applied
3. **Generated code** - Proto stubs must be regenerated in both environments
4. **Runtime behavior differences** - Service addresses differ (`localhost:50051` vs `memory-python:50051`)

**Solutions**:

1. **Pre-commit hook** to validate proto sync before commits
2. **Sync status command** in scripts: `python scripts/docker.py sync-check`
3. **Work log discipline** - Always note when changes require Docker rebuild
4. **Volume mounts for protos** - Docker reads from canonical location, no copy needed

### 4. Proto File Sync Pain

**Problem**: Proto files must be copied between:
- `src/memory/proto/` (canonical source)
- `src/orchestrator/proto/` (copy)
- Generated stubs in each service

**Current mitigation**: `scripts/proto_sync.py`

**Why can't we use a single location?**
- Docker build contexts are per-service (`src/memory/`, `src/orchestrator/`)
- Each Dockerfile can only access files within its context
- Symlinks don't work reliably (Windows, Docker)

**Solutions to evaluate**:

#### Option A: Build-time Proto Fetch (Current + Better)
Keep `proto_sync.py` but:
- Add pre-commit hook to auto-sync
- Add CI check to fail if out of sync
- Make Dockerfiles validate proto hashes

#### Option B: Shared Proto Volume in Docker
```yaml
services:
  memory-python:
    volumes:
      - ../memory/proto:/app/proto:ro  # Single source
```
Then regenerate stubs at container startup.

**Tradeoff**: Option B adds startup latency but eliminates sync issues.

#### Option C: Proto Submodule (Overkill)
Git submodule for protos. Too heavy for this project.

**Recommendation**: Option B (shared volume) for Docker, keep sync script for local dev.

### 5. Rust Dependency for Development

**Problem**: Not everyone has Rust installed. Current stack requires Rust for the salience gateway.

**Current mitigation**: Docker runs Rust service, so local dev doesn't need Rust.

**Remaining issue**: Local development (`scripts/local.py`) requires Rust to be installed.

**Solutions**:
1. **Document clearly**: Local dev requires Rust OR use Docker
2. **Python-only mode**: Add config flag to skip Rust gateway, route all salience through Python
3. **Docker hybrid**: Local services connect to Docker's Rust container

**Recommendation**: Option 3 (hybrid) gives best of both worlds - fast Python iteration, Rust performance.

---

## Action Items

### High Priority (blocking work)
1. [ ] Audit and fix `scripts/docker.py` to support individual service restart
2. [ ] Create parity between `docker.py` and `local.py`
3. [ ] Add sync-check command to detect environment drift

### Medium Priority (developer experience)
4. [ ] Standardize all services on `__main__.py` pattern
5. [ ] Add pre-commit hook for proto sync validation
6. [ ] Volume mount protos in Docker to eliminate copy step

### Low Priority (nice to have)
7. [ ] Document hybrid dev mode (local Python + Docker Rust)

---

## References

- [LEARNING_WORK_LOG.md](LEARNING_WORK_LOG.md) - TODO note about run.py audit
- [ADR-0001](../adr/ADR-0001-Architecture.md) - Polyglot architecture decision
