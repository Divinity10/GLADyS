# GLADyS Logging Standard

**Status**: IMPLEMENTED
**Author**: Claude
**Date**: 2026-01-26

---

## Purpose

Establish consistent, debuggable logging across all GLADyS services. This enables:
- Following a request across services (trace IDs)
- Quick identification of where failures occur
- Filtering logs by level, service, or trace
- File-based logs that persist beyond console sessions

---

## Log Format

### Structured JSON (Production)

All services output JSON logs for easy parsing:

```json
{
  "ts": "2026-01-26T17:30:45.123Z",
  "level": "INFO",
  "service": "memory-python",
  "trace_id": "abc123def456",
  "msg": "Heuristic query completed",
  "ctx": {
    "query_text": "oven is left on",
    "matches": 3,
    "elapsed_ms": 45
  }
}
```

### Human-Readable (Development)

For local development, a readable format:

```
2026-01-26 17:30:45.123 INFO  [memory-python] [abc123def456] Heuristic query completed matches=3 elapsed_ms=45
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO8601 | Timestamp with milliseconds |
| `level` | string | Log level (DEBUG, INFO, WARN, ERROR) |
| `service` | string | Service name (orchestrator, memory-python, memory-rust, executive) |
| `trace_id` | string | Request correlation ID (12 hex chars) |
| `msg` | string | Human-readable message |
| `ctx` | object | Optional structured context (key-value pairs) |

---

## Log Levels

Use levels consistently across all services:

| Level | When to Use | Examples |
|-------|-------------|----------|
| **ERROR** | Operation failed, requires attention | DB connection failed, gRPC error, unhandled exception |
| **WARN** | Recoverable issue, degraded operation | Cache miss, retry succeeded, fallback used |
| **INFO** | Significant checkpoints in request flow | Request received, response sent, heuristic matched |
| **DEBUG** | Detailed internals for debugging | Query parameters, intermediate results, timing |

### Level Guidelines

- **ERROR**: Something broke. A human should probably look at this.
- **WARN**: Something unexpected happened but we handled it. Worth knowing.
- **INFO**: Key milestones in request processing. Should be readable in production.
- **DEBUG**: Everything else. Off by default, enable when debugging.

**Default level**: INFO in production, DEBUG in development.

---

## Trace ID Propagation

### How It Works

1. **Origin**: Orchestrator generates trace_id when receiving external request
2. **Propagation**: trace_id passed in gRPC metadata to downstream services
3. **Logging**: Every log line includes trace_id for correlation

### gRPC Metadata Key

```
x-gladys-trace-id: abc123def456
```

### Generation

```python
import secrets
trace_id = secrets.token_hex(6)  # 12 hex chars, e.g., "abc123def456"
```

### Flow Example

```
[orchestrator] [abc123] Received event id=evt-001
[orchestrator] [abc123] Calling SalienceGateway.EvaluateSalience
[memory-rust]  [abc123] EvaluateSalience request received
[memory-rust]  [abc123] Querying Python for heuristics
[memory-python][abc123] QueryMatchingHeuristics: query="oven", matches=3
[memory-rust]  [abc123] EvaluateSalience response: salience=0.8, matched=heur-001
[orchestrator] [abc123] Event processed, matched_heuristic=heur-001
```

---

## Log Output

### File Locations

| Service | Log File |
|---------|----------|
| orchestrator | `logs/orchestrator.log` |
| memory-python | `logs/memory-python.log` |
| memory-rust | `logs/memory-rust.log` |
| executive | `logs/executive.log` |

Logs directory: `{PROJECT_ROOT}/logs/`

### Rotation

- Max file size: 10MB
- Keep last 5 rotated files
- Format: `{service}.log`, `{service}.log.1`, `{service}.log.2`, etc.

### Console Output

- Development: Human-readable format to stderr
- Production: JSON format to stderr (for container logging)

---

## Configuration

Environment variables control logging:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level |
| `LOG_FORMAT` | `human` | `human` or `json` |
| `LOG_FILE` | (none) | Path to log file (optional) |
| `LOG_FILE_LEVEL` | `DEBUG` | Level for file output (can differ from console) |

### Example Configurations

**Local development:**
```bash
LOG_LEVEL=DEBUG LOG_FORMAT=human
```

**Production:**
```bash
LOG_LEVEL=INFO LOG_FORMAT=json LOG_FILE=/var/log/gladys/service.log
```

**Debugging specific issue:**
```bash
LOG_LEVEL=INFO LOG_FILE=debug.log LOG_FILE_LEVEL=DEBUG
```

---

## Implementation

### Python Services

Use `structlog` for structured logging:

```python
# src/common/logging.py (new shared module)
import structlog
import logging
import os

def setup_logging(service_name: str):
    """Configure logging for a GLADyS service."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = os.environ.get("LOG_FORMAT", "human")

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Bind service name to all logs
    structlog.contextvars.bind_contextvars(service=service_name)

def get_logger():
    """Get a configured logger."""
    return structlog.get_logger()

def bind_trace_id(trace_id: str):
    """Bind trace_id to current context (call at request start)."""
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
```

**Usage in gRPC handler:**

```python
from common.logging import get_logger, bind_trace_id

logger = get_logger()

async def StoreHeuristic(self, request, context):
    # Extract or generate trace_id
    trace_id = dict(context.invocation_metadata()).get("x-gladys-trace-id")
    if not trace_id:
        trace_id = secrets.token_hex(6)
    bind_trace_id(trace_id)

    logger.info("StoreHeuristic request", heuristic_id=request.heuristic.id)

    try:
        result = await self._storage.store_heuristic(...)
        logger.info("StoreHeuristic success")
        return response
    except Exception as e:
        logger.error("StoreHeuristic failed", error=str(e))
        raise
```

### Rust Service

Use `tracing` crate with JSON output:

```rust
// src/logging.rs
use tracing_subscriber::{fmt, EnvFilter, layer::SubscriberExt, util::SubscriberInitExt};

pub fn setup_logging() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let fmt_layer = fmt::layer()
        .with_target(false)
        .with_thread_ids(false)
        .json();  // or .pretty() for development

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .init();
}
```

**Usage:**

```rust
use tracing::{info, warn, error, instrument, Span};

#[instrument(skip(self, request), fields(trace_id))]
async fn evaluate_salience(&self, request: Request<EvaluateSalienceRequest>) -> Result<...> {
    // Extract trace_id from metadata
    let trace_id = request.metadata()
        .get("x-gladys-trace-id")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("no-trace");

    Span::current().record("trace_id", trace_id);

    info!(event_id = %req.event_id, "EvaluateSalience request");

    let matches = self.query_storage_for_heuristics(&req.raw_text, None).await;
    info!(match_count = matches.len(), "Heuristics queried");

    // ...
}
```

---

## What Gets Logged

### Orchestrator

| Checkpoint | Level | Context |
|------------|-------|---------|
| Event received | INFO | event_id, source |
| Salience evaluated | INFO | event_id, salience_score, matched_heuristic |
| Executive called | INFO | event_id, heuristic_id |
| Event routing decision | DEBUG | event_id, route_reason |

### Memory Python

| Checkpoint | Level | Context |
|------------|-------|---------|
| gRPC request received | INFO | rpc_method |
| Query executed | DEBUG | query_type, params |
| Query result | INFO | result_count, elapsed_ms |
| gRPC response sent | INFO | success/error |

### Memory Rust (Salience Gateway)

| Checkpoint | Level | Context |
|------------|-------|---------|
| EvaluateSalience request | INFO | event_id |
| Cache hit/miss | DEBUG | cache_key, hit |
| Python query sent | DEBUG | query_text |
| Python query result | INFO | match_count |
| Salience computed | INFO | salience_score, matched_heuristic |

---

## Implementation Milestones

Each milestone has a clear verification step.

### M1: Python Logging Module (Isolation)

**Deliverable**: `src/common/logging.py` with setup_logging(), get_logger(), bind_trace_id()

**Verification**:
```python
from common.logging import setup_logging, get_logger, bind_trace_id
setup_logging("test-service")
logger = get_logger()
bind_trace_id("abc123")
logger.info("Test message", key="value")
# Should output structured log with service, trace_id, and context
```

### M2: Memory-Python Integration

**Deliverable**: memory-python gRPC handlers use new logging

**Verification**:
- Start memory-python service
- Call StoreHeuristic RPC
- See structured logs with request/response info
- Logs appear in `logs/memory-python.log`

### M3: Rust Logging

**Deliverable**: memory-rust uses tracing crate with JSON output

**Verification**:
- Start memory-rust service
- Call EvaluateSalience RPC
- See structured logs with request info
- Logs appear in `logs/memory-rust.log`

### M4: Trace ID Propagation

**Deliverable**: Trace ID flows via gRPC metadata across service boundaries

**Verification**:
- Orchestrator generates trace_id
- Rust receives it, logs it, passes to Python
- Python receives it, logs it
- All logs for one request share same trace_id

### M5: Full Integration

**Deliverable**: All services (orchestrator, memory-python, memory-rust, executive) using new logging

**Verification**:
- All services output structured logs
- All services write to log files
- Log levels configurable via LOG_LEVEL env var

### M6: Integration Test

**Deliverable**: `test_logging_trace_flow.py` - verifies trace ID appears in all service logs

**Verification**:
- Test sends request through orchestrator
- Test reads log files
- Test asserts trace_id appears in all relevant logs
- Test asserts logs are valid JSON (if LOG_FORMAT=json)

---

## Final Verification

Verified 2026-01-26:

- [x] Log format matches specification (JSON and human-readable)
- [x] All log levels used correctly (DEBUG, INFO, WARN, ERROR)
- [x] Trace IDs propagate end-to-end (x-gladys-trace-id header)
- [x] File output works (LOG_FILE env var, rotation configured)
- [x] Configuration via env vars works (LOG_LEVEL, LOG_FORMAT, LOG_FILE, LOG_FILE_LEVEL)
- [x] Integration test passes (test_trace_id_flow.py)

### Implementation Files

| Component | File |
|-----------|------|
| Python logging module | `src/common/gladys_common/logging.py` |
| Rust logging module | `src/memory/rust/src/logging.rs` |
| Memory-python integration | `src/memory/python/gladys_memory/grpc_server.py` |
| Rust server integration | `src/memory/rust/src/server.rs` |
| Orchestrator integration | `src/orchestrator/gladys_orchestrator/__main__.py` |
| Integration test | `src/integration/test_trace_id_flow.py` |
