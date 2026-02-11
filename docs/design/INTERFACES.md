# GLADyS Interface Specifications

**Status**: Living document — evolves as implementation reveals what works.
**Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md) for decisions and rationale.

This document defines the contracts between subsystems, plugin interfaces, and data structures. Developers implementing plugins or connecting subsystems should reference this file.

---

## Plugin Protocols

Each plugin type is defined as a **protocol** (language-agnostic contract), not a base class. Per-language SDKs provide composable helpers that implement the protocol. Base classes don't translate well across languages — SDKs do (see [SENSOR_ARCHITECTURE.md §3](SENSOR_ARCHITECTURE.md#3-sensor-protocol--sdks) for the full rationale).

All plugin types share a common lifecycle and health contract. The Supervisor calls `health()` uniformly on all plugin types without needing type-specific knowledge.

### Common Protocol (all plugins)

```
start() → void                   # lifecycle: initialize and begin
stop() → void                    # lifecycle: clean shutdown
health() → HealthStatus          # status reporting (used by Supervisor)
recover() → bool                 # attempt self-healing (true=recovered, false=shutdown needed)
```

### Sensor Protocol

Defined in detail in [SENSOR_ARCHITECTURE.md §3](SENSOR_ARCHITECTURE.md#3-sensor-protocol--sdks).

```
emit_events() → Event[]          # produce normalized events
start_capture(boundary) → void   # begin JSONL capture
stop_capture(boundary) → void    # stop JSONL capture
```

### Actuator Protocol

```
execute(action) → Result         # perform the action
get_state() → busy | idle | error
interrupt(priority) → bool       # whether preemption succeeded
```

### Skill Protocol

```
process(event, context) → Decision
confidence_estimate(event) → float
evaluate_outcome(episode, outcome) → OutcomeEvaluation
```

---

## OrchestratorService gRPC

Event routing RPCs defined in `proto/orchestrator.proto`.

### Event Routing

| RPC | Type | Purpose |
|-----|------|---------|
| `PublishEvent(PublishEventRequest) → PublishEventResponse` | Unary | Publish a single event (preferred for most sensors) |
| `PublishEvents(PublishEventsRequest) → PublishEventsResponse` | Unary | Publish a batch of events (high-volume sensors) |
| `StreamEvents(stream Event) → stream EventAck` | Streaming | Deprecated — retained for backward compatibility |
| `SubscribeEvents(SubscribeRequest) → stream Event` | Server-stream | Components subscribe to receive routed events |
| `SubscribeResponses(SubscribeResponsesRequest) → stream EventResponse` | Server-stream | Subscribe to response notifications (for evaluation UI) |

### Event Messages

```protobuf
message Event {
    string id = 1;
    google.protobuf.Timestamp timestamp = 2;
    string source = 3;
    string raw_text = 4;
    google.protobuf.Struct structured = 5;
    SalienceVector salience = 6;
    repeated string entity_ids = 7;
    repeated int32 tokens = 8;
    string tokenizer_id = 9;
    string matched_heuristic_id = 10;
    string intent = 11;                         // "actionable", "informational", "unknown"
    google.protobuf.Struct evaluation_data = 12; // Solution/cheat data (stripped before executive)
    RequestMetadata metadata = 15;
}

message PublishEventRequest  { Event event = 1; RequestMetadata metadata = 15; }
message PublishEventResponse { EventAck ack = 1; }
message PublishEventsRequest  { repeated Event events = 1; RequestMetadata metadata = 15; }
message PublishEventsResponse { repeated EventAck acks = 1; }
```

### EventAck

Returned for each published event. Contains routing result and optional response data.

```protobuf
message EventAck {
    string event_id = 1;
    bool accepted = 2;
    string error_message = 3;
    string response_id = 4;
    string response_text = 5;
    float predicted_success = 6;
    float prediction_confidence = 7;
    bool routed_to_llm = 8;
    string matched_heuristic_id = 9;
    bool queued = 10;
}
```

---

## OutcomeEvaluation

Returned by the skill protocol's `evaluate_outcome()`. Used by the learning module to weight Bayesian confidence updates.

```
OutcomeEvaluation {
    valence: float      # -1.0 (catastrophic) to +1.0 (ideal)
    confidence: float   # 0.0 to 1.0 — how sure the skill is about this assessment
    factors: []         # contributing factors (e.g., "storage_destroyed", "player_survived")
}
```

**Update weight**: `valence × confidence`. High-confidence catastrophic outcomes drive strong negative updates. Uncertain assessments barely move the needle.

**The `factors` list aids attribution** — tracing which decision led to the outcome, rather than blaming whichever heuristic fired most recently.

### Fallback without a skill

When no domain skill is loaded to evaluate an outcome:

1. **Explicit user feedback** (thumbs up/down) — user acts as domain expert
2. **Generic signals** — action undone within 60s (bad), suggestion ignored 3+ times (bad), no complaint within timeout (weakly good)
3. **No update** — better to learn nothing than to learn wrong

The system learns fastest in domains with skills loaded (continuous outcome evaluation) and slowest without skills (only explicit user feedback).

### Hard problems (not solved — track B)

- **Attribution**: Bad decision, bad execution, or bad luck?
- **Delayed consequences**: Immediate outcome good, downstream effects bad. When does the evaluation window close?
- **Counterfactuals**: Would the outcome have been the same without intervention?

---

## Learning Module I/O

The learning module is Orchestrator-owned with a clean boundary (see [ARCHITECTURE.md §10](ARCHITECTURE.md#10-learning-module-orchestrator-owned)).

| Input | Operation | Output |
|-------|-----------|--------|
| Actuator outcome (from channel) | Track intent→outcome completion | Health data for Supervisor |
| Explicit user feedback | Update heuristic confidence (Bayesian) | Write to Memory |
| Implicit signals (undo, ignore) | Punishment detection, confidence decay | Write to Memory |
| Episodic batch (sleep mode) | Pattern extraction → candidate heuristics | Write to Memory |

### Extraction discipline

The interface must stay clean enough to extract into a separate process later:

- Typed input messages, typed output messages, no shared mutable state with Orchestrator
- Module takes inputs and produces outputs — does not reach into Orchestrator internals
- No importing Orchestrator-internal types or state — dependency flows one direction

**Extraction spectrum**:

| Approach | When |
|----------|------|
| Learning logic inline in Orchestrator | PoC |
| Learning as a module with clean boundary | When learning code grows beyond trivial |
| Learning as a background worker (sleep mode) | When batch jobs need CPU isolation |
| Learning as a persistent subsystem (7th process) | When real-time + batch both run continuously |

Starting at row 2.

---

## Pack Directory Structure

Domain-first, not type-first. Each pack is a self-contained unit with a manifest declaring its components.

```
packs/
├── minecraft/
│   ├── sensors/
│   ├── skills/
│   ├── preprocessors/
│   ├── heuristics/
│   └── manifest.yaml
├── smart-home/
│   ├── sensors/
│   ├── skills/
│   └── manifest.yaml
├── personalities/
│   ├── murderbot/
│   │   └── manifest.yaml       # prompt modifier only
│   └── glados/
│       ├── heuristics/         # tagged origin: personality:glados
│       ├── skills/             # optional domain skills
│       └── manifest.yaml
└── core/                       # Built-in, always-loaded
    ├── sensors/
    └── skills/
```

### Pack Manifest

```yaml
name: minecraft
version: 1.0
sensors: [game_events, chat_log]
skills: [combat_advisor, build_planner]
preprocessors: [chat_parser]
heuristics: [default_combat.yaml]
personality: null  # Uses system personality
```

Runtime scans manifests to discover what to load — no hard-coded paths.