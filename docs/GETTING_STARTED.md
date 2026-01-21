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

The brain. Routes events, manages attention, coordinates everything.

**Local setup:**
```bash
# Start Memory (dependency)
cd src/memory && python run.py start

# Then work on Orchestrator
cd src/orchestrator    # (doesn't exist yet)
cargo build
```

**You need:** Rust toolchain

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

### Running everything

```bash
# Start Memory
cd src/memory && python run.py start

# (Future: start other subsystems similarly)
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

## Where to Find Things

| What | Where |
|------|-------|
| Architecture decisions | [docs/adr/](adr/) |
| Open design questions | [docs/design/OPEN_QUESTIONS.md](design/OPEN_QUESTIONS.md) |
| Memory subsystem | [src/memory/](../src/memory/) |
| gRPC contracts | `src/*/proto/*.proto` |

## Getting Help

- Check existing ADRs for design rationale
- Look at OPEN_QUESTIONS.md for active discussions
- Open an issue if stuck
