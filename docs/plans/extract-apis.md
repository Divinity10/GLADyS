# Extract APIs Plan

**Status**: Complete (committed on `extract-apis` branch, pending PR to main)
**Branch**: `extract-apis`
**Issues**: #36 (gladys_client), #37 (FUN API extraction)
**Reference**: [directory-restructure.md](directory-restructure.md) Phases 2-3

---

## Context

These are deferred phases from the directory restructure. Mike is building a Runescape sensor that will need to call `PublishEvents` via gRPC, and will eventually need dashboard observability. Clean APIs now prevent coupling problems later.

## Task 1: gladys_client (#36)

Extract gRPC/DB client code from `cli/` into `src/lib/gladys_client/` as a shared library.

### Files to extract

| Source | Target | What it does |
|--------|--------|-------------|
| `cli/_orchestrator.py` | `orchestrator.py` | `get_stub()`, `publish_event()`, `load_fixture()` — gRPC client for Orchestrator. CLI commands (`cmd_stats`, `cmd_list`, `cmd_watch`) can stay in cli/. |
| `cli/_db.py` | `db.py` | `get_dsn()`, `list_events()`, `get_event()`, `delete_event()`, `list_heuristics()`, `list_fires()`, `get_metrics()` — psycopg2 queries. |
| `cli/_cache_client.py` | `cache.py` | `get_stub()` — gRPC client for SalienceGateway. CLI commands can stay in cli/. |
| `cli/_health_client.py` | `health.py` | `check_health()` — multi-service health checker. |

### The coupling problem

`_db.py` imports `LOCAL_PORTS` and `DOCKER_PORTS` from `_gladys.py` to build the DSN. The fix: make `get_dsn()` take explicit `port` parameter instead of a `mode` string. Callers pass the port. No coupling to `_gladys.py`.

The other three files have no `_gladys.py` dependency. They do have `sys.path` hacks to find proto stubs — keep those for now (they work).

### Current consumers

- **Dashboard routers** (`events.py`, `metrics.py`, `fires.py`): import `_db` via `sys.path` hack in `backend/env.py`
- **Dashboard `services.py`**: imports `_gladys.is_port_open()` and backend classes — leave this alone, it's CLI admin stuff not client library
- **CLI tools**: use all four modules for CLI commands
- **Tests**: `tests/unit/test_orchestrator_client.py`

### After extraction

- `cli/` modules import from `gladys_client` instead of local `_` prefixed files
- Dashboard imports from `gladys_client` instead of `_db`
- Sensor code (Mike's) can import `gladys_client.orchestrator` to call `PublishEvents`

---

## Task 2: FUN API extraction (#37)

Separate REST/JSON endpoints from htmx rendering in the dashboard.

### Router inventory (10 routers in `src/services/dashboard/backend/routers/`)

**Pure REST/JSON — ready to move to `src/services/fun_api/`:**

- `cache.py` (`/api/cache`) — proxy to SalienceGateway gRPC
- `fires.py` (`/api/fires`) — DB query via `_db`
- `heuristics.py` (`/api/heuristics`) — proxy to Memory Storage gRPC
- `memory.py` (`/api/memory`) — proxy to Memory Storage gRPC
- `llm.py` (`/api/llm`) — HTTP to Ollama
- `logs.py` (`/api/logs`) — file reading
- `config.py` (`/api/config`) — config management

**Mixed (need splitting):**

- `events.py` — 6 HTMX endpoints (return HTML partials) + 4 REST endpoints (return JSON). REST endpoints: `POST /events/batch`, `GET /queue`, `DELETE /events/{id}`, `DELETE /events`.
- `metrics.py` — pure HTMX (returns `metrics.html` template). Keep in dashboard.
- `services.py` — 1 HTMX endpoint (`GET /health` returns `sidebar.html`) + 3 REST endpoints (`POST /{name}/start|stop|restart`).

### Recommended approach

Move pure REST routers to `src/services/fun_api/`. Split the REST endpoints out of `events.py` and `services.py`. Dashboard keeps HTMX-only routers. Both apps run in the same process (dashboard mounts fun_api as a sub-application or imports its routers).

Don't create a separate service/port — just separate the code so new REST endpoints have a clean home that doesn't involve htmx templates.

---

## Execution order

1. **gladys_client first** — it's simpler and unblocks Mike's sensor work
2. **FUN API second** — depends on gladys_client (dashboard routers currently import `_db`)

## Verify

- All services start (local)
- All existing tests pass (98 tests: 25+44+29)
- Dashboard loads and functions
- CLI tools work (`cli/local.py`)
- `from gladys_client.orchestrator import publish_event` works from Python REPL
