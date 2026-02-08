# GLADyS Documentation Map

**Purpose**: An inverted index mapping **Concepts** to **Files**.
**AI Instructions**: Find your topic below. Read the "Source of Truth" (ADR) for definitions, and "Implementation" for current state.

---

## Where Does New Information Go?

| I want to record... | Put it in |
|---------------------|-----------|
| An architectural decision (why we chose X) | [ARCHITECTURE.md](design/ARCHITECTURE.md) |
| An interface contract or data structure | [INTERFACES.md](design/INTERFACES.md) |
| Current implementation state of a subsystem | [DESIGN.md](design/DESIGN.md) |
| PoC scope, success criteria, abort signals | [POC_LIFECYCLE.md](design/POC_LIFECYCLE.md) |
| A permanent, immutable decision | `docs/adr/` (new ADR) |
| An open question or debate | `docs/design/questions/` |
| A term definition | [GLOSSARY.md](design/GLOSSARY.md) |
| Service topology, ports, data ownership | [CODEBASE_MAP.md](../CODEBASE_MAP.md) |
| Setup/run instructions, dev environment | [GETTING_STARTED.md](GETTING_STARTED.md) |
| Known shortcuts to fix post-PoC | [GitHub Issues](https://github.com/divinity10/GLADyS/issues) (label: tech-debt) |

If none of these fit, create a new doc — and add it to this table and the index below.

---

## 🧠 Intelligence & Learning
*Keywords: Bayesian, Confidence, Feedback, Training, EWMA, Adaptation*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0010](adr/ADR-0010-Learning-and-Inference.md) | **Bayesian definitions**, System 1 vs 2, Learning Pipeline. |
| **Truth** | [ADR-0007](adr/ADR-0007-Adaptive-Algorithms.md) | **EWMA**, User Preference tracking logic. |
| **Design** | [DESIGN.md#learning-subsystem](design/DESIGN.md#learning-subsystem) | **Current Implementation**: TD Learning, Confidence updates. |
| **Debate** | [Q&A](design/questions/learning.md) | Open questions on **TD Learning** and Heuristics. |
| **Math** | [Personality Model](design/PERSONALITY_IDENTITY_MODEL.md) | The math behind trait evolution. |
| **Design** | [LEARNING_STRATEGY.md](design/LEARNING_STRATEGY.md) | **Extensibility**: Learning signal interpretation interface (Bayesian strategy, alternative models). |

## ⚡ Salience & Attention
*Keywords: Filtering, Routing, Urgency, Habituation, Novelty*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0013](adr/ADR-0013-Salience-Subsystem.md) | Salience vector definitions, Attention budget. |
| **Truth** | [ADR-0001](adr/ADR-0001-GLADyS-Architecture.md) | High-level "Fast Path" (Rust) architecture. |
| **Design** | [DESIGN.md#salience-subsystem](design/DESIGN.md#salience-subsystem) | **Current Implementation**: Rust Gateway, Heuristic matching. |
| **Design** | [SALIENCE_MODEL.md](design/SALIENCE_MODEL.md) | **Salience Model Interface**: SalienceResult data object, threat/habituation separation, configurable weights. |
| **Impl** | `src/services/salience/src/server.rs` | **SalienceGateway** implementation (Code). |
| **Proto** | `proto/memory.proto` | Salience vector wire format. |
| **Design** | [SALIENCE_SCORER.md](design/SALIENCE_SCORER.md) | **Extensibility**: Rust trait for salience scoring algorithms. |

## 💾 Memory & Knowledge
*Keywords: Embeddings, Vector Search, Semantic, Episodic, Heuristics*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0004](adr/ADR-0004-Memory-Schema-Details.md) | **Database Schema**, L0-L3 hierarchy definitions. |
| **Truth** | [ADR-0009](adr/ADR-0009-Memory-Contracts-and-Compaction-Policy.md) | Compaction rules (Episodic -> Semantic). |
| **Design** | [DESIGN.md#memory-subsystem](design/DESIGN.md#memory-subsystem) | **Current Implementation**: Postgres + pgvector, Python storage. |
| **Debate** | [Q&A](design/questions/memory.md) | Discussions on embedding strategies. |
| **Impl** | `src/services/memory/gladys_memory/storage.py` | Storage implementation (Code). |

## 🏗️ Architecture & Design
*Keywords: Subsystems, API, Plugins, Packs, Interfaces, PoC, Lifecycle*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Decisions** | [ARCHITECTURE.md](design/ARCHITECTURE.md) | **10 architectural decisions**: subsystem taxonomy, API tiers, plugin ecosystem, async dispatch, learning module. |
| **Interfaces** | [INTERFACES.md](design/INTERFACES.md) | **Plugin contracts**: BasePlugin, Sensor/Actuator/Skill interfaces, OutcomeEvaluation, pack manifest, directory structure. |
| **Roadmap** | [POC_LIFECYCLE.md](design/POC_LIFECYCLE.md) | **PoC lifecycle**: claims, convergence tests, baseline metrics, DoD, proven/not-proven templates, future PoC roadmap. |
| **Scenarios** | [USE_CASES.md](design/USE_CASES.md) | Use case catalog validating architectural decisions. |
| **State** | [DESIGN.md](design/DESIGN.md) | **Current implementation**: per-subsystem status, PoC deviations, open questions. |
| **Overview** | [SUBSYSTEM_OVERVIEW.md](design/SUBSYSTEM_OVERVIEW.md) | Conceptual overview and onboarding guide for all subsystems. |

## 🛠️ Infrastructure & Ops
*Keywords: Docker, Scripts, Ports, Deployment, CLI, Queue*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Map** | [CODEBASE_MAP.md](../CODEBASE_MAP.md) | **Critical**: Ports, Service Topology, Directory Layout, Data Ownership. |
| **Guide** | [GETTING_STARTED.md](GETTING_STARTED.md) | Setup and run instructions. |
| **Code** | `cli/_service_base.py` | Core automation framework (includes `queue watch`, `queue stats` CLI). |
| **Lib** | `src/lib/gladys_client/` | Shared client library — DB queries, gRPC clients (orchestrator, cache, health). |
| **Code** | `cli/_orchestrator.py` | Orchestrator CLI commands (thin wrapper over gladys_client). |
| **Tool** | `tools/docsearch/` | **DocSearch**. Context packing tool for AI sessions. |
| **Test** | `tests/integration/test_llm_response_flow.py` | End-to-end integration test (Orchestrator ↔ Executive). |
| **Design** | [LOGGING_STANDARD.md](design/LOGGING_STANDARD.md) | Standardized structured logging conventions. |
| **Design** | [ROUTER_CONFIG.md](design/ROUTER_CONFIG.md) | **Extensibility**: Orchestrator router configuration (externalized from code). |

## 🎭 Executive & Personality
*Keywords: LLM, Decision Making, Traits, Response, OODA*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0014](adr/ADR-0014-Executive-Decision-Loop.md) | The OODA decision loop specification. |
| **Truth** | [ADR-0015](adr/ADR-0015-Personality-Subsystem.md) | Personality traits and response styles. |
| **Design** | [DESIGN.md#executive-subsystem](design/DESIGN.md#executive-subsystem) | **Current Implementation**: Python stub, Ollama integration. |
| **Impl** | `src/services/executive/gladys_executive/server.py` | Executive gRPC server (TD learning, heuristic writes). |
| **Config** | [Templates](design/PERSONALITY_TEMPLATES.md) | Specific personality configurations (Murderbot, Butler). |
| **Design** | [EXECUTIVE_DESIGN.md](design/EXECUTIVE_DESIGN.md) | Generalized executive subsystem: decision-making, response generation, learning. |
| **Design** | [LLM_PROVIDER.md](design/LLM_PROVIDER.md) | **Extensibility**: Abstract LLM provider interface (swappable without modifying decision logic). |
| **Design** | [DECISION_STRATEGY.md](design/DECISION_STRATEGY.md) | **Extensibility**: Executive decision strategy — heuristic vs LLM path selection, candidate ranking. |

## 🔌 Plugins & World
*Keywords: Sensors, Actuators, Manifest, Safety, Audit, Subscription, Dashboard*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0003](adr/ADR-0003-Plugin-Manifest-Specification.md) | `manifest.yaml` structure for Plugins. |
| **Design** | [SENSOR_ARCHITECTURE.md](design/SENSOR_ARCHITECTURE.md) | **Sensor protocol**: multi-sensor pipeline, language-agnostic contract, per-language SDKs, delivery patterns, capture/replay. |
| **Truth** | [ADR-0011](adr/ADR-0011-Actuator-Subsystem.md) | Actuator safety bounds and permissions. |
| **Truth** | [ADR-0012](adr/ADR-0012-Audit-Logging.md) | Immutable audit logging requirements. |
| **Design** | [DESIGN.md#orchestrator-subsystem](design/DESIGN.md#orchestrator-subsystem) | **Current Implementation**: Orchestrator routing and plugin mgmt. |
| **Impl** | `src/services/orchestrator/gladys_orchestrator/event_queue.py` | Priority queue with async worker and timeout scanner. |
| **Impl** | `src/services/orchestrator/gladys_orchestrator/server.py` | Orchestrator gRPC server (routing, subscriptions, store callbacks). |
| **UI** | `src/services/dashboard/` | Dashboard V2 (FastAPI + htmx + Alpine.js). See [DASHBOARD_V2.md](design/DASHBOARD_V2.md). |
| **UI** | [DASHBOARD_COMPONENT_ARCHITECTURE.md](design/DASHBOARD_COMPONENT_ARCHITECTURE.md) | Rendering patterns (Pattern A, widget macros) — prevents htmx/Alpine bugs. |
| **UI** | [DASHBOARD_WIDGET_SPEC.md](design/DASHBOARD_WIDGET_SPEC.md) | Widget macro specification for self-contained, testable components. |
| **UI** | [DASHBOARD_HEURISTICS_TAB.md](design/DASHBOARD_HEURISTICS_TAB.md) | Heuristics tab design (server-side rendering fix). |
| **UI** | [DASHBOARD_RESPONSE_DATA.md](design/DASHBOARD_RESPONSE_DATA.md) | Response and Heuristics tab data model. |
| **API** | `src/services/fun_api/` | JSON API routers (imported by dashboard). See [CODEBASE_MAP.md](../CODEBASE_MAP.md#dual-router-architecture-critical). |
| **UI (legacy)** | *(removed)* | Streamlit V1 dashboard deleted; replaced by V2 above. |

---

## 🔬 Research
*Keywords: Theory, Cognitive Science, Neuroscience, Academic, Open Questions*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Theory** | [THEORETICAL_FOUNDATIONS.md](research/THEORETICAL_FOUNDATIONS.md) | Cognitive science and RL foundations — how the architecture maps to neuroscience. |
| **Questions** | [OPEN_QUESTIONS.md](research/OPEN_QUESTIONS.md) | Unsolved research problems where expert input would help. |
| **Backlog** | [RESEARCH_BACKLOG.md](research/RESEARCH_BACKLOG.md) | Literature research tasks we can do ourselves. |

## 🔍 Validation & Metrics
*Where to check if things actually work.*

- **Benchmarking**: [BENCHMARK_STRATEGY.md](design/BENCHMARK_STRATEGY.md) (polyglot architecture validation)
- **E2E Status**: [INTEGRATION_TEST_RESULTS.md](validation/INTEGRATION_TEST_RESULTS.md)
- **LLM Quality**: [prediction_quality_report.md](validation/prediction_quality_report.md)
- **Dictionary**: [GLOSSARY.md](design/GLOSSARY.md) (Definitions of Terms)
- **Tech Debt**: [GitHub Issues](https://github.com/divinity10/GLADyS/issues) (label: tech-debt)

---

## 🏛️ Archive
*Superseded designs. Do not implement based on these.*

- `docs/design/archive/`
- `docs/archive/`