# Technical Debt

Items to revisit post-PoC. Each entry should note what it is, why it's fine for now, and what to do when it matters.

## `scripts/_db.py` — Connection per call

Opens and closes a psycopg2 connection for every function call. `get_metrics()` opens one connection for four sequential queries, but each of `list_events()`, `list_fires()`, etc. opens its own.

**Why it's fine now**: Dashboard is single-user, polling frequency is low.
**When it matters**: If polling interval drops below ~2s or multiple dashboard instances run simultaneously.
**Fix**: Add connection pooling (e.g., `psycopg2.pool.SimpleConnectionPool`) with module-level lifecycle.

## `scripts/_db.py` — DSN passed as parameter

Every caller passes `env.get_db_dsn()` on every call. Keeps the module stateless but creates repetitive call sites.

**Why it's fine now**: Only three callers (events, metrics, fires routers).
**When it matters**: If more consumers adopt `_db.py` and the pattern becomes noisy.
**Fix**: Add a `configure(dsn)` or `set_dsn(dsn)` function for module-level state, called once at startup.

## `scripts/_db.py` — `get_metrics()` runs four queries

Four separate `SELECT COUNT(*)` queries instead of a single query with subqueries.

**Why it's fine now**: Each query is trivial and indexed. Total time is negligible.
**When it matters**: If tables grow large or metrics endpoint is called frequently.
**Fix**: Combine into one query with subselects, or cache results with a short TTL.
