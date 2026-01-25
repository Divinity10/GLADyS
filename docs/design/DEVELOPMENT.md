# Development Guide

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

## Local Development

Run services as local Python/Rust processes. Best for:
- Debugging with IDE breakpoints
- Fast code-reload cycles
- Working on a single service

### Prerequisites

- Python 3.11+ with `uv` package manager
- Rust toolchain (for memory-rust salience gateway)
- Local PostgreSQL 17+ with pgvector extension
- Database: `gladys` with user `gladys`

### Commands

```bash
# From project root
python scripts/local.py start all       # Start all services
python scripts/local.py start memory    # Start just memory
python scripts/local.py stop all        # Stop all services
python scripts/local.py restart memory  # Restart memory
python scripts/local.py status          # Show status
python scripts/local.py test <test.py>  # Run test against local
python scripts/local.py psql            # Database shell
python scripts/local.py clean all       # Clear test data
```

### Service Ports (Local)

| Service | Port | Description |
|---------|------|-------------|
| orchestrator | 50050 | Event routing and accumulation |
| memory | 50051 | Memory Storage (Python) |
| memory-rust | 50052 | Salience Gateway (Rust fast path) |
| executive | 50053 | Executive stub (LLM planning) |
| PostgreSQL | 5432 | Database |

### Manual Startup (Alternative)

For more control, run each service in its own terminal:

```bash
# Terminal 1 - Python Memory storage
cd src/memory/python && uv run python -m gladys_memory.grpc_server

# Terminal 2 - Rust salience fast path
cd src/memory/rust && cargo run

# Terminal 3 - Orchestrator
cd src/orchestrator && uv run python run.py start

# Terminal 4 - Executive stub
cd src/executive && uv run python stub_server.py
```

---

## Docker Development

Run services in Docker containers. Best for:
- Developers without Rust installed
- Integration testing across all services
- Consistent environment for team members
- Testing before commits

### Prerequisites

- Docker Desktop (includes everything else)

### Commands

```bash
# From project root
python scripts/docker.py start all       # Start all services
python scripts/docker.py start memory    # Start memory services (Python + Rust)
python scripts/docker.py stop all        # Stop all services
python scripts/docker.py restart memory  # Restart memory services
python scripts/docker.py status          # Show container status
python scripts/docker.py logs memory     # Follow memory logs
python scripts/docker.py test <test.py>  # Run test against Docker
python scripts/docker.py psql            # Open database shell
python scripts/docker.py clean all       # Delete test data
```

### Service Ports (Docker)

Docker uses **offset ports** to avoid conflicts with local development:

| Service | Port | Docker Container |
|---------|------|------------------|
| orchestrator | 50060 | gladys-integration-orchestrator |
| memory-python | 50061 | gladys-integration-memory-python |
| memory-rust | 50062 | gladys-integration-memory-rust |
| executive | 50063 | gladys-integration-executive-stub |
| PostgreSQL | 5433 | gladys-integration-db |

### First-Time Setup

```bash
python scripts/docker.py start all
# Wait ~60 seconds for containers to be healthy
python scripts/docker.py status          # All should show [OK]
```

### After Code Changes

Python services auto-reload (source mounted as volumes). For Rust:

```bash
cd src/integration
docker-compose build memory-rust
python scripts/docker.py restart memory
```

---

## Running Tests

**Always use the wrapper scripts.** Tests require environment variables that the wrappers set automatically.

```bash
# Run specific test against Local
python scripts/local.py test test_td_learning.py

# Run specific test against Docker
python scripts/docker.py test test_td_learning.py

# Run all tests
python scripts/local.py test
python scripts/docker.py test
```

Tests will **fail** if run directly without the wrapper (prevents wrong-environment testing).

---

## Troubleshooting

### Port Already in Use

```bash
# Check what's using a port
netstat -ano | findstr :50051    # Windows
lsof -i :50051                   # Mac/Linux

# Kill process by PID
taskkill /PID <pid> /F           # Windows
kill -9 <pid>                    # Mac/Linux
```

### Container Won't Start

```bash
python scripts/docker.py logs memory    # Check logs
cd src/integration
docker-compose build --no-cache memory-python  # Rebuild image
```

### Database Issues

```bash
python scripts/docker.py psql           # Open database shell

# Reset database completely (WARNING: Deletes all data)
cd src/integration
docker-compose down -v
python scripts/docker.py start all
```

### Proto Sync Issues

After changing `.proto` files:

```bash
make proto                      # Regenerate all stubs
```

---

## Environment Variables

### Local Development

Create `.env` in project root (template at `.env.example`):

```bash
# PostgreSQL connection
STORAGE_HOST=localhost
STORAGE_PORT=5432
STORAGE_USER=gladys
STORAGE_PASSWORD=gladys_dev
STORAGE_DATABASE=gladys

# Optional: Ollama LLM
OLLAMA_URL=http://100.120.203.91:11435
OLLAMA_MODEL=qwen3-vl:8b
```

### Docker Development

Environment is configured in `src/integration/docker-compose.yml`. Override with:

```bash
OLLAMA_URL=http://host.docker.internal:11434 docker-compose up -d
```

---

## Quick Reference

| Task | Local | Docker |
|------|-------|--------|
| Start all | `python scripts/local.py start all` | `python scripts/docker.py start all` |
| Restart memory | `python scripts/local.py restart memory` | `python scripts/docker.py restart memory` |
| Check status | `python scripts/local.py status` | `python scripts/docker.py status` |
| Run tests | `python scripts/local.py test <file>` | `python scripts/docker.py test <file>` |
| View logs | (run in foreground) | `python scripts/docker.py logs memory` |
| Database shell | `python scripts/local.py psql` | `python scripts/docker.py psql` |
| Clean data | `python scripts/local.py clean all` | `python scripts/docker.py clean all` |
