# GLADyS Documentation Map

**Purpose**: An inverted index mapping **Concepts** to **Files**.
**AI Instructions**: Find your topic below. Read the "Source of Truth" (ADR) for definitions, and "Implementation" for current state.

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

## ⚡ Salience & Attention
*Keywords: Filtering, Routing, Urgency, Habituation, Novelty*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0013](adr/ADR-0013-Salience-Subsystem.md) | Salience vector definitions, Attention budget. |
| **Truth** | [ADR-0001](adr/ADR-0001-GLADyS-Architecture.md) | High-level "Fast Path" (Rust) architecture. |
| **Design** | [DESIGN.md#salience-subsystem](design/DESIGN.md#salience-subsystem) | **Current Implementation**: Rust Gateway, Heuristic matching. |
| **Impl** | `src/memory/rust/src/server.rs` | **SalienceGateway** implementation (Code). |
| **Proto** | `src/memory/proto/memory.proto` | Salience vector wire format. |

## 💾 Memory & Knowledge
*Keywords: Embeddings, Vector Search, Semantic, Episodic, Heuristics*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0004](adr/ADR-0004-Memory-Schema-Details.md) | **Database Schema**, L0-L3 hierarchy definitions. |
| **Truth** | [ADR-0009](adr/ADR-0009-Memory-Contracts-and-Compaction-Policy.md) | Compaction rules (Episodic -> Semantic). |
| **Design** | [DESIGN.md#memory-subsystem](design/DESIGN.md#memory-subsystem) | **Current Implementation**: Postgres + pgvector, Python storage. |
| **Debate** | [Q&A](design/questions/memory.md) | Discussions on embedding strategies. |
| **Impl** | `src/memory/python/gladys_memory/storage.py` | Storage implementation (Code). |

## 🛠️ Infrastructure & Ops
*Keywords: Docker, Scripts, Ports, Deployment, CLI, Queue*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Map** | [CODEBASE_MAP.md](../CODEBASE_MAP.md) | **Critical**: Ports, Service Topology, Directory Layout, Data Ownership. |
| **Guide** | [GETTING_STARTED.md](GETTING_STARTED.md) | Setup and run instructions. |
| **Code** | `scripts/_service_base.py` | Core automation framework (includes `queue watch`, `queue stats` CLI). |   
| **Code** | `scripts/_orchestrator.py` | Orchestrator gRPC client — queue inspection and event publishing. |
| **Tool** | `tools/docsearch/` | **DocSearch**. Context packing tool for AI sessions. |
| **Test** | `src/integration/test_orchestrator_executive.py` | End-to-end integration test (Orchestrator ↔ Executive). |
## 🎭 Executive & Personality
*Keywords: LLM, Decision Making, Traits, Response, OODA*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0014](adr/ADR-0014-Executive-Decision-Loop.md) | The OODA decision loop specification. |
| **Truth** | [ADR-0015](adr/ADR-0015-Personality-Subsystem.md) | Personality traits and response styles. |
| **Design** | [DESIGN.md#executive-subsystem](design/DESIGN.md#executive-subsystem) | **Current Implementation**: Python stub, Ollama integration. |
| **Impl** | `src/executive/gladys_executive/stub_server.py` | Executive gRPC server (TD learning, heuristic writes). |
| **Config** | [Templates](design/PERSONALITY_TEMPLATES.md) | Specific personality configurations (Murderbot, Butler). |

## 🔌 Plugins & World
*Keywords: Sensors, Actuators, Manifest, Safety, Audit, Subscription, Dashboard*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0003](adr/ADR-0003-Plugin-Manifest-Specification.md) | `manifest.yaml` structure for Plugins. |
| **Truth** | [ADR-0011](adr/ADR-0011-Actuator-Subsystem.md) | Actuator safety bounds and permissions. |
| **Truth** | [ADR-0012](adr/ADR-0012-Audit-Logging.md) | Immutable audit logging requirements. |
| **Design** | [DESIGN.md#orchestrator-subsystem](design/DESIGN.md#orchestrator-subsystem) | **Current Implementation**: Orchestrator routing and plugin mgmt. |
| **Impl** | `src/orchestrator/gladys_orchestrator/event_queue.py` | Priority queue with async worker and timeout scanner. |
| **Impl** | `src/orchestrator/gladys_orchestrator/server.py` | Orchestrator gRPC server (routing, subscriptions, store callbacks). |
| **UI** | `src/dashboard/` | Dashboard V2 (FastAPI + htmx + Alpine.js). See [DASHBOARD_V2.md](design/DASHBOARD_V2.md). |
| **UI (legacy)** | `src/ui/dashboard.py` | Streamlit dashboard (deprecated, replaced by V2). |

---

## 🔍 Validation & Metrics
*Where to check if things actually work.*

- **E2E Status**: [INTEGRATION_TEST_RESULTS.md](validation/INTEGRATION_TEST_RESULTS.md)
- **LLM Quality**: [prediction_quality_report.md](validation/prediction_quality_report.md)
- **Dictionary**: [GLOSSARY.md](design/GLOSSARY.md) (Definitions of Terms)
- **Tech Debt**: [TECH_DEBT.md](TECH_DEBT.md) (Known shortcuts to revisit post-PoC)

---

## 🏛️ Archive
*Superseded designs. Do not implement based on these.*

- `docs/design/archive/`
- `docs/archive/`