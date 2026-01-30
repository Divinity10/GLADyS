# GLADyS Executive (Stub)

The Executive is GLADyS's decision-making component - it receives high-salience events from the Orchestrator, processes them with an LLM, and learns from feedback.

**Status**: This is a Python stub for integration testing. The production Executive will be in C#/.NET.

## Service Info

| Property | Value |
|----------|-------|
| Port (local) | 50053 |
| Port (docker) | 50063 |
| Proto service | `ExecutiveService` |
| Entry point | `python -m gladys_executive start` |

## What It Does

```
Orchestrator → Executive → [LLM Decision] → Response
                    ↓
              [Pattern Extraction]
                    ↓
              MemoryStorage (learned heuristics)
```

1. **ProcessEvent** - Handles immediate high-salience events (threat > 0.7)
2. **ProcessMoment** - Handles batched low-salience events
3. **ProvideFeedback** - Receives user feedback, extracts patterns, creates heuristics

## Key Components

| File | Purpose |
|------|---------|
| `gladys_executive/server.py` | gRPC server, LLM integration, pattern extraction |
| `gladys_executive/__main__.py` | CLI entry point (`start`, `status` commands) |

## External Dependencies

| Service | Address | Purpose |
|---------|---------|---------|
| Ollama | `http://localhost:11434` | Local LLM inference |
| MemoryStorage | `localhost:50051` | Storing learned heuristics |

**Note**: Both are optional. Executive works without them but won't have LLM responses or persistent learning.

## Running

```bash
# Via admin script (recommended)
python scripts/local.py start executive

# Directly
cd src/executive
uv run python -m gladys_executive start

# With Ollama LLM
uv run python -m gladys_executive start --ollama-url http://localhost:11434 --model gemma:2b

# With Memory integration
uv run python -m gladys_executive start --memory-address localhost:50051
```

## Configuration

Environment variables or CLI flags:

| Variable | CLI Flag | Default | Purpose |
|----------|----------|---------|---------|
| `EXECUTIVE_PORT` | `--port` | 50053 | gRPC port |
| `OLLAMA_URL` | `--ollama-url` | (none) | Ollama server URL |
| `OLLAMA_MODEL` | `--model` | gemma:2b | LLM model name |
| `MEMORY_ADDRESS` | `--memory-address` | (none) | MemoryStorage address |

## Learning Loop

When feedback is provided:

1. **Positive feedback** → Extract pattern from context/response → Create heuristic
2. **Negative feedback** → Decrease confidence of matched heuristic (TD learning)

Extracted heuristics are stored via MemoryStorage (if connected) or local `heuristics.json` file.

## Proto Dependency

Uses protos from `src/orchestrator/gladys_orchestrator/generated/`:
- `executive.proto` - ExecutiveService definition
- `common.proto` - Event, Salience types
- `memory.proto` - For storing heuristics

## Testing

```bash
cd src/executive
uv run python -m gladys_executive status  # Check if running

# Integration tests (from src/integration)
cd src/integration
uv run pytest test_orchestrator_memory.py -v
```
