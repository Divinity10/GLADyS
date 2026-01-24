# Development Guide

How to run GLADyS services for development and testing.

## Two Ways to Run

| Mode | When to Use | Script |
|------|-------------|--------|
| **Local** | Active development, debugging, fast iteration | `python scripts/services.py` |
| **Docker** | Integration testing, team handoff, CI/CD | `python src/integration/run.py` |

---

## Local Development

Run services as local Python/Rust processes. Best for:
- Debugging with IDE breakpoints
- Fast code-reload cycles
- Working on a single service

### Prerequisites

- Python 3.11+ with `uv` package manager
- Rust toolchain (for memory-rust)
- Local PostgreSQL 17+ with pgvector extension

### Commands

```bash
# From project root
python scripts/services.py start all       # Start all services
python scripts/services.py start memory    # Start just memory
python scripts/services.py stop all        # Stop all services
python scripts/services.py restart memory  # Restart memory
python scripts/services.py status          # Show status
```

### Available Services

| Service | Port | Description |
|---------|------|-------------|
| memory | 50051 | Memory Storage + Salience Gateway |
| orchestrator | 50052 | Event routing and accumulation |
| executive | 50053 | Executive stub (LLM planning) |

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
- Integration testing across all services
- Consistent environment for team members
- Testing before commits

### Prerequisites

- Docker Desktop

### Commands

```bash
# From src/integration directory
python run.py start all       # Start all services
python run.py start memory    # Start memory services (Python + Rust)
python run.py stop all        # Stop all services
python run.py restart memory  # Restart memory services
python run.py status          # Show container status
python run.py logs memory     # Follow memory logs
python run.py psql            # Open database shell
python run.py clean-test      # Delete test data
```

### Available Services

| Service | Port | Docker Container |
|---------|------|------------------|
| memory | 50051, 50052 | gladys-integration-memory-python, gladys-integration-memory-rust |
| orchestrator | 50050 | gladys-integration-orchestrator |
| executive | 50053 | gladys-integration-executive-stub |
| db | 5433 | gladys-integration-db |

### First-Time Setup

```bash
cd src/integration
python run.py start all
# Wait ~60 seconds for containers to be healthy
python run.py status          # All should show [OK]
```

### After Code Changes

Python services auto-reload (source mounted as volumes). For Rust:

```bash
cd src/integration
docker-compose build memory-rust
python run.py restart memory
```

### Running Tests

```bash
# Killer feature test
cd src/memory/python
PYTHON_ADDRESS=localhost:50051 RUST_ADDRESS=localhost:50052 \
  uv run python ../../integration/test_killer_feature.py
```

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
cd src/integration
python run.py logs memory       # Check logs
docker-compose build --no-cache memory-python  # Rebuild image
```

### Database Issues

```bash
cd src/integration
python run.py psql              # Open database shell

# Reset database completely
docker-compose down -v          # WARNING: Deletes all data
python run.py start all
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
| Start all | `python scripts/services.py start all` | `python run.py start all` |
| Restart memory | `python scripts/services.py restart memory` | `python run.py restart memory` |
| Check status | `python scripts/services.py status` | `python run.py status` |
| View logs | (run in foreground) | `python run.py logs memory` |
| Database shell | `psql -U gladys -d gladys` | `python run.py psql` |
