# GLADyS Architecture Decisions

**Status**: Approved (Scott & Mike, 2026-01-29)
**Interfaces**: See [INTERFACES.md](INTERFACES.md) for plugin contracts and detailed specifications.
**PoC Roadmap**: See [POC_LIFECYCLE.md](POC_LIFECYCLE.md) for implementation phases and success criteria.

---

## 1. Two-Tier API: gRPC Internal, REST External

**Decision**: gRPC for service-to-service communication. REST (FUN API) for all external consumers — dashboard, CLI tools, future UIs, plugins.

**Why**: gRPC gives type safety, streaming, and performance between services we control. REST gives universal accessibility — any language, any client, no proto compilation needed. Industry standard (Google, Netflix, most cloud-native systems).

**In practice**: Services talk gRPC to each other. The FUN API's FastAPI layer becomes the official external gateway. CLI tools and future sensors connect via REST (or gRPC if they need streaming).

---

## 2. Single Client Library (Python)

**Decision**: Consolidate scattered Python gRPC client code into a single shared package (`gladys_client`).

**Why**: Three Python codebases duplicate gRPC channel setup with subtle differences — dashboard caches channels, scripts create one per call, health checks use context managers. Bug fix in one doesn't fix the others. One library, one pattern.

**Scope**: Python-only deduplication. Rust and C# generate their own gRPC clients from proto files, which is correct — no cross-language duplication exists.

**Industry term**: Client SDK pattern (AWS, Stripe, Twilio).

---

## 3. Six Runtime Subsystems

**Decision**: Six runtime subsystems (processes), plus a plugin/config ecosystem.

| # | Subsystem | Core Responsibility | Status |
|---|-----------|-------------------|--------|
| 1 | **Orchestrator** | Event routing, scheduling, preprocessing, learning module | Exists |
| 2 | **Memory** | Storage, embeddings, semantic search | Exists |
| 3 | **Salience** | Attention filtering, heuristic cache, novelty | Exists |
| 4 | **Executive** | Reasoning, decisions, skill/response dispatch | Exists (stub) |
| 5 | **FUN API** | REST gateway (Functional Unified Nexus), dev/QA UI, SSE | Exists |
| 6 | **Supervisor** | Health monitoring, auto-restart, alerts | New |

**Response Manager rejected as subsystem** — demoted to Executive module. Adding a service hop between Executive and actuators costs latency, and personality should be a prompt modifier in a single LLM call, not a second call. Actuator routing is a dispatch table; channel state is reported by actuators via interface; preemption is the actuator's responsibility.

**Supervisor justification**: Single authority on component health. Independent monitoring loop calls `health()` on all registered components uniformly via the common plugin protocol. Distributing health monitoring across subsystems creates duplication and no single source of truth. May share a process with Orchestrator if code boundary stays clean.

---

## 4. Plugin Ecosystem

**Decision**: Plugins are categorized by type, distributed as packs (grouped by domain).

| Type | What It Is | Runtime Owner |
|------|-----------|---------------|
| **Domain Skill** | Executable reasoning capability (not just data — code that *understands* domain events) | Executive |
| **Sensor** | External data source with managed lifecycle | Orchestrator |
| **Actuator** | External action target (speech, Discord, lights) | Executive (dispatch) |
| **Preprocessor** | Fast enrichment/normalization in hot path, pack-owned | Orchestrator |
| **Personality** | Config layer: prompt modifier + optional heuristics/skills | Executive |

**Domain Skills = capabilities, not data.** The Matrix analogy: Neo downloading kung-fu. A Minecraft skill knows what "player entered the Nether" *means*, provides domain-specific confidence, and handles routine events without the LLM.

**Personality can affect reasoning.** Primarily a prompt modifier (tone, style, TTS voice), but packs can optionally include heuristics and skills. Personality heuristics are tagged by origin (e.g., `origin: 'personality:glados'`) and disabled by default on personality swap. The system can cleanly enable/disable them as a group.

**Interface composition**: All plugins implement a common protocol (lifecycle + health). Type-specific protocols layer on top. See [INTERFACES.md](INTERFACES.md) for contracts.

---

## 5. Packs: Domain-First Distribution

**Decision**: Pack-first directory structure, not type-first. Manifest-driven discovery.

**Why**: A Minecraft pack has a sensor, a skill, a preprocessor, and heuristics. Scattering those across type directories forces you to look in four places for one logical unit. Grouping by domain keeps related code together.

**Precedent**: VS Code extensions, game mods, browser extensions. The pack is the installable unit.

**Personalities are a separate pack type** — cross-cutting, not domain-specific. A user runs the Minecraft pack with the Murderbot personality or the Butler personality.

See [INTERFACES.md](INTERFACES.md) for pack directory structure and manifest format.

---

## 6. Executive as Decision-Maker (Async Intent Posting)

**Decision**: The Executive decides *what* should happen, posts intents to actuator channels asynchronously (fire-and-forget), and moves on.

**Why**: The Executive must handle multiple events concurrently (parallel LLM calls). Synchronous dispatch serializes actuator execution behind LLM inference. Async posting decouples the Executive's lifecycle from actuator latency.

**How skills fit**: Domain Skills run *under* the Executive as plugins (library calls), not beside it as peer services. The Executive gains capabilities by loading skills.

**Dispatch table**: Maps `domain + capability → channel`, not `→ function call`. Actuators consume from their channels independently.

**Actuator selection must be deterministic** — same inputs, same actuator, every time. Resolution mechanism needs design (user-configured priority, context-scoped routing, capability specificity).

**Forward path**: Executive currently returns plain text (`response_text`). Will evolve to structured intents (e.g., `{type: "speak", content: "...", tone: "sarcastic", urgency: 0.8}`) when actuators exist.

---

## 7. Scheduling is an Orchestrator Responsibility

**Decision**: Event scheduling belongs inside the Orchestrator, not as a separate subsystem.

**Why**: Like an OS scheduler is part of the kernel. Adding a network hop to every scheduling decision adds latency in the wrong place.

**Current state**: Naive priority heap (FIFO within priority bands). Adequate for PoC. Needs starvation prevention, preemption, and time-budgeting at scale.

---

## 8. Arousal System: Deliberate Non-Requirement

**Decision**: No global arousal/alertness modulator.

**Why**: Software doesn't have the constraint that makes arousal necessary in brains (neurons are slow and mostly serial). Async/multi-threading + salience urgency dimension covers the functional need. If global load-shedding is needed later, it's an Orchestrator throttle, not a brain-inspired subsystem.

---

## 9. Directory Restructure

**Decision**: Reorganize the codebase before sensor/plugin work begins.

**Why**: Current structure doesn't match the subsystem taxonomy. Salience is buried in `memory/`, scripts mix tools with shared libs, tests are scattered. Cheapest to fix now while codebase is small.

**Key changes**: `src/services/` (subsystem per dir), `src/lib/` (shared libraries), `packs/` (domain-first plugins), `cli/` (replaces scripts/), `src/db/migrations/` (shared concern), `tests/` (consolidated).

Run `uv run codebase-info tree` for the current layout.

---

## 10. Learning Module (Orchestrator-Owned)

**Decision**: Learning is a module inside the Orchestrator, not a separate subsystem.

**Why**: Doesn't need its own process, network interface, or service identity. Making it a service adds a hop to every confidence update — same overhead that killed the Response Manager.

**What it does**: Owns the full feedback loop — observe outcomes (from actuator outcomes channel), update heuristic confidence (Bayesian), detect implicit signals (undo, ignore), extract patterns during sleep mode.

**Domain-aware outcome evaluation**: The learning module is domain-agnostic. Domain Skills provide outcome evaluation via `evaluate_outcome()` — valence, confidence, contributing factors. Without a loaded skill, falls back to explicit user feedback or generic signals. System learns fastest in domains with skills loaded.

**Extraction discipline**: Interface must stay clean for future extraction to separate process. Rules: typed inputs/outputs, no shared mutable state with Orchestrator, no importing Orchestrator internals. Cost of extraction is proportional to boundary maintenance.

See [INTERFACES.md](INTERFACES.md) for `OutcomeEvaluation` structure and learning module I/O table.

---

## Open Design Questions

Not decisions yet. Need design work.

- **Context/Mode detection** ("gaming" vs "working") — affects salience thresholds, active skills. Needs an owner.
- **Configuration subsystem** — runtime config changes beyond `.env` at startup.
- **Actuator conflict resolution** — deterministic selection when multiple actuators claim same capability.
- **Plugin behavior enforcement** — "immune system" for capability/resource/trust-tier bounds. Post-PoC (we control all plugins now), Supervisor is natural home.
- **Brain subsystem audit** — systematic review of brain regions mapped to GLADyS functions.