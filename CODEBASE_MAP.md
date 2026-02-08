# GLADyS Codebase Map

**Purpose**: AI-optimized source of truth to prevent hallucinations. Read this FIRST before making assumptions about the codebase.

**Last verified**: 2026-02-08 (updated: RPC tables synced to proto files, SDK directories, data flow)

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
│               │    │ (evaluates       │    │ (decides action)   │
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
| Executive | 50053 | 50063 | `ExecutiveService` | Python |
| Dashboard (UI) + fun_api | 8502 | 8502 | - | Python (FastAPI/htmx) |
| PostgreSQL | 5432 | 5433 | - | - |

**IMPORTANT**:
- **Docker Internal Ports**: Inside the Docker network, services communicate on their standard "Local Port" (e.g., Orchestrator talks to Memory at `memory-python:50051`). The "Docker Host Port" is only for external access (localhost).
- `MemoryStorage` (50051) handles: storing events, storing heuristics, embeddings, DB queries
- `SalienceGateway` (50052) handles: EvaluateSalience, cache management (stats/flush/evict/list)
- These are DIFFERENT services on DIFFERENT ports despite both being in `src/services/`

---

## Proto Services and Implementations

### `MemoryStorage` Service (memory.proto)
**Implemented by**: `src/services/memory/gladys_memory/grpc_server.py`
**Port**: 50051 (local) / 50061 (docker)

| RPC | Purpose |
|-----|---------|
| `StoreEvent` | Persist episodic event with embedding |
| `QueryByTime` | Query events by time range |
| `QueryBySimilarity` | Query events by embedding similarity |
| `ListEvents` | List recent events (newest first, paginated) |
| `GetEvent` | Get a single event by ID |
| `GenerateEmbedding` | Generate embedding for text |
| `StoreHeuristic` | Create/update learned rule |
| `QueryHeuristics` | Query heuristics by condition match (embedding similarity) |
| `QueryMatchingHeuristics` | Text search for heuristics (PostgreSQL tsvector, used by Rust on cache miss) |
| `GetHeuristic` | Get a single heuristic by ID |
| `UpdateHeuristicConfidence` | TD learning confidence update |
| `StoreEntity` | Store or update a semantic entity |
| `QueryEntities` | Query entities by name, type, or embedding |
| `StoreRelationship` | Store a relationship between entities |
| `GetRelationships` | Get relationships for an entity (1-hop context) |
| `ExpandContext` | Get entity + relationships + related entities (for LLM prompts) |
| `ListResponses` | List events with decision chain data (Response tab) |
| `GetResponseDetail` | Get full detail for one event (drill-down) |
| `DeleteResponses` | Delete multiple events by ID (dashboard bulk delete) |
| `RecordHeuristicFire` | Track heuristic firing (flight recorder) |
| `UpdateFireOutcome` | Record success/fail for learning |
| `GetPendingFires` | Get fires awaiting feedback |
| `ListFires` | List all heuristic fires with optional filtering |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, db status, etc. |

### `SalienceGateway` Service (memory.proto)
**Implemented by**: `src/services/salience/src/server.rs`
**Port**: 50052 (local) / 50062 (docker)

| RPC | Purpose |
|-----|---------|
| `EvaluateSalience` | Score event importance (cache-first: local cosine similarity on cached embeddings, falls back to MemoryStorage on cache miss) |
| `FlushCache` | Clear heuristic cache |
| `EvictFromCache` | Remove single heuristic from cache |
| `GetCacheStats` | Get hit rate, size, etc. |
| `ListCachedHeuristics` | List what's in cache |
| `NotifyHeuristicChange` | Push invalidation from Memory (created/updated/deleted) |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, cache stats |

### `OrchestratorService` (orchestrator.proto)
**Implemented by**: `src/services/orchestrator/gladys_orchestrator/server.py`
**Port**: 50050 (local) / 50060 (docker)

| RPC | Purpose |
|-----|---------|
| `PublishEvent` | Publish single sensor event (unary) |
| `PublishEvents` | Publish batch of sensor events (unary) |
| `StreamEvents` | Receive sensor events (streaming, deprecated) |
| `RegisterComponent` | Register sensor/component with capabilities |
| `Heartbeat` | Component heartbeat with state |
| `ResolveComponent` | Look up component by ID |
| `UnregisterComponent` | Remove component registration |
| `SendCommand` | Send command to a component |
| `SubscribeEvents` | Subscribe to event stream |
| `SubscribeResponses` | Subscribe to response stream |
| `ListQueuedEvents` | List events in processing queue |
| `GetQueueStats` | Get queue statistics |
| `GetSystemStatus` | Get overall system status |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, connected services |

### `ExecutiveService` (executive.proto)
**Implemented by**: `src/services/executive/gladys_executive/server.py`
**Port**: 50053 (local) / 50063 (docker)

| RPC | Purpose |
|-----|---------|
| `ProcessEvent` | Decide heuristic vs LLM path; generate response |
| `ProvideFeedback` | User feedback for heuristic formation |
| `GetHealth` | Basic health check (HEALTHY/UNHEALTHY) |
| `GetHealthDetails` | Detailed health with uptime, ollama/memory status |

---

## Data Flow: Event Processing

```
1. Sensor emits event
        │
        ▼
2. Orchestrator.PublishEvent (50050)
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
4. Orchestrator ALWAYS forwards to Executive.ProcessEvent (50053)
   with heuristic suggestion context (if any match found)
   Exception: emergency fast-path (confidence >= 0.95 AND threat >= 0.9)
        │
        ▼
5. Executive decides: high-confidence heuristic → fast-path (no LLM)
                      otherwise → LLM reasoning, may create new heuristic
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

--- Heuristic deletion (KNOWN GAP) ---

10. Dashboard calls DELETE /api/heuristics/{id}
        │
        ▼
11. fun_api/heuristics.py → Direct DB delete (bypasses gRPC, tech debt #83)
        │
        ▼
12. Heuristic removed from PostgreSQL
        │
        ✗ Rust SalienceGateway NOT notified
        ✗ Stale heuristic may remain in Rust LRU cache
```

**BUG**: Deleting a heuristic via dashboard does not call `NotifyHeuristicChange` to invalidate Rust cache. The deleted heuristic may continue to match events until cache TTL expires or cache is flushed.

---

## Data Ownership: Who Writes What

Each table has a single owning component. No table is written by multiple services.

| Table | Owner | Write Paths | Key Files |
|-------|-------|-------------|-----------|
| `episodic_events` | Orchestrator | (1) Immediate heuristic match, (2) After queued event processed | `server.py:182`, `event_queue.py:248` |
| `heuristic_fires` | Orchestrator | On any heuristic match (via LearningModule) | `learning.py:on_fire()` |
| `heuristics` | Executive | On positive feedback (learned patterns) | `gladys_executive/server.py:537-563` |
| `heuristics.confidence` | Executive | On any feedback (TD learning update) | `gladys_executive/server.py:477-485` |
| `heuristic_fires.outcome` | LearningModule | Implicit feedback (timeout, undo, ignored-3x, pattern match) | `learning.py:on_outcome()` |

### Response Delivery

All event responses flow through the Orchestrator — no component can push responses directly to clients.

| Path | Flow | Delivery |
|------|------|----------|
| Emergency fast-path | Sensor → Orchestrator → EventAck (inline) | Synchronous in PublishEvents stream (confidence >= 0.95 AND threat >= 0.9 only) |
| Normal (all other events) | Sensor → Orchestrator → Queue → Executive → Orchestrator → broadcast | Async via SubscribeResponses stream. Executive decides heuristic fast-path vs LLM. |

---

## Concurrency Model

### Overview

| Component | Runtime | Event Loop | gRPC Mode | Thread Model |
|-----------|---------|------------|-----------|--------------|
| **Orchestrator** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded + ThreadPoolExecutor for gRPC |
| **Memory Python** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Memory Rust** | Tokio | Multi-threaded Tokio runtime | Tonic (async) | Tokio work-stealing |
| **Executive** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Dashboard** | FastAPI (uvicorn) | asyncio | REST/SSE | Single-threaded + background gRPC thread for SSE |

### Orchestrator Concurrency

```
┌─────────────────────────────────────────────────────────────┐
│                    asyncio Event Loop                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ gRPC Server     │  │ EventQueue      │  │ _outcome     │ │
│  │ (handles RPCs)  │  │ _worker_loop()  │  │ _cleanup     │ │
│  │                 │  │ (async dequeue) │  │ _loop()      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                              │
│  Fire-and-forget tasks: asyncio.create_task() ──► NO ERROR  │
│                                                   HANDLING   │
└─────────────────────────────────────────────────────────────┘
```

**Background tasks** (created via `asyncio.create_task()`):
- `EventQueue._worker_loop()` - Dequeues events by priority, sends to Executive
- `EventQueue._timeout_scanner_loop()` - Removes expired events (default 30s timeout)
- `_outcome_cleanup_loop()` - Cleans expired outcome expectations every 30s, sends timeout=positive feedback via LearningModule
- `learning_module.on_fire()` - Fire-and-forget (records fire + registers outcome expectation)

**gRPC Server**: Uses `ThreadPoolExecutor(max_workers=config.max_workers)` but all handlers are `async def` running on the asyncio loop.

### Dashboard Concurrency (V2 — FastAPI)

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI (uvicorn)                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ asyncio Event Loop                                      ││
│  │ - REST endpoints (sync gRPC via env.py stubs)           ││
│  │ - SSE streams (EventSourceResponse)                     ││
│  │ - Jinja2 template rendering for htmx partials           ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Background Threads                                      ││
│  │ - PublishEvents gRPC (fire-and-forget, daemon)          ││
│  │ - SubscribeResponses gRPC (SSE feeder, per-client)      ││
│  │ - SSE retry loop for DB enrichment (race condition fix) ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Key design choices**:
1. Sync gRPC stubs wrapped in `run_in_executor` or background threads
2. SSE feeder thread per client, communicates via `asyncio.Queue`
3. DB enrichment retries with backoff (store_callback race condition)
4. htmx sidebar polls every 10s; controls are static (outside swap target) to preserve Alpine state

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
| Dashboard (FastAPI async) | Orchestrator (async) | Sync gRPC in background threads |

### Message Queues

| Queue | Type | Location | Purpose |
|-------|------|----------|---------|
| `asyncio.Queue` | In-memory | `router.py` Subscriber.queue | Event delivery to subscribers |
| `asyncio.Queue` | In-memory | `router.py` ResponseSubscriber.queue | Response delivery to subscribers |
| `asyncio.Queue` | In-memory | `events.py` response_queue | SSE gRPC thread → async SSE generator |

No external message queues (Redis, RabbitMQ, etc.) are used. All queues are in-process.

### Known Concurrency Issues

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Fire-and-forget | `router.py:115` | HIGH | `asyncio.create_task()` without error callback |
| Race condition | `outcome_watcher.py` | HIGH | `_pending` list modified without lock |
| SSE race condition | `events.py:341-357` | LOW | Mitigated with retry+backoff; store_callback may not commit before broadcast |

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

### Heuristic Field Gaps (Proto vs DB)

| Field | DB Column | Proto Field | Notes |
|-------|-----------|-------------|-------|
| Active status | `frozen` (BOOLEAN) | **NOT IN PROTO** | DB uses `frozen=false` for active. Code uses `getattr(h, "active") else True` |
| Origin ID | `origin_id` | `origin_id` | In proto but `_heuristic_to_dict` may not include it |

**Impact**: Dashboard filtering by "active" status requires workaround since proto doesn't have the field.

### SalienceVector Fields
All float 0.0-1.0:
- `threat`, `opportunity`, `humor`, `novelty`, `goal_relevance`, `social`, `emotional`, `actionability`, `habituation`

---

## Directory Structure

```
GLADys/
├── proto/                      # SHARED PROTO DEFINITIONS (source of truth)
│   ├── types.proto             # Shared types (SalienceVector, Health messages)
│   ├── common.proto            # Common message types (Event)
│   ├── memory.proto            # MemoryStorage + SalienceGateway services
│   ├── orchestrator.proto      # OrchestratorService
│   └── executive.proto         # ExecutiveService
│
├── src/
│   ├── lib/
│   │   ├── gladys_common/      # SHARED PYTHON UTILITIES
│   │   │   └── gladys_common/
│   │   │       ├── __init__.py
│   │   │       └── logging.py  # Structured logging (structlog)
│   │   │
│   │   └── gladys_client/      # SHARED CLIENT LIBRARY (DB, gRPC clients)
│   │       └── gladys_client/
│   │           ├── __init__.py
│   │           ├── db.py       # PostgreSQL queries (events, heuristics, fires, metrics)
│   │           ├── orchestrator.py  # Orchestrator gRPC client (publish_event, get_stub)
│   │           ├── cache.py    # SalienceGateway gRPC client
│   │           └── health.py   # Multi-service health checker
│   │
│   ├── services/
│   │   ├── memory/             # MemoryStorage service (port 50051)
│   │   │   └── gladys_memory/
│   │   │
│   │   ├── salience/           # SalienceGateway service (Rust, port 50052)
│   │   │   └── src/
│   │   │       └── logging.rs  # Structured logging (tracing)
│   │   │
│   │   ├── orchestrator/       # OrchestratorService (port 50050)
│   │   │   └── gladys_orchestrator/
│   │   │       └── generated/  # Generated stubs from proto/
│   │   │
│   │   ├── executive/          # ExecutiveService stub (port 50053)
│   │   │   └── gladys_executive/
│   │   │
│   │   ├── fun_api/            # JSON API (imported by dashboard, see Dual-Router below)
│   │   │   └── routers/        # REST/JSON routers: cache, fires, heuristics, llm, logs, etc.
│   │   │
│   │   └── dashboard/          # Dashboard V2 (FastAPI + htmx + Alpine.js)
│   │       ├── backend/        # HTMX routers + env management
│   │       │   └── routers/    # HTML routers: events, heuristics, fires, logs, etc.
│   │       ├── frontend/       # HTML/CSS/JS, Jinja2 components
│   │       └── tests/          # API tests (52 tests)
│   │
│   └── db/
│       └── migrations/         # PostgreSQL schema (shared, not memory-owned)
│
├── cli/                        # Service management scripts (thin wrappers over gladys_client)
│   ├── local.py                # Manage local services
│   ├── docker.py               # Manage Docker services
│   ├── proto_gen.py            # Generate proto stubs for all services
│   ├── _service_base.py        # Shared service management framework
│   ├── _local_backend.py       # Local service start/stop/status
│   ├── _docker_backend.py      # Docker service management
│   ├── _cache_client.py        # Cache CLI (re-exports from gladys_client.cache)
│   ├── _health_client.py       # Health CLI (re-exports from gladys_client.health)
│   ├── _db.py                  # DB CLI (re-exports from gladys_client.db)
│   ├── _sync_check.py          # Proto/migration sync verification
│   ├── _gladys.py              # Shared config (ports, utils)
│   └── convergence_test.py     # PoC 1 convergence test (10-step integration test)
│
├── src/sensors/
│   └── runescape/              # RuneScape sensor driver (Java RuneLite plugin, 1596 test events)
│
├── packs/                      # Plugin packs (formerly plugins/)
│   ├── sensors/                # Sensor packs (exploratory, pre-protocol — PoC 2 rewrites all)
│   │   ├── calendar-sensor/    # Google Calendar (Python, exploratory)
│   │   ├── melvor-sensor/      # Melvor Idle game (Python, exploratory)
│   │   └── sudoku-sensor/      # Sudoku (Python, exploratory)
│   ├── skills/                 # Skill packs
│   ├── personalities/          # Personality packs
│   └── outputs/                # Output/actuator packs
│
├── sdk/
│   ├── java/gladys-sensor-sdk/   # Java sensor SDK (gRPC client, event builder, heartbeat)
│   └── js/gladys-sensor-sdk/     # TypeScript sensor SDK (same API, ts-proto + grpc-tools)
│
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests + docker-compose.yml
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
| response_text | TEXT | Executive/heuristic response |
| response_id | TEXT | Links to executive response |
| predicted_success | FLOAT | Success prediction score |
| prediction_confidence | FLOAT | Confidence in prediction |
| archived | BOOLEAN | Soft delete flag (default false) |

### `heuristic_fires` (Flight Recorder)
| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| heuristic_id | UUID | FK to heuristics (CASCADE delete) |
| event_id | TEXT | Triggering event |
| fired_at | TIMESTAMPTZ | When fired (default NOW()) |
| outcome | TEXT | 'success', 'fail', 'unknown' (default 'unknown') |
| feedback_source | TEXT | 'explicit', 'implicit', NULL if no feedback yet |
| feedback_at | TIMESTAMPTZ | When feedback was received |
| episodic_event_id | UUID | FK to episodic_events (SET NULL on delete) |

---

## Logging and Observability

### Trace ID Propagation
All services propagate trace IDs via gRPC metadata for request correlation:

```
Header: x-gladys-trace-id
Format: 12 hex characters (e.g., "abc123def456")
```

Flow: Orchestrator generates → Rust receives and forwards → Python receives and logs

### Log File Locations

| Environment | Location | Notes |
|-------------|----------|-------|
| Local | `~/.gladys/logs/<service>.log` | Auto-configured by local.py |
| Docker | Container stdout | Use `docker-compose logs` or UI Logs tab |

Local services automatically get `LOG_FILE` set with `LOG_FILE_LEVEL=DEBUG` for troubleshooting.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level (DEBUG, INFO, WARN, ERROR) |
| `LOG_FORMAT` | `human` | Output format (`human` or `json`) |
| `LOG_FILE` | (auto for local) | Path to log file |
| `LOG_FILE_LEVEL` | `DEBUG` (local) | Level for file output |

### Logging Implementation

| Service | Module | Framework |
|---------|--------|-----------|
| Python services | `gladys_common.logging` | structlog |
| Rust services | `src/services/salience/src/logging.rs` | tracing |

See `docs/design/LOGGING_STANDARD.md` for full specification.

---

## Learning Module

**Location**: `src/services/orchestrator/gladys_orchestrator/learning.py`
**Integrated in**: `router.py` (via `LearningModule`), `server.py` (creation + cleanup loop)

Facade that consolidates all learning-related operations behind a clean interface. The router only interacts with `LearningModule` for learning operations — not directly with `outcome_watcher` or `memory_client` for learning purposes.

### Implicit Feedback Signals

| Signal | Meaning | Implementation |
|--------|---------|----------------|
| **Timeout** | No complaint within timeout → positive | `cleanup_expired()` sends positive feedback for expired outcome expectations |
| **Undo within 60s** | User undid the action → negative | `_check_undo_signal()` detects undo keywords in events within 60s of a fire |
| **Ignored 3x** | Heuristic fired 3 times without engagement → negative | `on_heuristic_ignored()` tracks consecutive ignores per heuristic |
| **Outcome pattern** | Expected event observed → positive/negative | Delegates to `OutcomeWatcher.check_event()` |

### Interface

| Method | Purpose |
|--------|---------|
| `on_feedback()` | Handle explicit feedback (user thumbs up/down) |
| `on_fire()` | Register heuristic fire (flight recorder + outcome watcher) |
| `on_outcome()` | Handle implicit feedback signal |
| `check_event_for_outcomes()` | Check incoming event for outcome matches + undo signals |
| `on_heuristic_ignored()` | Track ignored suggestions (3x = negative) |
| `cleanup_expired()` | Timeout handling + positive feedback + stale fire cleanup |

### Integration Points

| Location | What Happens |
|----------|--------------|
| `router.py` | Every incoming event checked via `learning_module.check_event_for_outcomes()` |
| `router.py` | Heuristic fires registered via `learning_module.on_fire()` |
| `server.py` | LearningModule created with memory_client + outcome_watcher |
| `server.py` | Cleanup loop calls `learning_module.cleanup_expired()` every 30s |

### OutcomeWatcher (Internal)

**Location**: `src/services/orchestrator/gladys_orchestrator/outcome_watcher.py`

Internal dependency of LearningModule. Watches for pattern-based outcome events after heuristic fires.

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

**Location**: `src/services/dashboard/`
**Framework**: FastAPI + htmx + Alpine.js
**Port**: 8502
**Design docs**:
- `docs/design/DASHBOARD_V2.md` — overall design
- `docs/design/DASHBOARD_COMPONENT_ARCHITECTURE.md` — rendering patterns

The dashboard provides a dev/debug interface for GLADyS with tabs for event simulation (Lab), response history (Response), heuristic management (Heuristics), fire history (Learning), LLM testing (LLM), log viewing (Logs), and configuration (Settings). Uses Server-Sent Events (SSE) for real-time event updates.

### Dual-Router Architecture (CRITICAL)

The dashboard has **two router layers** mounted in the same FastAPI app:

| Layer | Location | Returns | Purpose |
|-------|----------|---------|---------|
| **HTMX routers** | `src/services/dashboard/backend/routers/` | HTML | Server-side rendered partials for htmx |
| **JSON routers** | `src/services/fun_api/routers/` | JSON | REST API for programmatic access |

**IMPORTANT**: `fun_api/` is a **separate directory** at `src/services/fun_api/` (sibling to `dashboard/`). The dashboard imports it via `from fun_api.routers import ...`.

**Router Inventory**:

```
src/services/dashboard/backend/routers/   # HTML responses (htmx Pattern A)
├── events.py              # Event table, SSE stream, feedback
├── responses.py           # Response history table
├── services.py            # Service health rows
├── metrics.py             # Metrics strip
├── heuristics.py          # Heuristic rows (HTML)
├── fires.py               # Fire history rows (HTML)
└── logs.py                # Log lines (HTML)

src/services/fun_api/routers/             # JSON responses (REST API)
├── heuristics.py          # Heuristic CRUD (JSON)
├── cache.py               # Rust cache stats/flush
├── fires.py               # Heuristic fire history (JSON)
├── llm.py                 # Ollama status/test
├── logs.py                # Service log retrieval (JSON)
├── memory.py              # Memory probe
├── config.py              # Environment config
├── events.py              # Event operations (JSON)
└── services.py            # Service status (JSON)
```

**main.py imports and mounts BOTH** (`src/services/dashboard/backend/main.py`):
```python
# HTMX routers (HTML) - from dashboard/backend/
from backend.routers import events, fires, heuristics, logs, ...
app.include_router(events.router)  # HTML

# JSON routers - from sibling fun_api/ directory
from fun_api.routers import heuristics, cache, fires, logs, ...
app.include_router(heuristics.router)  # JSON
```

### Rendering Patterns

See `docs/design/DASHBOARD_COMPONENT_ARCHITECTURE.md` for full details.

**Pattern A (server-side rendering)** — for data lists:
- Backend renders HTML with Jinja `{% for %}` loops
- htmx fetches pre-rendered HTML
- Alpine.js only for row-level interactivity (expansion, editing)
- **Used by**: All tabs (Lab, Response, Heuristics, Learning, Logs, LLM, Settings)

**Pattern B (Alpine-only)** — for UI controls:
- Static HTML with Alpine.js reactivity
- No data rendering, only toggles/modals/dropdowns
- **Used by**: Toolbar filters, sidebar controls

**Anti-pattern (DO NOT USE)**:
- Alpine x-for for server data in htmx-loaded content
- htmx + x-for doesn't work reliably (x-for may not render DOM)

### Data Access Paths

**JSON path** (for REST API consumers):
```
Dashboard UI → fun_api/routers/heuristics.py → gRPC QueryHeuristics → Memory → DB
                                             ↘ Direct DB delete (tech debt #83)
```

**HTML path** (for htmx — Pattern A):
```
Dashboard UI → backend/routers/heuristics.py → gRPC QueryHeuristics → Memory → DB
               (returns rendered HTML via Jinja templates)

Dashboard UI → backend/routers/fires.py → gRPC ListFires → Memory → DB
Dashboard UI → backend/routers/logs.py → file read (no gRPC)
```

### Key Files

**Dashboard (HTML routers)** — `src/services/dashboard/`:
| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, mounts both router layers |
| `backend/env.py` | Environment singleton, gRPC channel management |
| `backend/routers/events.py` | Event CRUD, SSE stream, feedback, delete (HTML) |
| `backend/routers/responses.py` | Response history (HTML) |
| `backend/routers/heuristics.py` | Heuristic rows (HTML) |
| `backend/routers/fires.py` | Fire history rows (HTML) |
| `backend/routers/logs.py` | Log lines (HTML) |
| `frontend/index.html` | Layout shell with static sidebar |
| `frontend/components/*.html` | Jinja2 partials for tabs |

**FUN API (JSON routers)** — `src/services/fun_api/`:
| File | Purpose |
|------|---------|
| `routers/heuristics.py` | Heuristic CRUD (JSON) |
| `routers/fires.py` | Fire history (JSON) |
| `routers/logs.py` | Log retrieval (JSON) |
| `routers/cache.py` | Rust cache stats/flush |
| `routers/llm.py` | Ollama status/test |

**Shared** — `src/lib/gladys_client/`:
| File | Purpose |
|------|---------|
| `db.py` | All DB queries (events, heuristics, fires, metrics) |

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
   COPY src/lib/gladys_common/pyproject.toml ./common/pyproject.toml
   COPY src/lib/gladys_common/gladys_common ./common/gladys_common
   ```

3. **Strip uv.sources and fix path** before installing:
   ```dockerfile
   RUN sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
       sed -i 's/"gladys-common",/"gladys-common @ file:\/\/\/app\/common",/' pyproject.toml && \
       pip install -e ./common && \
       pip install -e .
   ```

**Services currently using gladys_common**:
- `src/services/orchestrator/` (router.py, __main__.py)
- `src/services/memory/` (grpc_server.py)

### 2. Local Path Dependencies in pyproject.toml

Files with `[tool.uv.sources]` sections that specify local paths:
- `src/services/orchestrator/pyproject.toml` → `gladys-common = { path = "../common" }`
- `src/services/memory/pyproject.toml` → `gladys-common = { path = "../../common" }`

These paths work locally but NOT in Docker unless handled as shown above.

### 3. Transitive Dependencies

Some packages may not install all their transitive dependencies correctly. Known examples:
- `huggingface-hub` and `sentence-transformers` require `requests` but it may not be auto-installed via uv
- **Fix**: Add explicit dependency in pyproject.toml: `"requests>=2.28"`

### 4. Verification After Changes

After modifying Dockerfiles or dependencies:
```bash
# Rebuild with no cache to catch issues
python cli/docker.py build <service> --no-cache

# Check packages in container
docker run --rm --entrypoint pip <image> freeze | grep <package>

# Run tests
python cli/docker.py test
```

### 5. Proto Files and Build Contexts

Proto files live at `proto/` (project root), but Dockerfiles have DIFFERENT build contexts:

| Service | Dockerfile | Build Context | Proto Access |
|---------|------------|---------------|--------------|
| memory-python | `src/services/memory/Dockerfile` | Project root | Uses pre-committed stubs |
| memory-rust | `src/services/salience/Dockerfile` | Project root | Needs `proto/` in context |
| orchestrator | `src/services/orchestrator/Dockerfile` | Project root | Needs `proto/` in context |
| executive | `src/services/executive/Dockerfile` | Project root | Needs `proto/` in context |

**Proto change problems:**
- Health RPCs return `UNIMPLEMENTED` → Docker image has old proto stubs
- Services show "running (healthy)" but gRPC health fails → Image needs rebuild

**Solution:**
```bash
docker compose -f docker/docker-compose.yml build --no-cache memory-rust
python cli/docker.py restart memory-rust
```

### 6. Python Services with Volume Mounts

memory-python and orchestrator have source mounted as volumes in `docker-compose.yml`:
```yaml
volumes:
  - ../memory/python/gladys_memory:/app/gladys_memory:ro
```

Python code changes are picked up WITHOUT rebuild. But:
- Proto stub changes still require rebuild (stubs are in generated/ dirs)
- `--force-recreate` recreates containers but doesn't rebuild images

---

## Database Schema Management

**CRITICAL**: Local and Docker databases must stay in sync unless you have a specific reason to diverge.

### How It Works
- Migrations live in `src/db/migrations/` (numbered .sql files)
- Both `cli/local.py start` and `cli/docker.py start` run migrations automatically
- Use `--no-migrate` only if you intentionally need different schemas

### When Adding/Modifying Schema
1. Create migration in `src/db/migrations/` with next number (e.g., `009_new_feature.sql`)
2. Use `IF NOT EXISTS` / `IF EXISTS` for idempotency
3. Run `python cli/local.py migrate` to apply locally
4. Run `python cli/docker.py migrate` to apply to Docker
5. **Both environments must have the same schema** — if you skip one, document why in working_memory.md

### Red Flags
- Test fails with "column does not exist" → migration not applied
- Different behavior between local and Docker → schema drift
- **Never assume migrations are applied** — verify with `\d tablename` in psql if unsure

---

## Common Mistakes to Avoid

1. **Port confusion**: MemoryStorage is 50051, SalienceGateway is 50052. They're different!
2. **Assuming keyword matching**: Heuristics use embedding similarity, not word overlap
3. **source vs origin**: `source` is the event sensor, `origin` is how the heuristic was created
4. **source_filter misuse**: Filters by condition_text PREFIX (e.g., "minecraft:..."), NOT by event.source
5. **Stale stubs**: After editing `proto/*.proto`, run `python cli/proto_gen.py` to regenerate
6. **Docker ports**: Add 10 to local ports (50051 → 50061)
7. **Missing trace IDs**: Always extract/propagate `x-gladys-trace-id` from gRPC metadata
8. **Fire-and-forget tasks**: `asyncio.create_task()` without error handling silently drops exceptions
9. **gRPC channel leaks**: Always close channels or use a managed client class
10. **Async lock scope**: If using `asyncio.Lock`, protect ALL access points, not just some
11. **Adding gladys_common import without Dockerfile update**: If you add `from gladys_common import ...` to a service, the Dockerfile MUST be updated (see Docker Build Requirements above)
12. **Using local context for services with shared deps**: docker-compose.yml must use project root context (`../..`) for any service that depends on gladys_common
13. **Dashboard router confusion**: `dashboard/backend/routers/` returns HTML (htmx), `fun_api/routers/` returns JSON (REST API). Both are mounted in `main.py`. Check which you need before modifying.
14. **Using Alpine x-for for server data in htmx content**: x-for doesn't reliably render when content is loaded via htmx. Use Jinja loops (Pattern A) instead. See `DASHBOARD_COMPONENT_ARCHITECTURE.md`.
15. **fun_api location confusion**: `fun_api/` is at `src/services/fun_api/` (sibling to `dashboard/`), NOT inside the dashboard directory. The dashboard imports it via `from fun_api.routers import ...`.
16. **JSON vs HTML endpoints**: Both exist for many entities. JSON: `fun_api/routers/heuristics.py`. HTML: `dashboard/backend/routers/heuristics.py`. htmx tabs need HTML routers.

---

## Troubleshooting

### "No immediate response" in UI despite services running

**Symptoms**: Event submitted in UI shows "(No immediate response)" even though all services show healthy.

**Diagnostic steps**:

1. **Run the integration test**:
   ```bash
   uv run python tests/integration/test_llm_response_flow.py
   ```
   This tests Executive directly AND through Orchestrator. If both pass, the issue is in the UI.

2. **Check LLM configuration**:
   ```bash
   python cli/local.py status
   ```
   Look for the `ollama` line - it should show `[OK] running` with your model name.

3. **Verify named endpoint resolution**: The Executive uses named endpoints. If you changed `.env` to use `OLLAMA_ENDPOINT=local`, the Executive MUST be restarted to pick up the change:
   ```bash
   python cli/local.py restart executive-stub
   ```

**Root causes** (in order of likelihood):

| Cause | Check | Fix |
|-------|-------|-----|
| Executive not restarted after config change | `status` shows wrong model | `restart executive-stub` |
| Salience too low (event queued) | UI shows "QUEUED" path | Select "Force HIGH (Immediate)" in UI or wait for async processing |
| Named endpoint not resolved | Executive startup doesn't show Ollama URL | Check `.env` has `OLLAMA_ENDPOINT_<NAME>` matching `OLLAMA_ENDPOINT` |
| Ollama unreachable | `status` shows `[--] unreachable` | Start Ollama or fix URL |
| Wrong environment selected | UI sidebar shows "Docker" | Switch to "Local" in UI sidebar |

**Key insight**: The Executive reads `.env` at startup and resolves named endpoints then. Changing `.env` has no effect until restart. This is different from the scripts which re-read `.env` on every invocation.

### Services fail to start

**"Address already in use"**: Another instance is running. Use `local.py stop all` first or check for zombie processes.

**"Connection refused" on health check**: Service crashed immediately after starting. Run in foreground to see errors:
```bash
python -m gladys_executive start  # instead of via local.py
```

### Database schema issues

**"column does not exist"**: Migration not applied. Run:
```bash
python cli/local.py migrate
```

**Different behavior local vs Docker**: Schema drift. Ensure both use same migrations:
```bash
python cli/local.py migrate
python cli/docker.py migrate
```

---

## Quick Commands

```bash
# Start all services locally
python cli/local.py start all

# Check status (process-level)
python cli/local.py status

# Check health (gRPC-level)
python cli/local.py health
python cli/local.py health -d    # detailed with uptime/metrics

# Regenerate proto stubs after editing proto/
python cli/proto_gen.py

# Cache management
python cli/local.py cache stats
python cli/local.py cache list
python cli/local.py cache flush

# Run integration tests
cd tests/integration && uv run pytest -v

# Database query
python cli/local.py query "SELECT * FROM heuristics LIMIT 5"
```

---

## See Also

- `docs/INDEX.md` - Documentation map (find docs by concept)
- `docs/design/DESIGN.md` - Living design doc (current implementation)
- `src/services/memory/README.md` - Memory subsystem details
- `src/services/orchestrator/README.md` - Event routing details
- `src/services/executive/README.md` - LLM integration details
- `docs/adr/` - Architecture decisions
- `docs/design/questions/` - Active design discussions
- `docs/design/SENSOR_ARCHITECTURE.md` - PoC 2 sensor protocol and SDK design
- `docs/design/LOGGING_STANDARD.md` - Logging and observability specification
- `sdk/java/gladys-sensor-sdk/README.md` - Java sensor SDK
- `sdk/js/gladys-sensor-sdk/README.md` - TypeScript sensor SDK
