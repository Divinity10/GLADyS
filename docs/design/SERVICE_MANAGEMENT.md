# Service Management

How to run GLADyS services for development and testing.

## Choose Your Development Path

| Your Setup | Recommended Mode | Script |
|------------|------------------|--------|
| Have Rust + PostgreSQL | **Local** | `python scripts/local.py` |
| Docker only | **Docker** | `python scripts/docker.py` |

**Don't have Rust installed?** Use Docker mode. It includes all dependencies.

---

## Two Ways to Run

| Mode | When to Use | Ports |
|------|-------------|-------|
| **Local** | Active development with Rust, debugging, fast iteration | 50050-50053, DB 5432 |
| **Docker** | No Rust installed, integration testing, team handoff | 50060-50063, DB 5433 |

Both modes can run **simultaneously** on different ports. This allows parallel development.

---

## Prerequisites

### Local Development
- Python 3.11+ with `uv` package manager
- Rust toolchain (for memory-rust salience gateway)
- Local PostgreSQL 17+ with pgvector extension
- Database: `gladys` with user `gladys`

### Docker Development
- Docker Desktop (includes everything else)

---

## Quick Reference

```bash
# Local development (requires Rust + PostgreSQL)
python scripts/local.py start all        # Start all services
python scripts/local.py status           # Check what's running
python scripts/local.py test <file>      # Run tests
python scripts/local.py clean heuristics # Clear learned rules
python scripts/local.py reset            # Full reset

# Docker (no Rust required)
python scripts/docker.py start all
python scripts/docker.py status
python scripts/docker.py test <file>
python scripts/docker.py clean heuristics
python scripts/docker.py reset
```

---

## First-Time Setup

### Docker (recommended for most)
```bash
python scripts/docker.py start all
# Wait ~60 seconds for containers to be healthy
python scripts/docker.py status          # All should show [OK]
```

### Local
```bash
# Ensure PostgreSQL is running with gladys database
python scripts/local.py start all
python scripts/local.py status
```

---

## After Code Changes

**Python services** auto-reload (source mounted as volumes in Docker):
```bash
# Just edit the code - changes are live immediately
```

**Rust changes** require rebuild:
```bash
cd src/integration
docker-compose build memory-rust
python scripts/docker.py restart memory
```

---

## Commands

### start

Start one or more services.

```bash
python scripts/local.py start memory      # Start memory service only
python scripts/local.py start all         # Start all services
python scripts/local.py start all --no-wait    # Start without waiting for health check
python scripts/docker.py start all --no-migrate # Skip automatic migrations
```

**Services available:**
- `memory` - Memory storage + salience gateway
- `orchestrator` - Event routing and accumulation
- `executive` - Executive stub (LLM planning)
- `all` - All of the above

**Startup order:** Services start in dependency order. The `start all` command handles this automatically.

**Automatic migrations (Docker):** The Docker script automatically runs database migrations before starting services. This ensures the schema is always up to date. Use `--no-migrate` to skip this step if needed.

### stop

Stop one or more services.

```bash
python scripts/local.py stop memory       # Stop memory service
python scripts/local.py stop all          # Stop all services
```

### restart

Stop then start services.

```bash
python scripts/local.py restart memory    # Restart memory service
python scripts/local.py restart all       # Restart all services
```

### status

Show the status of all services (process-level check).

```bash
python scripts/local.py status
python scripts/docker.py status
```

### health

Check gRPC health endpoints on running services. This calls the actual Health RPCs on each service to verify they're responding properly, not just that the process is running.

```bash
python scripts/local.py health              # Check all services
python scripts/local.py health memory-rust  # Check specific service
python scripts/local.py health -d           # Detailed output with uptime and metrics
python scripts/local.py health all --detailed
```

**Example output:**
```
memory-python        [OK] HEALTHY      uptime=3600s
memory-rust          [OK] HEALTHY      uptime=3595s
orchestrator         [OK] HEALTHY      uptime=3590s
executive-stub       [OK] HEALTHY      uptime=3585s
```

**Detailed output (`-d`):**
```
memory-python        [OK] HEALTHY      uptime=3600s
    db_connected: true
    embedding_model: sentence-transformers/all-MiniLM-L6-v2
memory-rust          [OK] HEALTHY      uptime=3595s
    cache_size: 42
    cache_capacity: 1000
    cache_hit_rate: 0.85
    total_hits: 127
    total_misses: 23
```

**Status vs Health:**
- `status` checks if the process is running (port listening, PID exists)
- `health` calls gRPC RPCs to verify the service is actually responding

**Exit codes:**
- `0` if all services are HEALTHY
- `1` if any service is UNHEALTHY, DEGRADED, or unreachable

**Example output (local):**
```
Service Status (LOCAL)
======================================================================
Service         Status     Port     PID        Description
----------------------------------------------------------------------
memory          [OK]   running    50051    12345      Memory Storage + Salience Gateway
orchestrator    [OK]   running    50050    12346      Event routing and accumulation
executive       [OK]   running    50053    12347      Executive stub (LLM planning)
======================================================================
```

**Example output (Docker):**
```
Service Status (DOCKER)
======================================================================
Service            Status               Port     Description
----------------------------------------------------------------------
memory-python      [OK] running (healthy) 50061    Memory Storage (Python)
memory-rust        [OK] running (healthy) 50062    Salience Gateway (Rust)
orchestrator       [OK] running (healthy) 50060    Event routing
executive-stub     [OK] running (healthy) 50063    Executive stub
db                 [OK] running (healthy) 5433     PostgreSQL + pgvector
======================================================================
```

### test

Run integration tests against the specified environment.

```bash
python scripts/local.py test test_td_learning.py   # Run specific test against LOCAL
python scripts/docker.py test test_td_learning.py  # Run specific test against DOCKER
python scripts/local.py test                       # Run all tests against LOCAL
python scripts/docker.py test                      # Run all tests against DOCKER
```

**Important:** Always use the wrapper scripts. Tests require environment variables that the wrappers set automatically. Running tests directly will fail.

### psql

Open an interactive PostgreSQL shell connected to the GLADyS database.

```bash
python scripts/local.py psql         # Local database (port 5432)
python scripts/docker.py psql        # Docker database (port 5433)
python scripts/docker.py psql -c "SELECT COUNT(*) FROM heuristics"  # Run single command
```

### query (Docker only)

Run a SQL query and print the result. Non-interactive alternative to `psql -c`.

```bash
python scripts/docker.py query "SELECT COUNT(*) FROM heuristics"
python scripts/docker.py query "SELECT name, confidence FROM heuristics ORDER BY confidence DESC LIMIT 5"
```

Useful for:
- Inspecting data directly
- Running ad-hoc queries
- Debugging issues

**Example session:**
```sql
gladys=# SELECT name, confidence FROM heuristics ORDER BY confidence DESC LIMIT 5;
gladys=# SELECT source, COUNT(*) FROM episodic_events GROUP BY source;
gladys=# \q
```

### migrate (Docker only)

Run database migrations to update the schema.

```bash
python scripts/docker.py migrate    # Apply all pending migrations
```

**How it works:**
- Migrations live in `src/memory/migrations/` as numbered SQL files (001_, 002_, etc.)
- Migrations are idempotent - safe to run multiple times
- "Already exists" errors are treated as success (migration was already applied)
- Each migration has a 60-second timeout to prevent hanging

**When to use:**
- After pulling new code that includes schema changes
- When setting up a fresh database
- Usually not needed - `start` runs migrations automatically

**Note:** The `start` command runs migrations automatically before starting services. You only need to run `migrate` manually for debugging or when starting services with `--no-migrate`.

### clean

Clear data from database tables. Useful for resetting state during testing or development.

```bash
python scripts/local.py clean heuristics  # Clear learned rules only
python scripts/local.py clean events      # Clear event history only
python scripts/local.py clean all         # Clear everything
```

**What gets cleaned:**

| Option | Tables Affected | Use Case |
|--------|-----------------|----------|
| `heuristics` | `heuristics` | Reset learned rules, keep event history |
| `events` | `episodic_events` | Clear event history, keep rules |
| `all` | Both tables | Full data reset |

**Note:** This uses `TRUNCATE ... CASCADE` which is fast but irreversible.

### reset

Full system reset: stops all services, clears all data, restarts services.

```bash
python scripts/local.py reset             # Full reset
python scripts/local.py reset --no-start  # Reset but don't restart
```

**What happens:**
1. All services are stopped
2. Database tables are truncated (heuristics + events)
3. All services are restarted (unless `--no-start`)

**Use cases:**
- Starting fresh for a new test session
- Recovering from corrupted state
- Preparing for a demo

### logs (Docker only)

Follow service logs in real-time.

```bash
python scripts/docker.py logs memory      # Follow memory service logs
python scripts/docker.py logs all         # Follow all service logs
```

Press `Ctrl+C` to stop following.

---

## Port Assignments

Local and Docker use **different ports** so both can run simultaneously:

| Service | Local Port | Docker Port | Protocol |
|---------|------------|-------------|----------|
| Orchestrator | 50050 | 50060 | gRPC |
| Memory (Python) | 50051 | 50061 | gRPC |
| Memory (Rust) | 50052 | 50062 | gRPC |
| Executive | 50053 | 50063 | gRPC |
| PostgreSQL | 5432 | 5433 | PostgreSQL |

**Why different ports?** This allows parallel development - you can run both local and Docker services at the same time without conflicts.

---

## Troubleshooting

### Service won't start

1. Check if port is already in use:
   ```bash
   python scripts/local.py status
   ```

2. Kill any zombie processes:
   ```bash
   python scripts/local.py stop all
   ```

3. Check for error messages in the service startup.

### Database connection errors

1. Verify PostgreSQL is running:
   ```bash
   # Local
   psql -h localhost -U gladys -d gladys -c "SELECT 1"

   # Docker
   docker exec gladys-integration-db psql -U gladys -d gladys -c "SELECT 1"
   ```

2. Check `pg_hba.conf` allows connections (local development).

### Migration hangs or times out

1. Check for stuck database connections:
   ```bash
   python scripts/docker.py psql
   ```
   ```sql
   SELECT pid, state, query FROM pg_stat_activity WHERE datname = 'gladys';
   ```

2. If you see connections in "idle in transaction" state, terminate them:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE datname = 'gladys' AND state = 'idle in transaction';
   ```

3. Retry the migration:
   ```bash
   python scripts/docker.py migrate
   ```

### Services show running but not responding

1. Check if the port is actually accepting connections:
   ```bash
   # Windows
   netstat -ano | findstr :50051

   # Linux/Mac
   lsof -i :50051
   ```

2. Restart the specific service:
   ```bash
   python scripts/local.py restart memory
   ```

### Need to see what's in the database

```bash
python scripts/local.py psql
# or
python scripts/docker.py psql
```

Then run queries:
```sql
-- See all heuristics
SELECT id, name, confidence, fire_count, origin FROM heuristics;

-- See recent events
SELECT id, source, raw_text, predicted_success FROM episodic_events
ORDER BY timestamp DESC LIMIT 10;

-- Count events by source
SELECT source, COUNT(*) FROM episodic_events GROUP BY source;

-- See events with responses (for fine-tuning validation)
SELECT id, raw_text, response_text, predicted_success
FROM episodic_events
WHERE response_text IS NOT NULL
ORDER BY timestamp DESC LIMIT 5;
```

---

## Environment Variables

### Local Development

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://gladys@localhost/gladys` | PostgreSQL connection |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama LLM endpoint |
| `CACHE_HEURISTIC_TTL_MS` | `5000` | Heuristic cache TTL in milliseconds |

### Docker

Environment variables are set in `src/integration/docker-compose.yml`.

---

## For Support

When helping users troubleshoot:

1. **Get status first:**
   ```bash
   python scripts/local.py status
   # or
   python scripts/docker.py status
   ```

2. **Check database connectivity:**
   ```bash
   python scripts/local.py psql
   # Then: SELECT 1;
   ```

3. **Check for data issues:**
   ```sql
   SELECT COUNT(*) FROM heuristics;
   SELECT COUNT(*) FROM episodic_events;
   ```

4. **If all else fails, reset:**
   ```bash
   python scripts/local.py reset
   ```

---

## For Developers

### Adding a new service

1. Add entry to `SERVICES` dict in `scripts/local.py`:
   ```python
   SERVICES = {
       # ... existing services ...
       "new_service": {
           "port": LOCAL_PORTS.new_service,
           "cwd": ROOT / "src" / "new_service",
           "cmd": ["uv", "run", "python", "server.py"],
           "description": "New service description",
       },
   }
   ```

2. Add port to `scripts/_gladys.py` PortConfig.

3. Add corresponding entry in `scripts/docker.py` for Docker.

4. Update `src/integration/docker-compose.yml` if needed.

### Running services manually (debugging)

Sometimes you want to run a service in the foreground to see output:

```bash
# Memory service
cd src/memory/python
uv run python -m gladys_memory.grpc_server

# Executive stub
cd src/executive
uv run python stub_server.py
```
