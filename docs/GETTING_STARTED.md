# Getting Started with GLADyS Development

You're a contributor. Here's how to get productive.

## Prerequisites (Everyone)

- **Git**: You have this if you're reading this
- **Docker Desktop**: [Install here](https://www.docker.com/products/docker-desktop/) - runs dependencies without local installs

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

**Local setup:**
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
- [src/memory/README.md](../src/memory/README.md) - Full details
- [src/memory/proto/memory.proto](../src/memory/proto/memory.proto) - API contract

---

### "I want to work on Orchestrator"

The brain. Routes events, manages attention, coordinates everything. Python + gRPC.

**Local setup:**
```bash
# Start Memory (dependency)
cd src/memory && python run.py start

# Then work on Orchestrator
cd src/orchestrator
uv sync              # Python dependencies
uv run python run.py # Run the server
```

**You need:** Python 3.11+, uv

**Run tests:**
```bash
cd src/orchestrator && uv run pytest
```

**Key files:**
- [src/orchestrator/README.md](../src/orchestrator/README.md) - Full details
- [src/orchestrator/proto/orchestrator.proto](../src/orchestrator/proto/orchestrator.proto) - API contract

**Key ADRs:**
- [ADR-0001](adr/ADR-0001-Architecture-and-Component-Design.md) - Overall architecture
- [ADR-0013](adr/ADR-0013-Salience-Engine-and-Attention-Management.md) - Attention/salience

---

### "I want to work on Executive"

User-facing decision layer. C#/.NET.

**Local setup:**
```bash
# Start dependencies
cd src/memory && python run.py start
# (Eventually: start Orchestrator too)

# Then work on Executive
cd src/executive    # (doesn't exist yet)
dotnet build
```

**You need:** .NET SDK

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

### Running the full stack (integration test)

```bash
cd src/integration
docker compose up -d    # Starts PostgreSQL, Memory (Python + Rust), Orchestrator
docker compose ps       # Check status
docker compose logs -f  # Follow logs
```

### Running individual subsystems

```bash
# Memory only
cd src/memory && python run.py start

# Orchestrator (requires Memory)
cd src/orchestrator && uv run python run.py
```

### Checking what's running

```bash
docker ps    # Shows all running containers
```

### Viewing logs

```bash
cd src/memory && python run.py logs    # Memory logs
# Or: docker compose logs -f
```

### Resetting a subsystem

```bash
cd src/memory && python run.py reset   # Deletes all data, fresh start
```

### Regenerating proto stubs

After modifying `.proto` files:

```bash
python scripts/proto_sync.py   # Or: make proto
```

This regenerates all Python stubs and fixes import issues.

### Configuration

Memory uses Pydantic Settings. Override via environment variables:

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

See `src/memory/python/gladys_memory/config.py` for all settings.

Rust fast path uses identical environment variables. See `src/memory/rust/src/config.rs`.

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
| Integration tests | [src/integration/](../src/integration/) |
| gRPC contracts | `src/*/proto/*.proto` |

## Getting Help

- Check existing ADRs for design rationale
- Look at OPEN_QUESTIONS.md for active discussions
- Open an issue if stuck
