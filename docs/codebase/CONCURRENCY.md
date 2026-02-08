# Concurrency Model


## Overview

| Component | Runtime | Event Loop | gRPC Mode | Thread Model |
|-----------|---------|------------|-----------|--------------|
| **Orchestrator** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded + ThreadPoolExecutor for gRPC |
| **Memory Python** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Memory Rust** | Tokio | Multi-threaded Tokio runtime | Tonic (async) | Tokio work-stealing |
| **Executive** | Python asyncio | Single via `asyncio.run()` | `grpc.aio` (async) | Single-threaded |
| **Dashboard** | FastAPI (uvicorn) | asyncio | REST/SSE | Single-threaded + background gRPC thread for SSE |

## Orchestrator Concurrency

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

## Dashboard Concurrency (V2 -- FastAPI)

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

## Rust Memory (Tokio)

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

## Sync/Async Boundaries

| Caller | Callee | Boundary |
|--------|--------|----------|
| Orchestrator (async) | Memory Python (async) | Clean - both async |
| Orchestrator (async) | Memory Rust (async) | Clean - both async |
| Dashboard (FastAPI async) | Orchestrator (async) | Sync gRPC in background threads |

## Message Queues

| Queue | Type | Location | Purpose |
|-------|------|----------|---------|
| `asyncio.Queue` | In-memory | `router.py` Subscriber.queue | Event delivery to subscribers |
| `asyncio.Queue` | In-memory | `router.py` ResponseSubscriber.queue | Response delivery to subscribers |
| `asyncio.Queue` | In-memory | `events.py` response_queue | SSE gRPC thread -> async SSE generator |

No external message queues (Redis, RabbitMQ, etc.) are used. All queues are in-process.

## Known Concurrency Issues

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Fire-and-forget | `router.py:115` | HIGH | `asyncio.create_task()` without error callback |
| Race condition | `outcome_watcher.py` | HIGH | `_pending` list modified without lock |
| SSE race condition | `events.py:341-357` | LOW | Mitigated with retry+backoff; store_callback may not commit before broadcast |
