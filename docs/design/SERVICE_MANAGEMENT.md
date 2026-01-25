# Service Management

GLADyS provides two service management scripts with identical interfaces:

| Environment | Script | When to Use |
|-------------|--------|-------------|
| **Local** | `scripts/services.py` | Development on your machine |
| **Docker** | `src/integration/run.py` | Integration testing, CI/CD, team development |

Both scripts use `uv run python <script>` or just `python <script>` if dependencies are installed.

---

## Quick Reference

```bash
# Local development
python scripts/services.py start all        # Start all services
python scripts/services.py status           # Check what's running
python scripts/services.py clean heuristics # Clear learned rules
python scripts/services.py reset            # Full reset

# Docker (integration testing)
cd src/integration
python run.py start all
python run.py status
python run.py clean heuristics
python run.py reset
```

---

## Commands

### start

Start one or more services.

```bash
python scripts/services.py start memory      # Start memory service only
python scripts/services.py start all         # Start all services
python scripts/services.py start all --no-wait  # Start without waiting for health check
```

**Services available:**
- `memory` - Memory storage + salience gateway
- `orchestrator` - Event routing and accumulation
- `executive` - Executive stub (LLM planning)
- `all` - All of the above

**Startup order:** Services start in dependency order. The `start all` command handles this automatically.

### stop

Stop one or more services.

```bash
python scripts/services.py stop memory       # Stop memory service
python scripts/services.py stop all          # Stop all services
```

### restart

Stop then start services.

```bash
python scripts/services.py restart memory    # Restart memory service
python scripts/services.py restart all       # Restart all services
```

### status

Show the status of all services.

```bash
python scripts/services.py status
```

**Example output (local):**
```
Service Status
============================================================
Service         Status     Port     PID        Description
------------------------------------------------------------
memory          [OK]   running    50051    12345      Memory Storage + Salience Gateway
orchestrator    [OK]   running    50052    12346      Event routing and accumulation
executive       [OK]   running    50053    12347      Executive stub (LLM planning)
============================================================
```

**Example output (Docker):**
```
Service Status (Docker)
======================================================================
Service            Status               Port     Description
----------------------------------------------------------------------
memory-python      [OK] running (healthy) 50051    Memory Storage (Python)
memory-rust        [OK] running (healthy) 50052    Salience Gateway (Rust)
orchestrator       [OK] running (healthy) 50050    Event routing
executive-stub     [OK] running (healthy) 50053    Executive stub
db                 [OK] running (healthy) 5433     PostgreSQL + pgvector
======================================================================
```

### psql

Open an interactive PostgreSQL shell connected to the GLADyS database.

```bash
python scripts/services.py psql
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

### clean

Clear data from database tables. Useful for resetting state during testing or development.

```bash
python scripts/services.py clean heuristics  # Clear learned rules only
python scripts/services.py clean events      # Clear event history only
python scripts/services.py clean all         # Clear everything
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
python scripts/services.py reset             # Full reset
python scripts/services.py reset --no-start  # Reset but don't restart
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
cd src/integration
python run.py logs memory      # Follow memory service logs
python run.py logs all         # Follow all service logs
```

Press `Ctrl+C` to stop following.

---

## Port Assignments

| Service | Local Port | Docker Port | Protocol |
|---------|------------|-------------|----------|
| Memory (Python) | 50051 | 50051 | gRPC |
| Memory (Rust) | - | 50052 | gRPC |
| Orchestrator | 50052 | 50050 | gRPC |
| Executive | 50053 | 50053 | gRPC |
| PostgreSQL | 5432 | 5433 | PostgreSQL |

**Note:** Docker uses port 5433 for PostgreSQL to avoid conflicts with local PostgreSQL on 5432.

---

## Troubleshooting

### Service won't start

1. Check if port is already in use:
   ```bash
   python scripts/services.py status
   ```

2. Kill any zombie processes:
   ```bash
   python scripts/services.py stop all
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
   python scripts/services.py restart memory
   ```

### Need to see what's in the database

```bash
python scripts/services.py psql
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
   python scripts/services.py status
   ```

2. **Check database connectivity:**
   ```bash
   python scripts/services.py psql
   # Then: SELECT 1;
   ```

3. **Check for data issues:**
   ```sql
   SELECT COUNT(*) FROM heuristics;
   SELECT COUNT(*) FROM episodic_events;
   ```

4. **If all else fails, reset:**
   ```bash
   python scripts/services.py reset
   ```

---

## For Developers

### Adding a new service

1. Add entry to `SERVICES` dict in `scripts/services.py`:
   ```python
   SERVICES = {
       # ... existing services ...
       "new_service": {
           "port": 50054,
           "cwd": ROOT / "src" / "new_service",
           "cmd": ["uv", "run", "python", "server.py"],
           "description": "New service description",
       },
   }
   ```

2. Add corresponding entry in `src/integration/run.py` for Docker.

3. Update `docker-compose.yml` if needed.

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
