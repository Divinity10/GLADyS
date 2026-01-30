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

**Decision**: One canonical client library per language for all service communication. Every consumer — app services, dashboard, scripts, tests — imports the same client code.

**Why**: Right now, gRPC channel setup and stub management is duplicated in three places with subtle differences:

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

## 3. Seven Runtime Subsystems

**Decision**: GLADyS has seven runtime subsystems (services that run as processes), plus a plugin/config ecosystem around them.

| # | Subsystem | Core Responsibility | Status |
|---|-----------|-------------------|--------|
| 1 | **Orchestrator** | Event routing, scheduling, preprocessing pipeline | Exists |
| 2 | **Memory** | Storage, embeddings, semantic search | Exists |
| 3 | **Salience** | Attention filtering, heuristic cache, novelty | Exists |
| 4 | **Executive** | Reasoning, decisions, domain skill dispatch | Exists (stub) |
| 5 | **Response Manager** | Output routing, personality, channel state, preemption | New |
| 6 | **API / Dashboard** | REST API, dev/QA UI, SSE | Exists |
| 7 | **Supervisor** | Sensor/service health monitoring, auto-restart, alerts | New |

**New: Response Manager** — Currently, the Executive produces text and the Orchestrator shoves it back through the gRPC stream. But responses have real complexity:
- Multiple output channels (speech, text chat, actuator commands, notifications)
- Priority/preemption (urgent response interrupts current speech)
- Personality application (tone/style applied before delivery)
- Channel state (is TTS busy? Is the user present?)

Example scenario:
1. Executive decides user should be notified via speech
2. Sends message + personality cue (sarcastic, urgent, etc.) to Response Manager
3. Response Manager sends to TTS with specified tone
4. Urgent event arrives — new message dispatched with high urgency
5. Urgency > current message priority — interrupt and speak new message

**New: Supervisor** — Who watches the watchers? We need to detect sick sensors (no events received in 20 minutes), alert users, auto-restart or disable failing components. Currently health checks are manual (`scripts/local.py health`).

---

## 4. Plugin Ecosystem

**Decision**: Plugins are categorized by type, but distributed as packs (grouped by domain).

| Type | What It Is | Runtime Owner |
|------|-----------|---------------|
| **Domain Skill** | Executable reasoning capability loaded into Executive | Executive |
| **Sensor** | External data source with managed lifecycle | Orchestrator |
| **Actuator** | External action target (speech, Discord, lights) | Response Manager |
| **Preprocessor** | Fast enrichment/normalization in hot path | Orchestrator |
| **Personality** | Config layer affecting response style, not reasoning | Response Manager |

**Domain Skills are not just data** — they include code that understands domain-specific events and can reason about them. A Minecraft skill knows what "player entered the Nether" *means*, can provide domain-specific confidence estimates, and can handle routine domain events without invoking the LLM. The analogy: Neo downloading kung-fu in The Matrix. It's not a reference book — it's a capability.

**Personality is a config layer, not a subsystem.** It affects how decisions get expressed (tone, style, TTS voice) but does not affect reasoning or learning.

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
│   └── butler/
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

## Additional Items on the Radar (Not Decisions Yet)

These were discussed but not resolved. They need design work:

- **Context/Mode detection** ("gaming" vs "working") — affects salience thresholds, active skills, response behavior. Needs an owner (Orchestrator or Salience).
- **Configuration subsystem** — runtime config changes beyond `.env` at startup. Dashboard Settings tab needs a backend.
- **Domain Skill plugin interface** — what does the Executive-to-Skill contract look like?
- **Brain subsystem audit** — systematic review of brain regions mapped to GLADyS functions. Episodic memory and metacognition already documented in ADRs. Worth doing deliberately.
- **Linux/WSL readiness** — audit for Windows path assumptions during directory restructure.
- **Install package** — single-command setup for new developers (`make setup && make run`).
- **Code velocity** — hot reload for Python gRPC services, one-command e2e test.
