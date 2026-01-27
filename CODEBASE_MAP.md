# GLADyS Codebase Map

**Purpose**: AI-optimized source of truth to prevent hallucinations. Read this FIRST before making assumptions about the codebase.

**Last verified**: 2026-01-26 (updated with code review findings)

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

## Concurrency Model

### Overview

| Component | Runtime | Event Loop | gRPC Mode | Thread Model |
|-----------|---------|------------|-----------|--------------|
| **Orchestrator** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded + ThreadPoolExecutor for gRPC |
| **Memory Python** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Memory Rust** | Tokio | Multi-threaded Tokio runtime | Tonic (async) | Tokio work-stealing |
| **Executive** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Dashboard** | Streamlit | None (sync) | `grpc` (sync) | Main + background subscription thread |

### Orchestrator Concurrency

```
┌─────────────────────────────────────────────────────────────┐
│                    asyncio Event Loop                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ gRPC Server     │  │ _moment_tick    │  │ _outcome     │ │
│  │ (handles RPCs)  │  │ _loop()         │  │ _cleanup     │ │
│  │                 │  │ (100ms tick)    │  │ _loop()      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                              │
│  Fire-and-forget tasks: asyncio.create_task() ──► NO ERROR  │
│                                                   HANDLING   │
└─────────────────────────────────────────────────────────────┘
```

**Background tasks** (created via `asyncio.create_task()`):
- `_moment_tick_loop()` - Flushes accumulated events to Executive every 100ms
- `_outcome_cleanup_loop()` - Cleans expired outcome expectations every 30s
- `record_heuristic_fire()` - Fire-and-forget, **no error handling** (known issue)

**gRPC Server**: Uses `ThreadPoolExecutor(max_workers=config.max_workers)` but all handlers are `async def` running on the asyncio loop.

### Dashboard Concurrency (PROBLEMATIC)

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Process                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Main Thread (Streamlit)                                 ││
│  │ - Reruns entire script on every user interaction        ││
│  │ - Uses SYNC grpc (blocking calls)                       ││
│  │ - Creates new gRPC channel per stub call                ││
│  │ - Channels NEVER closed (resource leak)                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Background Thread (response_subscriber_thread)          ││
│  │ - Started at module level (line 163-171)                ││
│  │ - Daemon thread (dies with process)                     ││
│  │ - Uses thread-safe queue.Queue for communication        ││
│  │ - CANNOT be restarted if environment changes            ││
│  │ - Errors print to console, not visible in UI            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Key problems**:
1. Sync gRPC in main thread blocks UI during calls
2. Background thread started once, can't recover from env switch
3. No mechanism to stop/restart subscription thread
4. gRPC channels leaked on every call

### Rust Memory (Tokio)

```
┌─────────────────────────────────────────────────────────────┐
│                    Tokio Runtime                             │
│  ┌─────────────────┐  ┌─────────────────────────────────┐   │
│  │ Tonic gRPC      │  │ Arc<RwLock<MemoryCache>>        │   │
│  │ Server          │  │ (thread-safe cache access)      │   │
│  │                 │  │                                 │   │
│  │ Handles:        │  │ - Read lock for queries         │   │
│  │ - EvaluateSal.  │  │ - Write lock for updates        │   │
│  │ - Cache ops     │  │                                 │   │
│  └─────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

Uses Tokio's multi-threaded work-stealing runtime. `Arc<RwLock<>>` ensures thread-safe cache access.

### Sync/Async Boundaries

| Caller | Callee | Boundary |
|--------|--------|----------|
| Orchestrator (async) | Memory Python (async) | Clean - both async |
| Orchestrator (async) | Memory Rust (async) | Clean - both async |
| Dashboard (sync) | Orchestrator (async) | **MISMATCH** - sync client calling async server |
| Dashboard thread (sync) | Orchestrator (async) | Sync streaming over gRPC |

### Message Queues

| Queue | Type | Location | Purpose |
|-------|------|----------|---------|
| `asyncio.Queue` | In-memory | `router.py` Subscriber.queue | Event delivery to subscribers |
| `asyncio.Queue` | In-memory | `router.py` ResponseSubscriber.queue | Response delivery to subscribers |
| `queue.Queue` | Thread-safe | `dashboard.py` session_state.response_queue | Background thread → main thread |

No external message queues (Redis, RabbitMQ, etc.) are used. All queues are in-process.

### Known Concurrency Issues

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Fire-and-forget | `router.py:115` | HIGH | `asyncio.create_task()` without error callback |
| Race condition | `outcome_watcher.py` | HIGH | `_pending` list modified without lock |
| Channel leak | `dashboard.py:77-95` | HIGH | gRPC channels never closed |
| Thread lifecycle | `dashboard.py:163-171` | HIGH | Can't restart subscription thread |
| Sync/async mismatch | `dashboard.py` | MEDIUM | Sync gRPC blocks Streamlit main thread |

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

## OutcomeWatcher (Implicit Feedback)

**Location**: `src/orchestrator/gladys_orchestrator/outcome_watcher.py`
**Integrated in**: `router.py`

Watches for "outcomes" after heuristic fires to provide implicit feedback. When a heuristic fires and a subsequent event matches the expected outcome pattern, positive feedback is automatically sent.

### Integration Points

| Location | What Happens |
|----------|--------------|
| `router.py:83-86` | Every incoming event is checked against pending outcomes via `check_event()` |
| `router.py:159-164` | When heuristic matches, fire is registered with expected outcome via `register_fire()` |
| `server.py:57` | OutcomeWatcher created via `_create_outcome_watcher()` |
| `server.py:107-108` | Cleanup loop started for expired expectations |

### Configuration

| Config Key | Default | Purpose |
|------------|---------|---------|
| `outcome_watcher_enabled` | `True` | Enable/disable outcome watching |
| `outcome_cleanup_interval_sec` | `30` | How often to clean expired expectations |
| `outcome_patterns_json` | `'[]'` | JSON array of trigger→outcome patterns |

### Known Issues (to be fixed)

- **Race condition**: `_pending` list modified without lock in `register_fire()` and `cleanup_expired()`
- **None check**: `result.get('success')` could fail if client returns None

---

## Dashboard (UI)

**Location**: `src/ui/dashboard.py` (1070 lines - refactoring planned)
**Framework**: Streamlit
**Port**: 8501

The dashboard provides a dev/debug interface for GLADyS with tabs for event simulation, memory inspection, cache management, and service controls.

### Known Issues (to be fixed)

| Issue | Severity | Description |
|-------|----------|-------------|
| gRPC channel leak | HIGH | Channels created in `get_*_stub()` are never closed |
| Silent thread errors | HIGH | Background thread errors print to console, not visible in UI |
| Thread lifecycle | HIGH | Subscription thread started at module level, can't recover from env changes |
| Bare except clauses | MEDIUM | Several places swallow all exceptions silently |

### Planned Refactoring

See `docs/design/REFACTORING_PLAN.md` Phase 1 for modularization plan:
- Extract `components/grpc_clients.py` for channel lifecycle management
- Extract `components/service_controls.py` for start/stop logic
- Extract tab-specific components (event_lab, memory_console, etc.)

---

## Docker Build Requirements (CRITICAL)

When adding dependencies or modifying code that uses shared packages, Docker builds will BREAK unless you follow these rules:

### 1. gladys_common Dependency Pattern

Any Python service using `gladys_common` (via `from gladys_common import ...`) MUST:

1. **Use project root as build context** in docker-compose.yml:
   ```yaml
   build:
     context: ../..  # Project root
     dockerfile: src/service/Dockerfile
   ```

2. **Copy gladys_common in Dockerfile**:
   ```dockerfile
   # Copy gladys-common first (dependency)
   COPY src/common/pyproject.toml ./common/pyproject.toml
   COPY src/common/gladys_common ./common/gladys_common
   ```

3. **Strip uv.sources and fix path** before installing:
   ```dockerfile
   RUN sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
       sed -i 's/"gladys-common",/"gladys-common @ file:\/\/\/app\/common",/' pyproject.toml && \
       pip install -e ./common && \
       pip install -e .
   ```

**Services currently using gladys_common**:
- `src/orchestrator/` (router.py, __main__.py)
- `src/memory/python/` (grpc_server.py)

### 2. Local Path Dependencies in pyproject.toml

Files with `[tool.uv.sources]` sections that specify local paths:
- `src/orchestrator/pyproject.toml` → `gladys-common = { path = "../common" }`
- `src/memory/python/pyproject.toml` → `gladys-common = { path = "../../common" }`

These paths work locally but NOT in Docker unless handled as shown above.

### 3. Transitive Dependencies

Some packages may not install all their transitive dependencies correctly. Known examples:
- `huggingface-hub` and `sentence-transformers` require `requests` but it may not be auto-installed via uv
- **Fix**: Add explicit dependency in pyproject.toml: `"requests>=2.28"`

### 4. Verification After Changes

After modifying Dockerfiles or dependencies:
```bash
# Rebuild with no cache to catch issues
python scripts/docker.py build <service> --no-cache

# Check packages in container
docker run --rm --entrypoint pip <image> freeze | grep <package>

# Run tests
python scripts/docker.py test
```

---

## Common Mistakes to Avoid

1. **Port confusion**: MemoryStorage is 50051, SalienceGateway is 50052. They're different!
2. **Assuming keyword matching**: Heuristics use embedding similarity, not word overlap
3. **source vs origin**: `source` is the event sensor, `origin` is how the heuristic was created
4. **source_filter misuse**: Filters by condition_text PREFIX (e.g., "minecraft:..."), NOT by event.source
5. **Stale stubs**: After editing `proto/*.proto`, run `python scripts/proto_gen.py` to regenerate
6. **Docker ports**: Add 10 to local ports (50051 → 50061)
7. **Missing trace IDs**: Always extract/propagate `x-gladys-trace-id` from gRPC metadata
8. **Fire-and-forget tasks**: `asyncio.create_task()` without error handling silently drops exceptions
9. **gRPC channel leaks**: Always close channels or use a managed client class
10. **Async lock scope**: If using `asyncio.Lock`, protect ALL access points, not just some
11. **Adding gladys_common import without Dockerfile update**: If you add `from gladys_common import ...` to a service, the Dockerfile MUST be updated (see Docker Build Requirements above)
12. **Using local context for services with shared deps**: docker-compose.yml must use project root context (`../..`) for any service that depends on gladys_common

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
- `docs/design/REFACTORING_PLAN.md` - Code quality fixes and dashboard modularization
