# GLADyS Orchestrator

The Orchestrator is GLADyS's event router - it receives events from sensors, evaluates their salience (importance), and routes high-salience events to the Executive for LLM-based decision making.

## Service Info

| Property | Value |
|----------|-------|
| Port (local) | 50050 |
| Port (docker) | 50060 |
| Proto service | `OrchestratorService` |
| Entry point | `python -m gladys_orchestrator start` |

## What It Does

```
Sensors → Orchestrator → [Salience Eval] → Executive (if high salience)
                              ↓
                    SalienceGateway (Rust 50052)
                              ↓
                    MemoryStorage (Python 50051)
```

1. **Receives events** via `PublishEvents` streaming RPC
2. **Calls SalienceGateway** (Rust, port 50052) to evaluate importance
3. **Routes high-salience events** to Executive for LLM processing
4. **Accumulates low-salience events** for batch processing

## Key Components

| File | Purpose |
|------|---------|
| `server.py` | gRPC server, `PublishEvents` handler |
| `router.py` | Event routing logic, salience thresholds |
| `accumulator.py` | Low-salience event batching |
| `outcome_watcher.py` | Watches for implicit feedback (learning) |
| `skill_registry.py` | Skill/action registry |
| `clients/` | gRPC clients for other services |
| `generated/` | Proto-generated stubs (DO NOT EDIT) |

## Proto Definitions

All proto definitions live in `proto/` at the project root (single source of truth).

```bash
# Regenerate stubs after editing protos
python scripts/proto_gen.py
```

Generated stubs are written to `gladys_orchestrator/generated/` (DO NOT EDIT these).

## Running

```bash
# Via admin script (recommended)
python scripts/local.py start orchestrator

# Directly
cd src/orchestrator
uv run python -m gladys_orchestrator start
```

## Configuration

Environment variables (see `config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORCHESTRATOR_HOST` | 0.0.0.0 | Bind address |
| `ORCHESTRATOR_PORT` | 50050 | gRPC port |
| `SALIENCE_ADDRESS` | localhost:50052 | SalienceGateway (Rust) |
| `EXECUTIVE_ADDRESS` | localhost:50053 | Executive service |
| `MEMORY_ADDRESS` | localhost:50051 | MemoryStorage (Python) |

## Dependencies

The Orchestrator depends on:
- **SalienceGateway** (50052) - for salience evaluation
- **MemoryStorage** (50051) - for storing events, recording fires
- **Executive** (50053) - for handling high-salience events

Start these first or use `python scripts/local.py start all`.

## Testing

```bash
cd src/orchestrator
uv run pytest tests/ -v

# Integration tests (requires all services running)
cd src/integration
uv run pytest test_orchestrator_memory.py -v
```
