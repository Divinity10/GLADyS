# Getting Started with GLADyS Development

You're a contributor. Here's how to get productive.

## Contents

- [Prerequisites](#prerequisites-everyone)
- [Architecture Overview](#architecture-overview)
- [Pick Your Area](#pick-your-area)
  - [Memory](#i-want-to-work-on-memory)
  - [Orchestrator](#i-want-to-work-on-orchestrator)
  - [Executive](#i-want-to-work-on-executive)
  - [Sensors](#i-want-to-build-a-sensor)
  - [Skills/Actuators](#i-want-to-build-a-skillactuator)
- [Common Tasks](#common-tasks)
  - [Running the full stack](#running-the-full-stack)
  - [Development workflow](#development-workflow)
  - [Service Ports](#service-ports)
  - [Configuration](#configuration)
  - [Running locally](#running-services-locally-outside-docker)
  - [Connecting to services](#connecting-to-running-services)
- [Technical Notes: Heuristic Matching](#technical-notes-heuristic-matching)
- [Where to Find Things](#where-to-find-things)

## Prerequisites (Everyone)

- **Git**: You have this if you're reading this
- **Docker Desktop**: [Install here](https://www.docker.com/products/docker-desktop/) - runs dependencies without local installs

## Choose Your Path

| Your Setup | Use This |
|------------|----------|
| **Docker only** (recommended for most) | `python scripts/docker.py` |
| **Rust + PostgreSQL installed** | `python scripts/local.py` |

**Don't have Rust?** That's fine - Docker mode includes everything.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Sensors                                  │
│        (Discord, Minecraft, Home Assistant, etc.)               │
└─────────────────────────────┬───────────────────────────────────┘
                              │ events
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Orchestrator                               │
│  • Routes events          • Manages attention (salience)        │
│  • Coordinates subsystems • Calls LLM when needed               │
└───────────┬─────────────────────────────────┬───────────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────────────┐
│        Memory         │         │          Executive            │
│  • Store/recall       │         │  • User interaction           │
│  • Semantic search    │         │  • Decision execution         │
│  • Learned heuristics │         │  • Skill invocation           │
└───────────────────────┘         └───────────────────────────────┘
```

Everything communicates via **gRPC**. Each subsystem runs as a separate service.

## Pick Your Area

### "I want to work on Memory"

The storage and retrieval layer. Rust fast path + Python ML/storage.

**Easiest: Use the full stack (recommended)**
```bash
make up   # Starts everything including Memory
# Edit Python code - changes auto-reload (volume mounted)
# Edit Rust code - run `make rust-rebuild`
```

**Local setup (for isolated development):**
```bash
cd src/memory
docker compose up -d postgres    # Just the database
cd python && uv sync             # Python dependencies
cd ../rust && cargo build        # Rust dependencies
```

**Run tests:**
```bash
cd src/memory/python && uv run pytest
cd src/memory/rust && cargo test
```

**Key files:**
- [src/memory/python/gladys_memory/grpc_server.py](../src/memory/python/gladys_memory/grpc_server.py) - Python gRPC server
- [src/memory/rust/src/server.rs](../src/memory/rust/src/server.rs) - Rust fast path
- [src/memory/proto/memory.proto](../src/memory/proto/memory.proto) - API contract
- [src/memory/python/gladys_memory/config.py](../src/memory/python/gladys_memory/config.py) - Configuration

---

### "I want to work on Orchestrator"

The brain. Routes events, manages attention, coordinates everything. Python + gRPC.

**Easiest: Use the full stack (recommended)**
```bash
make up   # Starts everything including Orchestrator
# Edit code - changes auto-reload (volume mounted)
```

**Local setup (for isolated development):**
```bash
# Start Memory first (dependency)
python scripts/local.py start memory

# Or start everything
python scripts/local.py start all
```

**You need:** Python 3.11+, uv

**Run tests:**
```bash
cd src/orchestrator && uv run pytest
```

**Key files:**
- [src/orchestrator/gladys_orchestrator/router.py](../src/orchestrator/gladys_orchestrator/router.py) - Event routing logic
- [src/orchestrator/gladys_orchestrator/server.py](../src/orchestrator/gladys_orchestrator/server.py) - gRPC server
- [src/orchestrator/proto/orchestrator.proto](../src/orchestrator/proto/orchestrator.proto) - API contract
- [scripts/local.py](../scripts/local.py) - Local service management
- [scripts/docker.py](../scripts/docker.py) - Docker service management

**Key ADRs:**
- [ADR-0001](adr/ADR-0001-Architecture-and-Component-Design.md) - Overall architecture
- [ADR-0013](adr/ADR-0013-Salience-Engine-and-Attention-Management.md) - Attention/salience

---

### "I want to work on Executive"

User-facing decision layer. Production will be C#/.NET, but we have a Python stub for PoC.

**Current state:** Python stub exists at `src/executive/stub_server.py`

**Local setup (using the stub):**
```bash
make up   # Starts all services including executive-stub
```

**Features:**
- `ProcessMoment` RPC - handles accumulated events
- Optional Ollama LLM integration (set `OLLAMA_URL` env var)
- `ProvideFeedback` RPC - pattern extraction for heuristic formation
- File-based heuristic storage (PoC only)

**Key files:**
- [src/executive/stub_server.py](../src/executive/stub_server.py) - Python stub implementation
- [src/orchestrator/proto/executive.proto](../src/orchestrator/proto/executive.proto) - API contract

**Key ADRs:**
- [ADR-0014](adr/ADR-0014-Executive-Decision-Loop-and-Proactive-Behavior.md) - Executive design

---

### "I want to build a Sensor"

Sensors bring data into GLADyS (Discord messages, game state, temperature readings, etc.)

**Local setup:**
```bash
# Start Orchestrator (dependency - when it exists)
# Then build your sensor in whatever language
```

**Key ADRs:**
- [ADR-0003](adr/ADR-0003-Plugin-Architecture.md) - Plugin/sensor architecture

---

### "I want to build a Skill/Actuator"

Skills/actuators let GLADyS take actions (send messages, control devices, etc.)

**Key ADRs:**
- [ADR-0003](adr/ADR-0003-Plugin-Architecture.md) - Plugin architecture
- [ADR-0011](adr/ADR-0011-Actuator-Subsystem.md) - Actuator design

---

## Common Tasks

  - [Running the full stack](#running-the-full-stack)
  - [Running the Evaluation Lab Bench](#running-the-evaluation-lab-bench)
  - [Development workflow](#development-workflow)

# ... (middle of file) ...

### Running the full stack

Use the Makefile (recommended):

```bash
make up          # Start all services (postgres, memory, rust, orchestrator, executive)
make down        # Stop all services
make restart     # Restart services
make benchmark   # Run performance benchmark
```

Or manually:

```bash
cd src/integration
docker compose up -d    # Starts all 5 services
docker compose ps       # Check status
docker compose logs -f  # Follow logs
```

### Running the Evaluation Lab Bench

The Lab Bench is a Streamlit dashboard for real-time testing of the learning loop.

```bash
cd src/ui
uv run streamlit run dashboard.py
```

See the [Lab Bench User Guide](../src/ui/USER_GUIDE.md) for details on event simulation, memory probing, and salience overrides.

### Development workflow

**Python changes** auto-reload (source mounted as volumes):
```bash
# Just edit the code - changes are live immediately
```

**Rust changes** require rebuild:
```bash
make rust-rebuild   # Rebuild only the Rust container
```

### Checking what's running

```bash
docker ps                        # All running containers
docker compose -f src/integration/docker-compose.yml ps   # GLADyS services
```

### Viewing logs

```bash
docker compose -f src/integration/docker-compose.yml logs -f           # All services
docker compose -f src/integration/docker-compose.yml logs memory-python  # Specific service
```

### Regenerating proto stubs

After modifying `.proto` files:

```bash
make proto   # Regenerates all Python stubs, fixes imports, validates Rust compiles
```

This uses `scripts/proto_sync.py` which:
- Regenerates Python stubs for memory and orchestrator
- Fixes relative imports in generated files
- Validates Rust compilation against proto changes

### Service Ports

Local and Docker use **different ports** to allow parallel development:

| Service | Local | Docker | Description |
|---------|-------|--------|-------------|
| Orchestrator | 50050 | 50060 | Main entry point - send events here |
| Memory (Python) | 50051 | 50061 | Storage + SalienceGateway (slow path) |
| Memory (Rust) | 50052 | 50062 | SalienceGateway only (fast path) |
| Executive | 50053 | 50063 | Decision-making + LLM |
| PostgreSQL | 5432 | 5433 | Database |

**Default flow**: Orchestrator → Rust fast path → Executive

### Configuration

**Environment variables** (set before `make up` or in shell):

```bash
# Switch Orchestrator to use Python path instead of Rust
export SALIENCE_MEMORY_ADDRESS=memory-python:50051

# Enable LLM in Executive (point to your Ollama server)
export OLLAMA_URL=http://192.168.1.100:11434
export OLLAMA_MODEL=gemma:2b
```

**Memory (Python) settings** - see `src/memory/python/gladys_memory/config.py`:

```bash
# Database
export STORAGE_HOST=localhost
export STORAGE_PORT=5433

# Salience tuning
export SALIENCE_NOVELTY_SIMILARITY_THRESHOLD=0.85
export SALIENCE_WORD_OVERLAP_MIN=2

# Server
export GRPC_PORT=50051
```

**Rust fast path** uses identical env vars - see `src/memory/rust/src/config.rs`.

### Running services locally (outside Docker)

For development, you can run individual services locally:

**All services (recommended):**
```bash
# Docker (no Rust required)
python scripts/docker.py start all
python scripts/docker.py status

# Local (requires Rust + PostgreSQL)
python scripts/local.py start all
python scripts/local.py status
```

**Individual service (for debugging):**
```bash
cd src/orchestrator
uv run python run.py start --salience-address localhost:50051
```

**Memory (Python):**
```bash
cd src/memory/python
uv run python -m gladys_memory.grpc_server
```

**Memory (Rust):**
```bash
cd src/memory/rust
STORAGE_ADDRESS=http://localhost:50051 cargo run
```

### Connecting to running services

**Python client example:**
```python
import grpc
from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc

channel = grpc.insecure_channel('localhost:50050')
stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

# Send an event
response = stub.IngestEvent(orchestrator_pb2.IngestEventRequest(
    event=orchestrator_pb2.Event(
        id="test-1",
        source="my-sensor",
        raw_text="Something happened",
    )
))
```

**grpcurl (CLI testing):**
```bash
# List services
grpcurl -plaintext localhost:50050 list

# Call a method
grpcurl -plaintext -d '{"event": {"id": "1", "source": "test", "raw_text": "hello"}}' \
  localhost:50050 gladys.orchestrator.OrchestratorService/IngestEvent
```

## Technical Notes: Heuristic Matching

**Why do we have two matching approaches?**

GLADyS has two paths for salience evaluation:

| Path | Language | Matching Method | Use Case |
|------|----------|-----------------|----------|
| **Slow path** | Python | Embedding similarity (pgvector) | Semantic matching, production quality |
| **Fast path** | Rust | Word overlap | Low-latency MVP, no embedding model |

**Embedding similarity (pgvector)** compares the *meaning* of text:
- "DANGER! Hostile approaching!" matches "threat detected" because they're semantically similar
- Handles synonyms, paraphrasing, different word forms
- Requires an embedding model (Python has access to this)

**Word overlap (Rust MVP)** does literal keyword matching:
- "DANGER! Hostile approaching!" matches if heuristic contains words like "danger", "hostile"
- Case-insensitive, strips punctuation
- Fast but brittle - misses semantic relationships

**Why does Rust use word overlap?**

The Rust fast path is optimized for sub-millisecond latency. Loading an embedding model into Rust would add startup time and memory overhead. The word-overlap approach is a placeholder that:

1. Demonstrates the fast-path architecture
2. Works for explicit keyword triggers
3. Will be replaced when we add embedding support

**Configuration for word matching:**

```bash
# Minimum word overlap count (default: 2)
export SALIENCE_MIN_WORD_OVERLAP=2

# Minimum overlap ratio (default: 0.3 = 30% of condition words must match)
export SALIENCE_WORD_OVERLAP_RATIO=0.3
```

**Production roadmap:**
- Short term: Word overlap for explicit triggers
- Medium term: Rust calls Python for embeddings when needed
- Long term: Rust-native embedding model (ONNX runtime)

## Where to Find Things

| What | Where |
|------|-------|
| Architecture decisions | [docs/adr/](adr/) |
| Open design questions | [docs/design/OPEN_QUESTIONS.md](design/OPEN_QUESTIONS.md) |
| Performance baseline | [docs/design/PERFORMANCE_BASELINE.md](design/PERFORMANCE_BASELINE.md) |
| Memory subsystem | [src/memory/](../src/memory/) |
| Orchestrator subsystem | [src/orchestrator/](../src/orchestrator/) |
| Executive stub | [src/executive/](../src/executive/) |
| Integration tests | [src/integration/](../src/integration/) |
| gRPC contracts | `src/*/proto/*.proto` |
| Makefile targets | `make help` |
| Proto sync script | [scripts/proto_sync.py](../scripts/proto_sync.py) |

## Getting Help

- Check existing ADRs for design rationale
- Look at OPEN_QUESTIONS.md for active discussions
- Open an issue if stuck
