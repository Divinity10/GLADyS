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
- [proto/memory.proto](../proto/memory.proto) - API contract
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
- [proto/orchestrator.proto](../proto/orchestrator.proto) - API contract
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
- `ProcessEvent` RPC - handles events requiring LLM reasoning
- Optional Ollama LLM integration (set `OLLAMA_URL` env var)
- `ProvideFeedback` RPC - pattern extraction for heuristic formation

**Key files:**
- [src/executive/gladys_executive/server.py](../src/executive/gladys_executive/server.py) - Python stub implementation
- [proto/executive.proto](../proto/executive.proto) - API contract

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

After modifying `.proto` files in `proto/`:

```bash
python scripts/proto_gen.py   # Regenerates all Python stubs
```

This script:
- Regenerates Python stubs from `proto/` to service-specific `generated/` directories
- Fixes relative imports in generated files
- Validates syntax of generated Python files

### Service Management

For service ports, see **[CODEBASE_MAP.md](../CODEBASE_MAP.md#service-ports)**.

Quick start:
```bash
# Docker (recommended - no Rust required)
python scripts/docker.py start all
python scripts/docker.py status

# Local (requires Rust + PostgreSQL)
python scripts/local.py start all
python scripts/local.py status
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

GLADyS uses **semantic similarity** for heuristic matching via pgvector embeddings.

**How it works:**
- Heuristic conditions are stored with embeddings (384-dim, all-MiniLM-L6-v2)
- Event text is embedded and compared via cosine similarity
- Threshold of 0.7 ensures semantic meaning matches (not just shared words)

**Example:**
- "User wants ice cream" **matches** "User wants frozen dessert" (0.78 similarity)
- "email about killing neighbor" does **NOT** match "email about meeting" (0.69 similarity)

**Architecture:**
- **Rust fast path** delegates to Python for semantic matching
- **Python storage** handles embedding generation and similarity search
- **LRU cache** in Rust stores recently-used heuristics for stats

**Key config:**
```bash
# Similarity threshold (default: 0.7)
export CACHE_NOVELTY_THRESHOLD=0.7

# Minimum heuristic confidence to consider (default: 0.5)
export SALIENCE_MIN_HEURISTIC_CONFIDENCE=0.5
```

## Where to Find Things

| What | Where |
|------|-------|
| Architecture decisions | [docs/adr/](adr/) |
| Open design questions | [docs/design/questions/](design/questions/README.md) |
| Service ports & layout | [CODEBASE_MAP.md](../CODEBASE_MAP.md) |
| Memory subsystem | [src/memory/](../src/memory/) |
| Orchestrator subsystem | [src/orchestrator/](../src/orchestrator/) |
| Executive stub | [src/executive/](../src/executive/) |
| Integration tests | [src/integration/](../src/integration/) |
| gRPC contracts | [proto/](../proto/) |
| Makefile targets | `make help` |
| Proto generation script | [scripts/proto_gen.py](../scripts/proto_gen.py) |

## Getting Help

- Check existing ADRs for design rationale
- Look at [design questions](design/questions/) for active discussions
- Open an issue if stuck
