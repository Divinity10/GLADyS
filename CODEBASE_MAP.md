# GLADyS Codebase Map

**Purpose**: AI-optimized source of truth to prevent hallucinations. Read this FIRST before making assumptions about the codebase.

**Last verified**: 2026-01-26

---

## Service Topology

> **Note on Languages**: The Orchestrator and Executive are currently implemented in **Python**. This differs from `GEMINI.md` / ADR-0001 (which specify Rust/C#). This map reflects the *actual* codebase state.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL CALLERS                            │
│              (Sensors, Dashboard UI, Tests, Executive)              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Orchestrator │    │  SalienceGateway │    │    Executive     │
│    (Python)   │    │     (Rust)       │    │    (Python)      │
│   Port 50050  │    │   Port 50052     │    │   Port 50053     │
│               │    │                  │    │                  │
│ OrchestratorSvc│   │ SalienceGateway  │    │ ExecutiveService │
│               │    │ (evaluates       │    │ (stub for now)   │
│ Routes events │    │  salience)       │    │                  │
└───────┬───────┘    └────────┬─────────┘    └──────────────────┘
        │                     │
        │                     │ QueryMatchingHeuristics RPC
        │                     ▼
        │            ┌──────────────────┐
        │            │  MemoryStorage   │
        └───────────►│    (Python)      │
                     │   Port 50051     │
                     │                  │
                     │ MemoryStorage    │
                     │ (stores data,    │
                     │  generates       │
                     │  embeddings)     │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │   PostgreSQL     │
                     │  + pgvector      │
                     │   Port 5432      │
                     └──────────────────┘
```

---

## Port Reference (CRITICAL - memorize this)

| Service | Local Port | Docker Host Port | Proto Service | Language |
|---------|------------|------------------|---------------|----------|
| Orchestrator | 50050 | 50060 | `OrchestratorService` | Python |
| MemoryStorage | 50051 | 50061 | `MemoryStorage` | Python |
| SalienceGateway | 50052 | 50062 | `SalienceGateway` | Rust |
| Executive | 50053 | 50063 | `ExecutiveService` | Python (stub) |
| Dashboard (UI) | 8501 | 8501 | - | Python (Streamlit) |
| PostgreSQL | 5432 | 5433 | - | - |

**IMPORTANT**:
- **Docker Internal Ports**: Inside the Docker network, services communicate on their standard "Local Port" (e.g., Orchestrator talks to Memory at `memory-python:50051`). The "Docker Host Port" is only for external access (localhost).
- `MemoryStorage` (50051) handles: storing events, storing heuristics, embeddings, DB queries
- `SalienceGateway` (50052) handles: EvaluateSalience, cache management (stats/flush/evict/list)
- These are DIFFERENT services on DIFFERENT ports despite both being in `src/memory/`

---

## Proto Services and Implementations

### `MemoryStorage` Service (memory.proto)
**Implemented by**: `src/memory/python/gladys_memory/grpc_server.py`
**Port**: 50051 (local) / 50061 (docker)

| RPC | Purpose |
|-----|---------|
| `StoreEvent` | Persist episodic event with embedding |
| `StoreHeuristic` | Create/update learned rule |
| `QueryMatchingHeuristics` | Semantic search for heuristics (embedding similarity) |
| `UpdateHeuristicConfidence` | TD learning confidence update |
| `RecordHeuristicFire` | Track heuristic firing (flight recorder) |
| `UpdateFireOutcome` | Record success/fail for learning |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, db status, etc. |

### `SalienceGateway` Service (memory.proto)
**Implemented by**: `src/memory/rust/src/server.rs`
**Port**: 50052 (local) / 50062 (docker)

| RPC | Purpose |
|-----|---------|
| `EvaluateSalience` | Score event importance (calls MemoryStorage on cache miss) |
| `FlushCache` | Clear heuristic cache |
| `EvictFromCache` | Remove single heuristic from cache |
| `GetCacheStats` | Get hit rate, size, etc. |
| `ListCachedHeuristics` | List what's in cache |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, cache stats |

### `OrchestratorService` (orchestrator.proto)
**Implemented by**: `src/orchestrator/gladys_orchestrator/server.py`
**Port**: 50050 (local) / 50060 (docker)

| RPC | Purpose |
|-----|---------|
| `PublishEvents` | Receive sensor events (streaming) |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, connected services |

### `ExecutiveService` (executive.proto)
**Implemented by**: `src/executive/gladys_executive/server.py`
**Port**: 50053 (local) / 50063 (docker)

| RPC | Purpose |
|-----|---------|
| `ProcessEvent` | Handle high-salience event with LLM |
| `SubmitFeedback` | User feedback for learning |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, ollama/memory status |

---

## Data Flow: Event Processing

```
1. Sensor emits event
        │
        ▼
2. Orchestrator.PublishEvents (50050)
        │
        ▼
3. Orchestrator calls SalienceGateway.EvaluateSalience (50052)
        │
        ├─► Rust checks local LRU cache
        │   └─► Cache HIT: return cached salience + record hit
        │
        └─► Cache MISS: Rust calls MemoryStorage.QueryMatchingHeuristics (50051)
                │
                ▼
            Python does semantic search (embedding cosine similarity)
                │
                ▼
            Results returned to Rust → cached → salience computed
        │
        ▼
4. If salience > threshold: Orchestrator calls Executive.ProcessEvent (50053)
        │
        ▼
5. Executive uses LLM to decide action, may create new heuristic
```

---

## Data Flow: Heuristic Creation and Learning

```
1. Executive decides to create heuristic from LLM response
        │
        ▼
2. Executive calls MemoryStorage.StoreHeuristic (50051)
        │  - condition_text: natural language trigger
        │  - effects_json: what to do when matched
        │  - origin: 'learned', 'user', 'pack', 'built_in'
        │
        ▼
3. Python generates embedding from condition_text
        │
        ▼
4. Heuristic stored in PostgreSQL (heuristics table)

--- Later, when heuristic fires ---

5. Event matches heuristic during EvaluateSalience
        │
        ▼
6. Executive records fire: MemoryStorage.RecordHeuristicFire (50051)
        │
        ▼
7. User gives feedback (thumbs up/down) OR outcome detected
        │
        ▼
8. MemoryStorage.UpdateHeuristicConfidence (50051)
        │  - Uses TD learning: new_conf = old_conf + lr * (actual - predicted)
        │
        ▼
9. Confidence updated, heuristic becomes more/less trusted
```

---

## Key Conventions

### Heuristic Matching
- **Semantic matching**: Python uses cosine similarity between event embedding and condition_embedding
- **NOT keyword matching**: Don't assume simple word overlap
- **source_filter**: Optional filter that matches heuristic condition_text PREFIX (e.g., `source="minecraft"` matches conditions starting with `"minecraft:"`)

### Heuristic Fields
| Field | Purpose |
|-------|---------|
| `condition_text` | Natural language description of when to trigger |
| `condition_embedding` | 384-dim vector generated from condition_text |
| `effects_json` | JSON with salience modifiers and actions |
| `confidence` | 0.0-1.0, updated via TD learning |
| `origin` | `'learned'`, `'user'`, `'pack'`, `'built_in'` |

### SalienceVector Fields
All float 0.0-1.0:
- `threat`, `opportunity`, `humor`, `novelty`, `goal_relevance`, `social`, `emotional`, `actionability`, `habituation`

---

## Directory Structure

```
GLADys/
├── proto/                      # SHARED PROTO DEFINITIONS (source of truth)
│   ├── types.proto             # Shared types (SalienceVector, Health messages)
│   ├── common.proto            # Common message types (Event, Moment)
│   ├── memory.proto            # MemoryStorage + SalienceGateway services
│   ├── orchestrator.proto      # OrchestratorService
│   └── executive.proto         # ExecutiveService
│
├── src/
│   ├── common/                 # SHARED PYTHON UTILITIES
│   │   └── gladys_common/
│   │       ├── __init__.py
│   │       └── logging.py      # Structured logging (structlog)
│   │
│   ├── memory/
│   │   ├── python/             # MemoryStorage service (port 50051)
│   │   │   └── gladys_memory/
│   │   │       └── generated/  # Generated stubs from proto/
│   │   ├── rust/               # SalienceGateway service (port 50052)
│   │   │   └── src/
│   │   │       └── logging.rs  # Structured logging (tracing)
│   │   └── migrations/         # PostgreSQL schema (shared)
│   │
│   ├── orchestrator/           # OrchestratorService (port 50050)
│   │   └── gladys_orchestrator/
│   │       └── generated/      # Generated stubs from proto/
│   │
│   ├── executive/              # ExecutiveService stub (port 50053)
│   │   └── gladys_executive/
│   │
│   └── integration/            # Integration tests + docker-compose.yml
│
├── scripts/
│   ├── local.py                # Manage local services
│   ├── docker.py               # Manage Docker services
│   ├── proto_gen.py            # Generate proto stubs for all services
│   ├── _service_base.py        # Shared service management framework
│   ├── _local_backend.py       # Local service start/stop/status
│   ├── _docker_backend.py      # Docker service management
│   ├── _cache_client.py        # gRPC client for cache management
│   ├── _health_client.py       # gRPC client for health checks
│   ├── _sync_check.py          # Proto/migration sync verification
│   └── _gladys.py              # Shared config (ports, utils)
│
└── docs/
    ├── adr/                    # Architecture Decision Records
    └── design/                 # Design docs and discussions
```

---

## Database Schema (Key Tables)

### `heuristics`
| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| name | TEXT | Human-readable name |
| condition | JSONB | `{"text": "...", "origin": "..."}` |
| action | JSONB | Effects/actions when triggered |
| confidence | FLOAT | 0.0-1.0, TD learning target |
| condition_embedding | vector(384) | For semantic search |
| origin | TEXT | 'learned', 'user', 'pack', 'built_in' |
| fire_count | INT | Times heuristic triggered |
| success_count | INT | Successful outcomes |

### `episodic_events`
| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| timestamp | TIMESTAMPTZ | When event occurred |
| source | TEXT | Sensor/origin |
| raw_text | TEXT | Natural language description |
| embedding | vector(384) | For similarity search |
| salience | JSONB | Computed salience vector |

### `heuristic_fires` (Flight Recorder)
| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| heuristic_id | UUID | FK to heuristics |
| event_id | TEXT | Triggering event |
| fired_at | TIMESTAMPTZ | When fired |
| outcome | TEXT | 'success', 'fail', NULL (pending) |
| feedback_source | TEXT | 'explicit', 'implicit' |

---

## Logging and Observability

### Trace ID Propagation
All services propagate trace IDs via gRPC metadata for request correlation:

```
Header: x-gladys-trace-id
Format: 12 hex characters (e.g., "abc123def456")
```

Flow: Orchestrator generates → Rust receives and forwards → Python receives and logs

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level (DEBUG, INFO, WARN, ERROR) |
| `LOG_FORMAT` | `human` | Output format (`human` or `json`) |
| `LOG_FILE` | (none) | Path to log file (optional) |
| `LOG_FILE_LEVEL` | same as LOG_LEVEL | Level for file output |

### Logging Implementation

| Service | Module | Framework |
|---------|--------|-----------|
| Python services | `gladys_common.logging` | structlog |
| Rust services | `src/memory/rust/src/logging.rs` | tracing |

See `docs/design/LOGGING_STANDARD.md` for full specification.

---

## Common Mistakes to Avoid

1. **Port confusion**: MemoryStorage is 50051, SalienceGateway is 50052. They're different!
2. **Assuming keyword matching**: Heuristics use embedding similarity, not word overlap
3. **source vs origin**: `source` is the event sensor, `origin` is how the heuristic was created
4. **source_filter**: Filters by condition_text PREFIX, not by origin field
5. **Stale stubs**: After editing `proto/*.proto`, run `python scripts/proto_gen.py` to regenerate
6. **Docker ports**: Add 10 to local ports (50051 → 50061)
7. **Missing trace IDs**: Always extract/propagate `x-gladys-trace-id` from gRPC metadata

---

## Quick Commands

```bash
# Start all services locally
python scripts/local.py start all

# Check status (process-level)
python scripts/local.py status

# Check health (gRPC-level)
python scripts/local.py health
python scripts/local.py health -d    # detailed with uptime/metrics

# Regenerate proto stubs after editing proto/
python scripts/proto_gen.py

# Cache management
python scripts/local.py cache stats
python scripts/local.py cache list
python scripts/local.py cache flush

# Run integration tests
cd src/integration && uv run pytest -v

# Database query
python scripts/local.py query "SELECT * FROM heuristics LIMIT 5"
```

---

## See Also

- `src/memory/README.md` - Memory subsystem details
- `src/orchestrator/README.md` - Event routing details
- `src/executive/README.md` - LLM integration details
- `docs/adr/` - Architecture decisions
- `docs/design/OPEN_QUESTIONS.md` - Active design discussions
- `docs/design/LOGGING_STANDARD.md` - Logging and observability specification
