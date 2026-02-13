# GLADyS Admin Scripts

Unified service management for running GLADyS in local or Docker environments.

## Quick Reference

```bash
# Local development (native processes)
python cli/local.py status
python cli/local.py start all
python cli/local.py stop all

# Docker environment
python cli/docker.py status
python cli/docker.py start all
python cli/docker.py stop all
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
| `_cache_client.py` | Cache CLI (thin wrapper over gladys_client.cache) |
| `_health_client.py` | Health CLI (thin wrapper over gladys_client.health) |
| `_db.py` | DB CLI (thin wrapper over gladys_client.db) |
| `_orchestrator.py` | Orchestrator CLI (thin wrapper over gladys_client.orchestrator) |
| `_gladys.py` | Shared config (ports, utilities) |
| `verify_env.py` | Environment verification |
| `verify_local.py` | Local setup verification |

## Examples

```bash
# Start everything locally
python cli/local.py start all

# Check what's running
python cli/local.py status

# Check gRPC health endpoints
python cli/local.py health
python cli/local.py health -d  # detailed

# View orchestrator logs
python cli/local.py logs orchestrator -f

# View cache stats
python cli/local.py cache stats

# Run a SQL query
python cli/local.py sql "SELECT COUNT(*) FROM heuristics"

# Run integration tests
python cli/local.py test

# Stop everything
python cli/local.py stop all
```

## Health Check

The `health` command calls gRPC health endpoints on running services:

```bash
# Check all services
python cli/local.py health

# Check specific service
python cli/local.py health memory-rust

# Detailed output with uptime and metrics
python cli/local.py health -d
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
python cli/proto_gen.py
```

This regenerates stubs in:

- `src/services/memory/gladys_memory/` (memory_pb2.py, memory_pb2_grpc.py)
- `src/services/orchestrator/gladys_orchestrator/generated/`

## Cache Management

The SalienceGateway (Rust) has an LRU cache. Manage it with:

```bash
# View cache statistics
python cli/local.py cache stats

# List cached heuristics
python cli/local.py cache list

# Flush entire cache
python cli/local.py cache flush

# Evict specific heuristic
python cli/local.py cache evict <heuristic-id>
```
