# Directory Restructure Plan

**Status**: Complete (2026-01-30)

**Deviations**:
- Phase 2 (gladys_client extraction) deferred — cli/ modules are tightly coupled to _gladys.py config. Dashboard continues importing via sys.path. Extraction needs API design work.
- Phase 3 (FUN API extraction) deferred — dashboard routers mix htmx partial rendering with REST/gRPC proxy logic. Clean extraction requires splitting each router.
- Phase 4 executed incrementally alongside Phases 1-3, not as a separate batch.
**Prerequisite for**: Phase 1 (see [ITERATIVE_DESIGN.md](../design/ITERATIVE_DESIGN.md))
**Reference**: [ARCHITECTURE.md Â§9](../design/ARCHITECTURE.md), [INTERFACES.md](../design/INTERFACES.md)

---

## Why

The architecture decisions from 2026-01-29 define a subsystem taxonomy and pack structure that the current directory layout doesn't support. Restructuring now (small codebase) is cheaper than later.

## Current → Target

| Current | Target | Notes |
|---------|--------|-------|
| `src/orchestrator/` | `src/services/orchestrator/` | Move into services/ |
| `src/memory/python/` | `src/services/memory/` | Flatten — remove python/ nesting |
| `src/memory/rust/` | `src/services/salience/` | Salience gets its own home |
| `src/executive/` | `src/services/executive/` | Move into services/ |
| `src/dashboard/` | `src/services/dashboard/` | Keep name. UI + backend stay together. |
| (new) | `src/services/fun_api/` | Extract REST gateway from dashboard backend |
| `src/common/` | `src/lib/gladys_common/` | Move into lib/ |
| (new) | `src/lib/gladys_client/` | Unified gRPC client (extracted from scripts/) |
| `src/memory/migrations/` | `src/db/migrations/` | Schema is shared concern, not memory-owned |
| `scripts/` | `cli/` | Rename. Shared libs move to src/lib/ |
| `plugins/` | `packs/` | Match architecture terminology |
| `src/integration/` | `tests/integration/` | Consolidate tests |
| `tests/` (root) | `tests/unit/` + `tests/integration/` | Restructure |
| `src/outputs/` | Delete | Placeholder (.gitkeep only) |
| `src/sensors/` | Delete | Placeholder (.gitkeep only) |
| `src/salience/` | Delete | Placeholder (.gitkeep only) |

## Execution Order

### Phase 1: Mechanical moves

Pure `git mv` operations. No code changes. Commit after each group so git tracks renames cleanly.

1. Create directory scaffolding: `src/services/`, `src/lib/`, `src/db/`, `packs/`
2. Move services into `src/services/` (orchestrator, executive, dashboard)
3. Flatten memory: `src/memory/python/` → `src/services/memory/`
4. Move Rust salience: `src/memory/rust/` → `src/services/salience/`
5. Move common: `src/common/` → `src/lib/gladys_common/`
6. Move migrations: `src/memory/migrations/` → `src/db/migrations/`
7. Rename plugins → packs: `plugins/` → `packs/`
8. Rename scripts → cli: `scripts/` → `cli/`
9. Consolidate tests: `src/integration/` → `tests/integration/`, existing `tests/` files → `tests/unit/`
10. Delete empty placeholders: `src/outputs/`, `src/sensors/`, `src/salience/`

### Phase 2: Extract shared client

Move existing gRPC client code from `cli/` (formerly scripts/) into `src/lib/gladys_client/`. This is a move-and-refactor, not a rewrite.

Source files to extract from:
- `cli/_orchestrator.py` — gRPC client for orchestrator
- `cli/_db.py` — direct DB client
- `cli/_cache_client.py` — cache client
- `cli/_health_client.py` — health check client

Target: `src/lib/gladys_client/` as an installable Python package with `pyproject.toml`.

**Approach**: Move the code, make it importable, update `cli/` to import from the new location. Don't redesign the API — refine later based on actual consumer needs.

### Phase 3: Extract FUN API

Separate the REST gateway from the dashboard UI:

- `src/services/fun_api/` — FastAPI REST endpoints that proxy gRPC calls (currently in `src/services/dashboard/backend/`)
- `src/services/dashboard/` — HTML/htmx/Alpine frontend, serves static files, imports fun_api

The fun_api is a service that exposes gRPC operations over REST. The dashboard is a UI consumer. They deploy together for now but are logically separate.

### Phase 4: Update all imports and configs

- Update all Python imports across services, CLI, tests
- Update Dockerfiles (COPY paths, working directories)
- Update docker-compose files
- Update `proto_gen.py` output paths
- Update `CODEBASE_MAP.md` with new layout
- Update any hardcoded paths in docs

### Phase 5: Verify

- All services start (local and Docker)
- All existing tests pass
- Dashboard loads and functions
- CLI tools work (`cli/local.py`, `cli/docker.py`)
- Proto generation works

## Decisions

- **Dashboard keeps its name** — not renamed to fun_api. The FUN API is the REST gateway layer extracted from the dashboard backend.
- **gladys_client starts as extraction** — move existing code from scripts, don't design a new SDK upfront.
- **Commit per phase** — keeps git history clean and makes bisection possible if something breaks.

## Deferred

- **Supervisor service** (`src/services/supervisor/`) — no implementation exists yet. Create the directory when there's code to put in it.
- **gladys_client API design** — refine after dashboard and CLI are both consuming it. Don't guess the interface.

## Done When

- All services start (local + Docker)
- All existing tests pass
- Import paths updated everywhere
- Dockerfiles updated
- `CODEBASE_MAP.md` reflects new layout
- No references to old paths in code or docs

