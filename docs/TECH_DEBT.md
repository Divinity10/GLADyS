# Technical Debt

Items to revisit post-PoC. Each entry should note what it is, why it's fine for now, and what to do when it matters.

## `gladys_client/db.py` — Connection per call

Opens and closes a psycopg2 connection for every function call. `get_metrics()` opens one connection for four sequential queries, but each of `list_events()`, `list_fires()`, etc. opens its own.

**Why it's fine now**: Dashboard is single-user, polling frequency is low.
**When it matters**: If polling interval drops below ~2s or multiple dashboard instances run simultaneously.
**Fix**: Add connection pooling (e.g., `psycopg2.pool.SimpleConnectionPool`) with module-level lifecycle.

## `gladys_client/db.py` — DSN passed as parameter

Every caller passes `env.get_db_dsn()` on every call. Keeps the module stateless but creates repetitive call sites.

**Why it's fine now**: Only three callers (events, metrics, fires routers).
**When it matters**: If more consumers adopt `gladys_client.db` and the pattern becomes noisy.
**Fix**: Add a `configure(dsn)` or `set_dsn(dsn)` function for module-level state, called once at startup.

## `gladys_client/db.py` — `get_metrics()` runs four queries

Four separate `SELECT COUNT(*)` queries instead of a single query with subqueries.

**Why it's fine now**: Each query is trivial and indexed. Total time is negligible.
**When it matters**: If tables grow large or metrics endpoint is called frequently.
**Fix**: Combine into one query with subselects, or cache results with a short TTL.

## Executive — `accepted=True` on rejection (#43)

`ProvideFeedback` in `src/services/executive/gladys_executive/server.py` returns `accepted=True` with `error_message` for all rejection cases (quality gate, dedup, parse failure). Callers cannot distinguish accepted feedback from rejected without parsing `error_message`.

**Why it's fine now**: Dashboard doesn't branch on `accepted` — it shows the error_message if present.
**When it matters**: When clients need programmatic rejection handling (e.g., retry logic, metrics on rejection rate).
**Fix**: Return `accepted=False` for rejections. Update dashboard and any client code that checks this field.

## f-string logging across services

~50 log calls in orchestrator (server.py, event_queue.py, clients/, outcome_watcher.py, skill_registry.py, registry.py) and memory (grpc_server.py) use f-string formatting instead of structlog keyword args. Router.py and executive/server.py were converted in W3 review fixes.

**Why it's fine now**: structlog still captures the output; the difference is that structured fields aren't machine-parseable from f-strings.
**When it matters**: When log aggregation or querying by structured fields is needed.
**Fix**: Convert remaining f-string `logger.xxx(f"...")` calls to `logger.xxx("message", key=value)` style across all services.

## `datetime.utcnow()` deprecation in outcome_watcher.py

`outcome_watcher.py` uses `datetime.utcnow()` which is deprecated since Python 3.12 in favor of `datetime.now(datetime.UTC)`.

**Why it's fine now**: Functionally identical; only triggers deprecation warnings in test output.
**When it matters**: Python 3.14+ may remove it entirely.
**Fix**: Replace `datetime.utcnow()` with `datetime.now(datetime.UTC)` in `outcome_watcher.py` and any other files using the old pattern.

## `gladys_client` — Sync-only API

The client library (`src/lib/gladys_client/`) exposes only synchronous gRPC wrappers. All four services use async gRPC internally (`grpc.aio`), and the convergence test already bypasses the client lib to use async stubs directly for full `EventAck` field access.

**Why it's fine now**: Only two sync consumers (dashboard polling, CLI scripts). The convergence test works around it.
**When it matters**: PoC 2 introduces concurrent processing and volume handling. Any async caller (test harness, future orchestration scripts) must duplicate gRPC setup instead of using the client lib.
**Fix**: Add async variants of key methods (`publish_event_async`, `check_health_async`, etc.) alongside the existing sync API. Consider `grpc.aio` channels with proper lifecycle management.

## Stale Streamlit references in historical docs

Several files in `docs/coordination/` and one test comment still reference the old Streamlit dashboard (`src/ui/dashboard.py`) which no longer exists:

- `docs/coordination/GEMINI_BUG_FIXES.md` lines 75-76, 116
- `docs/coordination/MESSAGES.md` line 43
- `tests/integration/test_subscription_delivery.py` line 71

**Why it's fine now**: These are historical coordination docs and a test comment. They don't affect runtime or AI session behavior (CLAUDE.md, INDEX.md, and DASHBOARD_V2.md were already fixed).
**When it matters**: If someone reads these docs expecting them to be current.
**Fix**: Update references to note the dashboard is now FastAPI at `src/services/dashboard/`, or mark the coordination docs as historical.

## Sensors — Unused `import os`

Both `packs/sensors/sudoku-sensor/sensor.py` and `packs/sensors/melvor-sensor/sensor.py` import `os` but never use it. `setup_logging()` handles env vars internally.

**Why it's fine now**: No functional impact.
**When it matters**: Linter enforcement.
**Fix**: Remove `import os` from both files.
