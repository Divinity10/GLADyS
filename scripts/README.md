# GLADyS Admin Scripts

Unified service management for running GLADyS in local or Docker environments.

## Quick Reference

```bash
# Local development (native processes)
python scripts/local.py status
python scripts/local.py start all
python scripts/local.py stop all

# Docker environment
python scripts/docker.py status
python scripts/docker.py start all
python scripts/docker.py stop all
```

## Port Mapping

| Service | Local | Docker | Description |
|---------|-------|--------|-------------|
| Orchestrator | 50050 | 50060 | Event routing |
| MemoryStorage | 50051 | 50061 | Python storage layer |
| SalienceGateway | 50052 | 50062 | Rust salience evaluation |
| Executive | 50053 | 50063 | LLM decision making |
| PostgreSQL | 5432 | 5433 | Database |

## Commands

Both `local.py` and `docker.py` support:

| Command | Usage | Description |
|---------|-------|-------------|
| `status` | `status` | Show all service status |
| `health` | `health [service] [-d]` | Check gRPC health endpoints |
| `start` | `start <service/all>` | Start services |
| `stop` | `stop <service/all>` | Stop services |
| `restart` | `restart <service/all>` | Restart services |
| `logs` | `logs <service> [-f]` | View/follow logs |
| `migrate` | `migrate` | Run database migrations |
| `cache` | `cache stats/list/flush/evict` | Manage Rust cache |
| `sql` | `sql "SELECT ..."` | Run SQL query |
| `psql` | `psql` | Open psql shell |
| `test` | `test [file]` | Run integration tests |
| `clean-db` | `clean-db all/heuristics/events` | Clear database |

## Service Names

- `all` - All services
- `memory` - memory-python + memory-rust
- `memory-python` - MemoryStorage only
- `memory-rust` - SalienceGateway only
- `orchestrator` - Orchestrator
- `executive-stub` - Executive stub (Python)

## Files

| File | Purpose |
|------|---------|
| `local.py` | CLI for local development |
| `docker.py` | CLI for Docker environment |
| `proto_gen.py` | Generate proto stubs from `proto/` |
| `_service_base.py` | Framework: ServiceManager, ServiceBackend |
| `_local_backend.py` | Local process management |
| `_docker_backend.py` | Docker Compose integration |
| `_cache_client.py` | gRPC client for cache management |
| `_health_client.py` | gRPC client for health checks |
| `_db.py` | Centralized DB queries (events, heuristics, fires, metrics) |
| `_orchestrator.py` | Orchestrator gRPC client (queue, events) |
| `_gladys.py` | Shared config (ports, utilities) |
| `verify_env.py` | Environment verification |
| `verify_local.py` | Local setup verification |

## Examples

```bash
# Start everything locally
python scripts/local.py start all

# Check what's running
python scripts/local.py status

# Check gRPC health endpoints
python scripts/local.py health
python scripts/local.py health -d  # detailed

# View orchestrator logs
python scripts/local.py logs orchestrator -f

# View cache stats
python scripts/local.py cache stats

# Run a SQL query
python scripts/local.py sql "SELECT COUNT(*) FROM heuristics"

# Run integration tests
python scripts/local.py test

# Stop everything
python scripts/local.py stop all
```

## Health Check

The `health` command calls gRPC health endpoints on running services:

```bash
# Check all services
python scripts/local.py health

# Check specific service
python scripts/local.py health memory-rust

# Detailed output with uptime and metrics
python scripts/local.py health -d
```

**Output:**
```
memory-python        [OK] HEALTHY      uptime=3600s
memory-rust          [OK] HEALTHY      uptime=3595s
orchestrator         [OK] HEALTHY      uptime=3590s
executive-stub       [OK] HEALTHY      uptime=3585s
```

## Proto Generation

All proto definitions live in `proto/` at the project root. After editing protos:

```bash
python scripts/proto_gen.py
```

This regenerates stubs in:
- `src/memory/python/gladys_memory/generated/`
- `src/orchestrator/gladys_orchestrator/generated/`

## Cache Management

The SalienceGateway (Rust) has an LRU cache. Manage it with:

```bash
# View cache statistics
python scripts/local.py cache stats

# List cached heuristics
python scripts/local.py cache list

# Flush entire cache
python scripts/local.py cache flush

# Evict specific heuristic
python scripts/local.py cache evict <heuristic-id>
```
