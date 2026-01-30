# Architecture Decisions — January 29, 2026

**Purpose**: Decisions made during Scott's architecture review session. Each needs Mike's buy-in before implementation.

**Status**: Draft for discussion

---

## 1. Two-Tier API: gRPC Internal, REST External

**Decision**: Use gRPC for service-to-service communication and REST for all external consumers (dashboard, CLI tools, future UIs, plugins).

**Why**: These serve different needs. gRPC gives us type safety, streaming, and performance between services we control. REST gives universal accessibility — any language, any client, no proto compilation needed.

**What this means in practice**:
- Services (Orchestrator, Memory, Salience, Executive) continue talking gRPC to each other
- The Dashboard's FastAPI REST API becomes the official external API, not just a dashboard backend
- CLI tools switch from direct gRPC to calling the REST API
- Future sensors and plugins connect via REST (or gRPC if they need streaming performance)

**What we have today**:
- Dashboard already serves REST via FastAPI (`src/dashboard/backend/`)
- Admin scripts talk gRPC directly (`scripts/_orchestrator.py`, `scripts/_health_client.py`)
- No unified external API layer

**Industry precedent**: This is standard microservice architecture (Google, Netflix, most cloud-native systems). gRPC internal + REST external is the most common pattern.

---

## 2. Single Client Library

**Decision**: Consolidate the scattered Python gRPC client code into a single shared package (`gladys_client`). Every Python consumer — app services, dashboard, scripts, tests — imports the same client code.

**Scope**: This is about eliminating duplication *within Python*, not creating cross-language client libraries. Rust and future C# services generate their own gRPC clients directly from proto files, which is standard and correct — there's no Python version of the Salience system and no Rust version of the Orchestrator. The problem is that multiple Python codebases each roll their own gRPC channel setup to talk to the same services.

**Why**: Right now, gRPC channel setup and stub management is duplicated in three Python codebases with subtle differences:

**Dashboard** (`src/dashboard/backend/env.py`):
```python
# Caches channels, creates stubs lazily, supports env switching
def _get_channel(self, address: str) -> grpc.Channel:
    if address not in self._channels:
        self._channels[address] = grpc.insecure_channel(address)
    return self._channels[address]

def orchestrator_stub(self):
    return orchestrator_pb2_grpc.OrchestratorServiceStub(
        self._get_channel(self.config.orchestrator)
    )
```

**Admin scripts** (`scripts/_orchestrator.py`):
```python
# Creates channel per call, no caching, no env awareness
def get_stub(address: str) -> orchestrator_pb2_grpc.OrchestratorServiceStub:
    channel = grpc.insecure_channel(address)
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
```

**Health checks** (`scripts/_health_client.py`):
```python
# Yet another pattern: uses context manager, adds connection timeout
with grpc.insecure_channel(address) as channel:
    grpc.channel_ready_future(channel).result(timeout=5)
```

Three patterns for the same operation. Bug fix in one doesn't fix the others. A shared `gladys_client` library consolidates this: connection management, retry logic, environment switching — written once, used everywhere.

**Industry term**: Client SDK pattern. AWS, Stripe, Twilio all ship client libraries for the same reason.

---

## 3. Six Runtime Subsystems

**Decision**: GLADyS has six runtime subsystems (services that run as processes), plus a plugin/config ecosystem around them.

| # | Subsystem | Core Responsibility | Status |
|---|-----------|-------------------|--------|
| 1 | **Orchestrator** | Event routing, scheduling, preprocessing pipeline | Exists |
| 2 | **Memory** | Storage, embeddings, semantic search | Exists |
| 3 | **Salience** | Attention filtering, heuristic cache, novelty | Exists |
| 4 | **Executive** | Reasoning, decisions, domain skill dispatch, response dispatch | Exists (stub) |
| 5 | **FUN API** | REST API (Functional Unified Nexus), dev/QA UI, SSE | Exists |
| 6 | **Supervisor** | Sensor/service health monitoring, auto-restart, alerts | New |

**Response dispatch is an Executive module, not a subsystem.** Originally proposed as a separate "Response Manager" subsystem, but this was rejected due to performance concerns — adding a service hop between the Executive and actuators adds latency, and response generation (including personality) should happen in a single LLM call, not two. Instead:

- **Personality** is a prompt modifier injected into the Executive's LLM request (e.g., "Respond in a sarcastic tone"). One LLM call, not two.
- **Actuator routing** is a dispatch table inside the Executive. Actuators advertise their capabilities and domain via a standard interface. The Executive queries the registry for matching actuators and dispatches directly.
- **Channel state** (e.g., "is TTS busy?") is reported by actuators via their interface (`get_state()`), not tracked by a separate manager.
- **Priority/preemption** is the actuator's responsibility — the Executive dispatches with a priority value, and the actuator decides whether to interrupt its current work.

**New: Supervisor** — Who watches the watchers? Single authority on component health. Runs an independent monitoring loop that calls `health()` on all registered components (via BasePlugin interface), tracks health timelines, applies restart/disable policy, and exposes status to the FUN API. Other subsystems can request on-demand health checks, but the Supervisor owns the response. May share a process with the Orchestrator as long as the code is cleanly separated. Distributing health monitoring across subsystems was rejected — it creates duplication and no single source of truth.

### Plugin Interface Composition

All plugins implement a base interface. Type-specific interfaces layer on top.

**BasePlugin** (all plugins):
- `health()` → status reporting (used by Supervisor)
- `capabilities()` → what this plugin can do
- `start()` / `stop()` → lifecycle management

**SensorPlugin** = BasePlugin + SensorInterface:
- `emit_events()` → event stream
- `get_state()` → busy/idle/error

**ActuatorPlugin** = BasePlugin + ActuatorInterface:
- `execute(action)` → result
- `get_state()` → busy/idle/error
- `interrupt(priority)` → whether preemption succeeded

**SkillPlugin** = BasePlugin + SkillInterface:
- `process(event, context)` → decision
- `confidence_estimate(event)` → float
- `evaluate_outcome(episode, outcome)` → OutcomeEvaluation (see §10)

This means the Supervisor doesn't need special knowledge of each plugin type — it calls `health()` on everything uniformly.

---

## 4. Plugin Ecosystem

**Decision**: Plugins are categorized by type, but distributed as packs (grouped by domain).

| Type | What It Is | Runtime Owner |
|------|-----------|---------------|
| **Domain Skill** | Executable reasoning capability loaded into Executive | Executive |
| **Sensor** | External data source with managed lifecycle | Orchestrator |
| **Actuator** | External action target (speech, Discord, lights) | Executive (dispatch module) |
| **Preprocessor** | Fast enrichment/normalization in hot path | Orchestrator |
| **Personality** | Config layer affecting response style, optionally reasoning | Executive (prompt modifier + optional heuristics/skills) |

**Domain Skills are not just data** — they include code that understands domain-specific events and can reason about them. A Minecraft skill knows what "player entered the Nether" *means*, can provide domain-specific confidence estimates, and can handle routine domain events without invoking the LLM. The analogy: Neo downloading kung-fu in The Matrix. It's not a reference book — it's a capability.

**Personality is a config layer, not a subsystem.** Primarily affects how decisions get expressed (tone, style, TTS voice) via prompt modifiers. However, personality packs can optionally include:

- **Heuristics** that influence reasoning (e.g., a GLaDOS personality leans into testing metaphors and references a neurotoxin module that's always offline). These are tagged by origin (e.g., `origin: 'personality:glados'`) and **disabled by default on personality swap** to prevent stale heuristics from firing under a different personality.
- **Skill plugins** (e.g., a "math geek" personality bundles a math skill). These follow the same disable-on-swap rule.
- **Fictional actuator references** for flavor (e.g., neurotoxin emitter — always reports offline via `get_state()`).

The key distinction: personality heuristics are *optional and tagged*, not mixed into the general heuristic pool. The system can cleanly enable/disable them as a group.

**Preprocessors are fast and pack-owned.** A video pack includes its own CV preprocessor that detects motion/people/objects. An email pack parses sender/subject/urgency. These run in the hot path before salience evaluation, so speed matters. The Orchestrator runs whatever preprocessor chain the event's source pack registered.

**Sensors have managed lifecycle** — dynamically loaded/unloaded, health-monitored by the Supervisor.

---

## 5. Packs: Domain-First Distribution

**Decision**: Packs group related components by domain. Pack-first directory structure, not type-first.

**Why**: A Minecraft pack has a sensor, a skill, a preprocessor, and heuristics. Scattering those across `sensors/`, `skills/`, `preprocessors/`, `heuristics/` directories forces you to look in four places for one logical unit. Grouping by domain keeps related code together.

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
└── core/                  # Built-in, always-loaded
    ├── sensors/
    └── skills/
```

**Manifest-driven discovery**: Each pack declares what it provides. The runtime scans manifests to know what to load — no hard-coded paths.

```yaml
name: minecraft
version: 1.0
sensors: [game_events, chat_log]
skills: [combat_advisor, build_planner]
preprocessors: [chat_parser]
heuristics: [default_combat.yaml]
personality: null  # Uses system personality
```

**Personalities are a separate pack type** — they're cross-cutting, not domain-specific. A user runs the Minecraft pack with the Murderbot personality or the Butler personality.

**Precedent**: This is how VS Code extensions, game mods, and browser extensions work. The pack is the installable unit.

---

## 6. Executive as Decision-Maker (Command/Dispatch)

**Decision**: The Executive decides *what* should happen and delegates *how* to specialized components. It does not execute actions itself.

**Why**: Keeps the Executive lean — it reasons and decides, period. Decouples it from knowing how speech, actuators, or skills work. New output channels (speech, smart home, etc.) can be added without changing Executive code.

**How skills fit**: Domain Skills run *under* the Executive as plugins (library calls), not beside it as peer services. The Executive gains capabilities by loading skills, like Neo downloading kung-fu. It doesn't delegate to a separate kung-fu service.

**Current state**: The Executive returns a `ProcessEventResponse` with `response_text` as a plain string:
```python
return executive_pb2.ProcessEventResponse(
    accepted=True,
    response_id=response_id,
    response_text=response_text,
    predicted_success=predicted_success,
    prediction_confidence=prediction_confidence,
)
```

**Forward-compatible path**: When we introduce the Response Manager, the Executive would return structured intents instead of plain text — e.g., `{type: "speak", content: "...", tone: "sarcastic", urgency: 0.8}`. For the PoC, plain text through the existing stream is sufficient. The structured format is a later-stage PoC change.

---

## 7. Scheduling is an Orchestrator Responsibility

**Decision**: Event scheduling (priority, preemption, starvation prevention) belongs inside the Orchestrator, not as a separate subsystem.

**Why**: Like an OS scheduler is part of the kernel, not a separate process. Adding a network hop to every scheduling decision is exactly the wrong place to add latency.

**Current state**: The EventQueue uses a priority heap ordered by salience:
```python
# Max-heap via negative salience (heapq is min-heap)
heapq.heappush(self._heap, (-salience, self._counter, event_id))
```

This is naive — FIFO within priority bands, no preemption, no starvation prevention. At scale (hundreds of events/second from multiple sensors), this needs:
- **Starvation prevention**: Low-priority events shouldn't wait forever
- **Preemption**: High-urgency events should interrupt in-flight low-priority processing
- **Time-budgeting**: How long to spend on each event (deferred — premature for PoC)

**Not PoC scope**: The current priority queue is adequate for PoC-level event volumes. These enhancements are needed when real sensors are generating high-frequency events.

---

## 8. Arousal System: Deliberate Non-Requirement

**Decision**: We do not need a global arousal/alertness modulator.

**Why**: In the human brain, arousal is a global gain dial that modulates everything simultaneously — because neurons are slow and mostly serial. Software doesn't have this constraint. We can process 50 events concurrently via async/multi-threading. The urgency dimension in the salience vector, combined with the scheduling capabilities in the Orchestrator, covers the functional need without a dedicated system.

This is a **deliberate architectural choice**, not an oversight. If we discover we need global state modulation later (e.g., "system is overloaded, shed load on everything"), it can be added to the Orchestrator as a global throttle. We don't need a brain-inspired arousal system to do it.

---

## 9. Directory Restructure

**Decision**: Reorganize the codebase now, before sensor/plugin work begins.

**Why**: The current structure was fine for early exploration but doesn't accommodate what's coming. Adding it now while the codebase is small is the cheapest it'll ever be.

**Current structure (problems highlighted)**:
```
GLADys/
├── src/
│   ├── common/              # Shared utils (only package here)
│   ├── memory/
│   │   ├── python/          # MemoryStorage service
│   │   ├── rust/            # SalienceGateway — DIFFERENT subsystem, buried here
│   │   └── migrations/      # DB schema — owned by memory but used by others
│   ├── orchestrator/
│   ├── executive/
│   ├── dashboard/
│   └── integration/         # Tests mixed with docker-compose
├── scripts/                 # CLI tools mixed with shared libraries
│   ├── local.py             # CLI tool
│   ├── _db.py               # Shared library (not a CLI tool)
│   ├── _orchestrator.py     # Shared library (not a CLI tool)
│   └── ...
└── tools/                   # Unclear distinction from scripts/
```

**Proposed structure**:
```
GLADys/
├── proto/                      # Shared proto definitions (unchanged)
├── src/
│   ├── lib/                    # Shared libraries (imported, not deployed)
│   │   ├── gladys_common/      # Logging, shared utils
│   │   └── gladys_client/      # Unified service client (NEW)
│   │
│   ├── services/               # Runtime subsystems (each is deployable)
│   │   ├── orchestrator/
│   │   ├── memory/             # MemoryStorage only
│   │   ├── salience/           # SalienceGateway (Rust) — own home
│   │   ├── executive/
│   │   ├── dashboard/          # API + Dashboard
│   │   └── supervisor/         # Future: health monitoring
│   │
│   └── db/
│       └── migrations/         # Schema (not memory-owned)
│
├── packs/                      # Plugin ecosystem (domain-first)
│   ├── core/                   # Built-in sensors/skills
│   ├── personalities/
│   └── ...                     # Future domain packs
│
├── cli/                        # CLI tools only (no shared libs)
│   ├── local.py
│   ├── docker.py
│   └── ...
│
├── tests/                      # All tests consolidated
│   ├── unit/
│   └── integration/
│
├── tools/                      # Dev-only tooling (docsearch, etc.)
└── docs/                       # Unchanged
```

**Key changes**:
1. **`src/lib/`** — shared libraries have a clear home, separate from services
2. **Salience gets its own directory** — it's a separate subsystem, separate language, separate build
3. **`packs/`** — plugin/sensor work has a home from day one
4. **`cli/`** replaces `scripts/`** — pure CLI tools, shared libs moved to `src/lib/`
5. **Migrations to `src/db/`** — database schema is a shared concern, not memory-owned
6. **Tests consolidated** — not scattered across service directories

**Cost**: Updating import paths, Dockerfiles, docker-compose build contexts, and service management scripts. Mechanical work, mostly find-and-replace.

---

## 10. Async Intent Posting & Learning Module

### Executive → Actuator: Async Intent Posting

**Decision**: The Executive posts intents to actuator channels asynchronously (fire-and-forget), rather than calling actuators synchronously.

**Why**: The Executive must handle multiple events concurrently (parallel LLM calls). Synchronous dispatch would serialize actuator execution behind LLM inference. Async posting decouples the Executive's lifecycle from actuator latency — it decides, posts, and moves to the next event.

**How it works**:
- The dispatch table maps `domain + capability → channel`, not `→ function call`
- The Executive posts structured intents to the appropriate channel
- Actuators consume from their channels independently
- The Executive does not wait for or track actuator completion

**Brain analogy**: The prefrontal cortex doesn't wait for confirmation that your mouth finished saying words. It decides, dispatches, and moves on. Motor cortex handles execution. Re-engagement only happens on interruption or failure.

### Actuator Selection Must Be Deterministic

When multiple actuators claim the same capability (e.g., two `speak` handlers: local TTS and Discord), selection must be deterministic — same inputs, same actuator, every time. Non-deterministic routing prevents bug reproduction and makes behavior unpredictable.

**Resolution order** (design needed, not decided yet):
- User-configured priority per capability
- Context-scoped routing ("gaming" → Discord voice; "home" → local TTS)
- Capability specificity (`speak:discord` beats `speak:*`)

### Learning Module (Orchestrator-Owned)

**Decision**: Learning is a module inside the Orchestrator, not a separate subsystem. It owns the full feedback loop: observe outcomes, update beliefs, extract patterns.

**Why not a subsystem**: Learning doesn't need its own process, network interface, or service identity. It doesn't serve requests. Making it a service adds a hop to every confidence update — the same overhead that killed the Response Manager proposal.

**What it does**:

| Input | Operation | Output |
|-------|-----------|--------|
| Actuator outcome (from channel) | Track intent→outcome completion | Health data for Supervisor |
| Explicit user feedback | Update heuristic confidence (Bayesian) | Write to Memory |
| Implicit signals (undo, ignore) | Punishment detection, confidence decay | Write to Memory |
| Episodic batch (sleep mode) | Pattern extraction → candidate heuristics | Write to Memory |

The outcomes channel from async intent posting gives it a natural input stream — one module consuming one channel, rather than learning logic scattered across subsystems.

### Outcome Evaluation Requires Domain Knowledge

**Key insight**: Determining whether an outcome is good or bad requires domain knowledge. "Storage blew up" is a fact; "storage blowing up is bad" requires knowing what storage contains and that items are lost permanently. The learning module is domain-agnostic — it doesn't have this knowledge. Domain Skills do.

**How it works**: The learning module calls the relevant skill's `evaluate_outcome()` to assess what happened:

```
evaluate_outcome(episode, outcome) → {
    valence: float      # -1.0 (catastrophic) to +1.0 (ideal)
    confidence: float   # how sure the skill is about this assessment
    factors: []         # what contributed ("storage_destroyed", "player_survived")
}
```

The learning module uses `valence × confidence` as the Bayesian update weight. High-confidence catastrophic outcomes drive strong negative updates. Uncertain assessments barely move the needle.

The `factors` list aids **attribution** — tracing which decision led to the outcome, rather than blaming whichever heuristic fired most recently.

**Fallback without a skill** (no domain expert available):
1. Explicit user feedback (thumbs up/down) — user acts as domain expert
2. Generic signals — action undone within 60s (bad), suggestion ignored 3+ times (bad), no complaint within timeout (weakly good)
3. No update — better to learn nothing than to learn wrong

This means the system **learns fastest in domains with skills loaded** (continuous outcome evaluation) and **slowest without skills** (only explicit user feedback). That's correct behavior — be cautious about learning in domains you don't understand.

**Hard problems** (not solved yet, captured for track B):
- **Attribution**: Was the bad outcome caused by a bad decision, bad execution, or bad luck?
- **Delayed consequences**: Immediate outcome was good, but downstream effects were bad. When does the evaluation window close?
- **Counterfactuals**: Would the outcome have been the same without intervention?

**Sleep mode**: Batch learning (pattern extraction, heuristic generation from episodes) runs during idle periods when the system has spare compute. The Orchestrator's scheduler can give the learning module elevated priority during sleep cycles.

### Extraction Discipline

**Critical constraint**: The learning module's interface must stay clean enough to extract into a separate process later without surgery.

**Rules**:
- Define the interface as if it were already a service: typed input messages, typed output messages, no shared mutable state with the Orchestrator
- The module takes inputs (outcomes, feedback signals) and produces outputs (writes to Memory). It does not reach into Orchestrator internals
- No importing Orchestrator-internal types or state — dependency flows one direction

**When extraction matters**: If learning batch jobs become heavy enough to compete with event routing for CPU, or if real-time outcome monitoring and batch extraction both need to run continuously. The extraction cost is proportional to how well the boundary is maintained.

**Spectrum**:

| Approach | When |
|----------|------|
| Learning logic inline in Orchestrator | PoC |
| Learning as a module with clean boundary | When learning code grows beyond trivial |
| Learning as a background worker (sleep mode) | When batch jobs need CPU isolation |
| Learning as a persistent subsystem (7th process) | When real-time + batch both run continuously |

We're starting at row 2. Let it emerge from track B (Events & Learning) work.

---

## Additional Items on the Radar (Not Decisions Yet)

These were discussed but not resolved. They need design work:

- **Context/Mode detection** ("gaming" vs "working") — affects salience thresholds, active skills, response behavior. Needs an owner (Orchestrator or Salience).
- **Configuration subsystem** — runtime config changes beyond `.env` at startup. Dashboard Settings tab needs a backend.
- **Domain Skill plugin interface** — what does the Executive-to-Skill contract look like?
- **Actuator conflict resolution** — deterministic selection when multiple actuators claim the same capability. Priority, context-scoping, specificity rules. Needs design.
- **Plugin behavior enforcement** — "immune system" ensuring plugins only use declared capabilities, respect resource bounds, don't escalate trust tiers. Post-PoC need (we control all plugins for now), but Supervisor is the natural home.
- **Brain subsystem audit** — systematic review of brain regions mapped to GLADyS functions. Episodic memory and metacognition already documented in ADRs. Worth doing deliberately.
- **Linux/WSL readiness** — audit for Windows path assumptions during directory restructure.
- **Install package** — single-command setup for new developers (`make setup && make run`).
- **Code velocity** — hot reload for Python gRPC services, one-command e2e test.
