# Technical Debt: Service Architecture & Developer Experience

**Created**: 2026-01-26
**Status**: Resolved
**Closed**: 2026-01-26

---

## Summary

All high and medium priority items have been resolved. This document is kept for historical reference.

---

## Resolved Items

### 1. Inconsistent Service Entry Points ✅

**Problem**: Each Python service used a different pattern.

**Solution**: Standardized all services on `__main__.py` pattern:
```bash
python -m gladys_memory start
python -m gladys_orchestrator start
python -m gladys_executive start
```

### 2. Service Management Scripts ✅

**Problem**: `docker.py` and `local.py` had inconsistent commands and couldn't restart individual services.

**Solution**: Complete refactor with shared framework:
- `scripts/_service_base.py` - ServiceManager, ServiceBackend abstraction
- `scripts/_local_backend.py` - Local process management
- `scripts/_docker_backend.py` - Docker Compose integration
- Both scripts now support identical commands: `status`, `health`, `start`, `stop`, `restart`, `logs`, `migrate`, `cache`, `sql`, `psql`, `test`, `clean-db`

### 3. Parallel AI Development (Claude + Gemini) ✅

**Problem**: Synchronization when one agent makes changes affecting both environments.

**Solution**:
- `scripts/_sync_check.py` - Detects proto/migration drift
- Clear port separation (local: 50050-50053, Docker: 50060-50063)
- Work log discipline via `docs/design/LEARNING_WORK_LOG.md`

### 4. Proto File Sync Pain ✅

**Problem**: Proto files duplicated between `src/memory/proto/` and `src/orchestrator/proto/`.

**Solution** (different from originally proposed): Single shared `proto/` directory at project root.
- `proto/*.proto` - Single source of truth
- `scripts/proto_gen.py` - Generates stubs to service-specific `generated/` directories
- Legacy `proto_sync.py` removed
- Legacy `src/memory/proto/` and `src/orchestrator/proto/` directories removed

**Why not volume mounts?** The shared directory approach is simpler and works for both local and Docker development without additional Docker configuration.

### 5. Pre-commit Hook for Proto Sync ✅ (Not Needed)

**Original proposal**: Hook to validate proto files are in sync.

**Resolution**: No longer needed. With single `proto/` directory, there's nothing to sync. Stale stubs are caught at runtime with clear error messages pointing to `proto_gen.py`.

### 6. Volume Mount Protos in Docker ✅ (Solved Differently)

**Original proposal**: Mount shared proto volume in Docker.

**Resolution**: Solved by moving to single `proto/` directory. Docker builds copy from this location. No volume mounts needed.

### 7. Hybrid Dev Mode Documentation

**Status**: Deferred. Not currently a pain point - developers either use full local or full Docker.

---

## References

- [SERVICE_SCRIPTS_WORKLOG.md](../archive/SERVICE_SCRIPTS_WORKLOG.md) - Implementation details (archived)
- [scripts/README.md](../../scripts/README.md) - Current script documentation
