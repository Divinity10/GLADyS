# ADR-0005: gRPC Service Contracts

| Field | Value |
|-------|-------|
| **Status** | Approved |
| **Date** | 2026-01-25 |
| **Updated** | 2026-02-13 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Contracts |
| **Tags** | grpc, api, transport, timeouts |
| **Depends On** | ADR-0001, ADR-0003, ADR-0004 |

---

## 1. Context and Problem Statement

GLADyS consists of multiple components written in different languages (Python orchestrator/sensors/salience/memory,
C# executive, Rust memory fast-path). These components must communicate reliably with low latency.

This ADR defines the gRPC service contract **principles**, communication patterns, and supporting infrastructure
(auth, tracing, error handling).

**Canonical source:** Actual proto definitions live in `proto/*.proto`. This ADR captures architectural decisions
and high-level patterns only.

---

## 2. Decision Drivers

1. **Latency:** Total budget ~1000ms; inter-component communication must be fast
2. **Polyglot:** Must work across Rust, Python, and C#
3. **Type safety:** Contracts should catch errors at compile time where possible
4. **Extensibility:** New sensors and skills without contract changes
5. **Observability:** Tracing and logging built-in from day one
6. **Future-proofing:** Prepare for distributed deployment without major refactoring

---

## 3. Communication Topology

### 3.1 Component Relationships

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR (Python)                            │
│                                                                          │
│   • Message broker (pub/sub fan-out)                                     │
│   • Lifecycle management                                                 │
│   • Health monitoring                                                    │
│   • Service registry                                                     │
└──────────────────────────────────────────────────────────────────────────┘
       │              │                │                │
       │ gRPC         │ gRPC           │ gRPC           │ gRPC
       │ bidir        │                │                │
       ▼              ▼                ▼                ▼
┌────────────┐  ┌───────────────┐  ┌────────────┐  ┌────────────┐
│  SENSORS   │  │   SALIENCE    │  │ EXECUTIVE  │  │  OUTPUTS   │
│  (Python)  │  │   GATEWAY     │  │   (C#)     │  │  (Python)  │
│            │  │   (Python)    │  │            │  │            │
│ Audio      │  │               │  │            │  │ TTS        │
│ Visual     │  │ ┌───────────┐ │  │            │  │            │
│ Minecraft  │  │ │  MEMORY   │ │  │            │  │            │
│            │  │ │CONTROLLER │ │  │            │  │            │
│            │  │ └───────────┘ │  │            │  │            │
└────────────┘  └───────────────┘  └────────────┘  └────────────┘
                       │                  │
                       │◄─────────────────┘
                       │ Direct query (Memory Controller)
```

### 3.2 Message Flow Patterns

| Flow | Pattern | Routing |
|------|---------|---------|
| Sensor → Salience | Pub/Sub via Orchestrator | Parallel fan-out |
| Sensor → Orchestrator (logging) | Pub/Sub | Same event, parallel subscriber |
| Salience → Executive | Unary | Direct routing via Orchestrator |
| Executive → Memory | Unary | Direct to Memory Controller |
| Executive → Output | Unary + Status Stream | Direct + async notify to Orchestrator |
| Orchestrator → Any | Unary | Lifecycle commands |

### 3.3 Pub/Sub Fan-Out

When a sensor emits an event, Orchestrator delivers to all subscribers in parallel:

```
Sensor emits event
        │
        ▼
   Orchestrator
        │
        ├──► Salience Gateway (processes event)
        │         │
        │         └──► Executive (if salient)
        │
        └──► Orchestrator log (records event)
```

Salience Gateway does not wait for Orchestrator logging. Both receive simultaneously.

---

## 4. Service Contract Principles

**Canonical definitions:** See `proto/*.proto` for exact message structures and field definitions.

### 4.1 Package Structure

```
gladys/
├── v1/
│   ├── common.proto           # Shared messages (Event, RequestMetadata, ComponentStatus, etc.)
│   ├── orchestrator.proto     # Orchestrator service (event routing, lifecycle, health)
│   ├── sensor.proto           # Sensor service (registration, control)
│   ├── salience.proto         # Salience Gateway service
│   ├── memory.proto           # Memory Controller service
│   ├── executive.proto        # Executive service
│   └── output.proto           # Output service
```

### 4.2 Common Message Patterns

**All RPCs include:**

- `RequestMetadata` with `request_id`, `trace_id`, `span_id`, `timestamp_ms`, `source_component`
- Standard error handling via `ErrorDetail` message

**Event structure:**

- `id` (UUID), `timestamp`, `source` (sensor ID)
- `raw_text` (natural language), `structured` (domain-specific JSON via google.protobuf.Struct)
- `salience` (populated by Salience Gateway), `entity_ids` (populated by Entity Extractor)

**Component status:**

- `ComponentState` enum: UNKNOWN, STARTING, ACTIVE, PAUSED, STOPPING, STOPPED, ERROR, DEAD
- `ComponentStatus` message with `component_id`, `state`, `message`, `last_heartbeat`

### 4.3 Orchestrator Service (proto/orchestrator.proto)

**Event Routing:**

- `PublishEvent` / `PublishEvents` - Sensors publish events (unary or batch)
- `SubscribeEvents` - Components subscribe to receive events (streaming)
- `SubscribeResponses` - Subscribe to executive responses (streaming)
- `FlushMoment` - Manual moment accumulator flush (testing/evaluation)

**Component Lifecycle:**

- `RegisterComponent` - Component registration with orchestrator
- `UnregisterComponent` - Graceful shutdown
- `SendCommand` - Send lifecycle commands (START, STOP, PAUSE, RESUME, RELOAD, RECOVER, HEALTH_CHECK)

**Health & Status:**

- `Heartbeat` - Periodic heartbeats with minimal payload (sensor_id, state) + command delivery via
  `HeartbeatResponse.pending_commands`
- `GetSystemStatus` - Query all component statuses

**Service Discovery:**

- `ResolveComponent` - Resolve component address by ID

**Key architectural decision:** Pull-based command delivery via `HeartbeatResponse.pending_commands` follows Kubernetes/AWS Systems Manager pattern.

### 4.4 Sensor Service (proto/sensor.proto)

**Not used in current architecture.** Sensors communicate via `OrchestratorService` only.

Future consideration: If sensors expose gRPC endpoints, define `SensorService` for direct control (push-based commands).

### 4.5 Salience Gateway Service (proto/salience.proto)

**Salience Evaluation:**

- `EvaluateSalience` - Evaluate event salience, return `SalienceVector` (threat, opportunity, humor, novelty,
  goal_relevance, social, emotional, actionability, habituation)

**Heuristic Management:**

- Query, create, update heuristics (rule-based salience shortcuts)

### 4.6 Memory Controller Service (proto/memory.proto)

**Query:**

- `Query` - Semantic search via pgvector
- `QueryByEntity` - Find memories associated with entity

**Store:**

- `Store` - Store memory (L1-L4 routing based on importance/consolidation)

**Entity Management:**

- `GetEntity`, `CreateEntity`, `UpdateEntity` - Entity lifecycle

### 4.7 Executive Service (proto/executive.proto)

**Response Generation:**

- `GenerateResponse` - LLM-based response generation
- `StreamResponse` - Streaming response generation

**Skill Execution:**

- `ExecuteSkill` - Execute registered skill (Python/C# extension)

### 4.8 Output Service (proto/output.proto)

**Audio Output:**

- `SynthesizeSpeech` - TTS synthesis
- `StreamAudio` - Streaming audio output

---

## 5. Transport Strategy

**Decision:** HTTP/2 for all gRPC communication

**Why:**

- Multiplexing: Multiple requests over single connection (lower latency)
- Bidirectional streaming: Pub/sub and status streams
- Header compression: Reduces overhead for repeated metadata
- Flow control: Built-in backpressure

**Implementation:**

- Python: `grpcio`
- C#: `Grpc.Net.Client` / `Grpc.AspNetCore`
- Rust: `tonic`

---

## 6. Timeout Budget

Total latency budget: **~1000ms** (from sensor event → executive response → TTS output)

| Operation | Timeout | Notes |
|-----------|---------|-------|
| Event publish (sensor → orchestrator) | 100ms | Fast ack, queued for processing |
| Salience evaluation | 200ms | Heuristic fast path <10ms, LLM fallback <200ms |
| Executive response generation | 500ms | Streaming starts earlier, full generation <500ms |
| Memory query | 100ms | L0-L2 fast, L3-L4 may be slower |
| TTS synthesis | 200ms | Piper fast (~50ms), Bark slower (~500ms) |
| Heartbeat | 5000ms | Low priority, 30-60s interval |
| Component registration | 10000ms | One-time, can be slower |

**Circuit breaker:** After 3 consecutive timeouts, component marked ERROR and orchestrator triggers recovery.

---

## 7. Error Handling

**Standard error format:**

```protobuf
message ErrorDetail {
    string code = 1;                // Machine-readable error code
    string message = 2;             // Human-readable message
    map<string, string> metadata = 3;
}
```

**Error codes:**

- `TIMEOUT` - Operation exceeded deadline
- `UNAVAILABLE` - Component not reachable
- `PERMISSION_DENIED` - Security policy violation
- `INVALID_ARGUMENT` - Malformed request
- `RESOURCE_EXHAUSTED` - Queue full, backpressure triggered
- `INTERNAL` - Unexpected error

**Retry policy:**

- Idempotent operations (queries, GET): Retry with exponential backoff (50ms, 100ms, 200ms)
- Non-idempotent (commands, POST): No automatic retry, return error to caller
- Streaming: Reconnect with jitter on disconnect

**Client-side:**

- Log error with `request_id` and `trace_id` for correlation
- Propagate error to orchestrator for health monitoring
- Trigger circuit breaker after 3 consecutive failures

---

## 8. Security

**Phase 1 (PoC):** No authentication (localhost-only deployment)

**Phase 2:** Mutual TLS (mTLS)

- Each component has certificate signed by GLADyS CA
- Orchestrator validates client certificates
- Prevents unauthorized components from joining

**Phase 3:** Token-based auth

- JWT tokens for remote sensors
- Short-lived tokens (15 min), refreshable
- Permission scopes (read-only sensors, admin dashboards)

**Memory access:**

- Executive → Memory: Direct gRPC call (trusted)
- Sensors → Memory: Prohibited (sensors publish events, not direct memory writes)
- Outputs → Memory: Read-only via Memory Controller

**Sensitive data handling:**

- Credentials in events: Stripped by orchestrator before storage
- PII: Redacted unless user consents (ADR-0008)
- Encryption at rest: PostgreSQL transparent data encryption (future)

---

## 9. Observability

**OpenTelemetry integration:**

- All RPCs emit traces automatically (gRPC interceptors)
- `trace_id` propagated via `RequestMetadata`
- Spans: `sensor.publish_event`, `orchestrator.route`, `salience.evaluate`, `executive.generate_response`

**Metrics:**

- RPC latency histograms (P50, P95, P99)
- Error rates by service and RPC
- Queue depths (orchestrator event queue, salience queue)
- Component health (heartbeat intervals, uptime)

**Logging:**

- Structured JSON logs
- Include `request_id`, `trace_id`, `component_id` in every log line
- Log levels: DEBUG (local dev), INFO (production), ERROR (always)

**Correlation:**

- `request_id` links all logs for a single event → response cycle
- `trace_id` links distributed traces across services

---

## 10. Versioning

**Strategy:** Additive changes only (protobuf guarantees backward compatibility)

**Allowed:**

- Add new RPC methods
- Add new optional fields to existing messages
- Add new enum values (with `UNSPECIFIED = 0` default)

**Forbidden:**

- Remove or rename fields
- Change field types
- Change field numbers

**Breaking changes:**

- Require new package version (`gladys.v2`)
- Old and new versions coexist during migration
- Orchestrator routes requests based on client version

**Field deprecation:**

```protobuf
string old_field = 3 [deprecated = true];  // Still present, not used
string new_field = 4;                      // Replacement
```

**Version negotiation:**

- Components declare supported versions in `RegisterComponent`
- Orchestrator refuses incompatible clients
- Dashboard shows version mismatches in component status

---

## 11. Alternatives Considered

### 11.1 REST/HTTP JSON

**Pros:** Simple, widely understood, easy debugging (cURL)
**Cons:** No streaming, no type safety, higher latency (JSON overhead)
**Rejected:** Latency budget too tight for JSON serialization

### 11.2 ZeroMQ

**Pros:** Very low latency (~10μs), simple
**Cons:** No type safety, no built-in tracing, manual connection management
**Rejected:** Lack of type safety risky for polyglot system

### 11.3 Apache Thrift

**Pros:** Similar to gRPC, polyglot
**Cons:** Less active ecosystem, no streaming, weaker tooling
**Rejected:** gRPC has better Python/C#/Rust support

### 11.4 Cap'n Proto

**Pros:** Zero-copy, extremely fast
**Cons:** Immature tooling, small ecosystem
**Rejected:** Too experimental for production system

---

## 12. Consequences

### 12.1 Benefits

1. **Type safety:** Proto compiler catches contract violations at build time
2. **Performance:** HTTP/2 multiplexing + protobuf binary reduces latency
3. **Observability:** Built-in tracing via interceptors
4. **Extensibility:** New RPCs and fields without breaking existing clients
5. **Polyglot:** Python, C#, Rust interop with minimal glue code

### 12.2 Drawbacks

1. **Learning curve:** Team must learn protobuf syntax and gRPC patterns
2. **Debugging:** Binary protocol harder to inspect than JSON (use grpcurl)
3. **Streaming connections require connection management

### 12.3 Risks

1. Proto versioning mistakes could cause incompatibilities
2. Timeout tuning may need adjustment based on real usage
3. Circuit breaker thresholds need calibration

---

## 13. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0003: Plugin Manifest Specification
- ADR-0004: Memory Schema Details
- ADR-0006: Observability & Monitoring
- ADR-0007: Adaptive Algorithms
- ADR-0008: Security and Privacy (permission enforcement, shared memory)

---

## 14. References

**Proto definitions (canonical source):**

- `proto/common.proto` - Shared messages (Event, RequestMetadata, ComponentStatus, Entity, UserProfile)
- `proto/orchestrator.proto` - Orchestrator service (event routing, lifecycle, health, discovery)
- `proto/salience.proto` - Salience Gateway service
- `proto/memory.proto` - Memory Controller service
- `proto/executive.proto` - Executive service
- `proto/output.proto` - Output service

**Implementation guides:**

- `docs/codebase/SENSOR_CONTROL.md` - Sensor control protocol (SendCommand + Heartbeat delivery)
- `docs/codebase/TOPOLOGY.md` - Component relationships and message flows
- `docs/codebase/CONCURRENCY.md` - Threading model and async patterns

**Build configuration:**

- `buf.yaml` - Buf build config
- `buf.gen.yaml` - Code generation config

**Build commands:**

```bash
# Generate Python
buf generate --template buf.gen.python.yaml

# Generate C#
buf generate --template buf.gen.csharp.yaml

# Generate Rust
buf generate --template buf.gen.rust.yaml
```
