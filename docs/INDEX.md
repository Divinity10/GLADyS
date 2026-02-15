# GLADyS Documentation Map

**Purpose**: An inverted index mapping **Concepts** to **Files**.
**AI Instructions**: Find your topic below. Read "Truth" (ADR) for definitions, "Design" for design intent, "Impl" for code locations.

---

## Where Does New Information Go?

| I want to record... | Put it in |
|---------------------|-----------|
| An architectural decision (why we chose X) | [ARCHITECTURE.md](design/ARCHITECTURE.md) |
| An interface contract or data structure | [INTERFACES.md](design/INTERFACES.md) |
| Current implementation state of a subsystem | [DESIGN.md](design/DESIGN.md) |
| Phase scope, success criteria, abort signals | [ITERATIVE_DESIGN.md](design/ITERATIVE_DESIGN.md) |
| A permanent, immutable decision | `docs/adr/` (new ADR) |
| An open question or debate | `docs/design/questions/` |
| A term definition | [GLOSSARY.md](design/GLOSSARY.md) |
| Service topology, data ownership | [SERVICE_TOPOLOGY.md](codebase/SERVICE_TOPOLOGY.md) |
| Service ports | Run `codebase-info ports` |
| Concept-to-code mapping | [CONCEPT_MAP.md](../CONCEPT_MAP.md) |
| Setup/run instructions, dev environment | [GETTING_STARTED.md](GETTING_STARTED.md) |
| Known shortcuts to fix post-Phase | [GitHub Issues](https://github.com/divinity10/GLADyS/issues) (label: tech-debt) |

If none of these fit, create a new doc — and add it to this table and the index below.

---

## ðŸ§  Intelligence & Learning

*Keywords: Bayesian, Confidence, Feedback, Training, EWMA, Adaptation*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0010](adr/ADR-0010-Learning-and-Inference.md) | **Bayesian definitions**, System 1 vs 2, Learning Pipeline, **Outcome evaluation** (§3.11), **Deferred validation** (§3.12). |
| **Truth** | [ADR-0007](adr/ADR-0007-Adaptive-Algorithms.md) | **EWMA**, User Preference tracking logic. |
| **Design** | [DESIGN.md#learning-subsystem](design/DESIGN.md#learning-subsystem) | TD Learning, Confidence update design and deviations from ADRs. |
| **Debate** | [Q&A](design/questions/learning.md) | Open questions on **TD Learning** and Heuristics. |
| **Math** | [Personality Model](design/PERSONALITY_IDENTITY_MODEL.md) | The math behind trait evolution. |
| **Design** | [LEARNING_STRATEGY.md](design/LEARNING_STRATEGY.md) | **Extensibility**: Learning signal interpretation interface (Bayesian strategy, alternative models). |
| **Design** | [CONFIDENCE_BOOTSTRAPPING.md](design/CONFIDENCE_BOOTSTRAPPING.md) | LLM endorsement bootstraps below-threshold heuristics. Defines **three measurement dimensions**: context match, confidence, success rate. Dev rating workflow. |

## âš¡ Salience & Attention

*Keywords: Filtering, Routing, Urgency, Habituation, Novelty, Selection, Confidence Threshold, Context Match*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0013](adr/ADR-0013-Salience-Subsystem.md) | Salience vector definitions, Attention budget. |
| **Truth** | [ADR-0001](adr/ADR-0001-GLADyS-Architecture.md) | High-level "Fast Path" (Rust) architecture. |
| **Design** | [DESIGN.md#salience-subsystem](design/DESIGN.md#salience-subsystem) | Rust Gateway, Heuristic matching design and deviations from ADRs. |
| **Design** | [SALIENCE_MODEL.md](design/SALIENCE_MODEL.md) | **Salience Model Interface**: SalienceResult data object, threat/habituation separation, configurable weights. |
| **Impl** | `src/services/salience/src/server.rs` | **SalienceGateway** implementation (Code). |
| **Proto** | `proto/memory.proto` | Salience vector wire format. |
| **Design** | [SALIENCE_SCORER.md](design/SALIENCE_SCORER.md) | **Extensibility**: Rust trait for salience scoring algorithms. |
| **Design** | [DECISION_STRATEGY.md](design/DECISION_STRATEGY.md) | **Selection strategy**: similarity-dominant ranking, confidence threshold gate, urgency-modulated tiers, three measurement dimensions. |

## ðŸ’¾ Memory & Knowledge

*Keywords: Embeddings, Vector Search, Semantic, Episodic, Heuristics*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0004](adr/ADR-0004-Memory-Schema-Details.md) | **Database Schema**, L0-L3 hierarchy definitions. |
| **Truth** | [ADR-0009](adr/ADR-0009-Memory-Contracts-and-Compaction-Policy.md) | Compaction rules (Episodic -> Semantic). |
| **Design** | [DESIGN.md#memory-subsystem](design/DESIGN.md#memory-subsystem) | Postgres + pgvector storage design and deviations from ADRs. |
| **Debate** | [Q&A](design/questions/memory.md) | Discussions on embedding strategies. |
| **Impl** | `src/services/memory/gladys_memory/storage.py` | Storage implementation (Code). |

## ðŸ—ï¸ Architecture & Design

*Keywords: Subsystems, API, Plugins, Packs, Interfaces, Phase, Lifecycle*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Decisions** | [ARCHITECTURE.md](design/ARCHITECTURE.md) | **10 architectural decisions**: subsystem taxonomy, API tiers, plugin ecosystem, async dispatch, learning module. |
| **Interfaces** | [INTERFACES.md](design/INTERFACES.md) | **Plugin contracts**: common/sensor/actuator/skill protocols, OutcomeEvaluation, pack manifest, directory structure. |
| **Roadmap** | [ITERATIVE_DESIGN.md](design/ITERATIVE_DESIGN.md) | **Phase lifecycle**: claims, convergence tests, baseline metrics, DoD, proven/not-proven templates, future Phase roadmap. |
| **Scenarios** | [USE_CASES.md](design/USE_CASES.md) | Use case catalog validating architectural decisions. |
| **State** | [DESIGN.md](design/DESIGN.md) | Per-subsystem implementation status, Phase deviations, open questions. The status-tracking doc. |
| **Overview** | [SUBSYSTEM_OVERVIEW.md](design/SUBSYSTEM_OVERVIEW.md) | Conceptual overview and onboarding guide for all subsystems. |
| **Truth** | [ADR-0008](adr/ADR-0008-Security-and-Privacy.md) | **Security & Privacy**: permissions, sandboxing, age restrictions, data retention, fail-closed defaults. |
| **Index** | [ADR README](adr/README.md) | ADR index with status, reading order, and dependency graph. |

## ðŸ“‹ Design Questions

*Keywords: Open Questions, Decisions, Tradeoffs*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Index** | [README.md](design/questions/README.md) | Status summary of all design questions. |
| **Resolved** | [confidence-bootstrapping.md](design/questions/confidence-bootstrapping.md) | ~~How new heuristics bootstrap~~ → Resolved: [CONFIDENCE_BOOTSTRAPPING.md](design/CONFIDENCE_BOOTSTRAPPING.md) |
| **Question** | [confidence-analysis-harness.md](design/questions/confidence-analysis-harness.md) | Tooling for analyzing confidence dynamics. |
| **Question** | [feedback-signal-decomposition.md](design/questions/feedback-signal-decomposition.md) | Breaking feedback into component signals. |
| **Question** | [user-feedback-calibration.md](design/questions/user-feedback-calibration.md) | Calibrating user feedback to learning rate. |
| **Resolved** | [sensor-dashboard.md](design/questions/sensor-dashboard.md) | ~~Sensor management dashboard design~~ → Resolved: [SENSOR_DASHBOARD.md](design/SENSOR_DASHBOARD.md) |
| **Question** | [resource-allocation.md](design/questions/resource-allocation.md) | Resource allocation across concurrent events. |
| **Question** | [poc1-findings.md](design/questions/poc1-findings.md) | Phase 1 findings requiring Phase 2 action. |
| **Question** | [cross-cutting.md](design/questions/cross-cutting.md) | Cross-cutting design concerns. |
| **Question** | [data-types.md](design/questions/data-types.md) | Data type design questions. |
| **Question** | [infrastructure.md](design/questions/infrastructure.md) | Infrastructure design questions. |
| **Question** | [plugins.md](design/questions/plugins.md) | Plugin system design questions. |
| **Question** | [outcome-correlation.md](design/questions/outcome-correlation.md) | Decision-to-outcome matching, retroactive multi-heuristic evaluation. |
| **Question** | [urgency-selection.md](design/questions/urgency-selection.md) | Urgency-modulated thresholds, heuristic selection tiers, cache decision. |
| **Question** | [goal-identification.md](design/questions/goal-identification.md) | Goal impact on success measurement, goal inference, goal-directed prompts. |

## ðŸ› ï¸ Infrastructure & Ops

*Keywords: Docker, Scripts, Ports, Deployment, CLI, Queue*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Map** | [CONCEPT_MAP.md](../CONCEPT_MAP.md) | Concept-to-code map — brain-inspired concepts to implementing modules. For live data, run `codebase-info`. |
| **Tool** | `tools/codebase-info/` | **codebase-info**: Live-generated codebase reference (RPCs, ports, schema, tree, routers). |
| **Guide** | [GETTING_STARTED.md](GETTING_STARTED.md) | Setup and run instructions. |
| **Conventions** | [CONVENTIONS.md](CONVENTIONS.md) | Code, testing, and dependency conventions across all services. |
| **Guide** | [docs/README.md](README.md) | Documentation landing page with reading order and quick links. |
| **Truth** | [ADR-0002](adr/ADR-0002-Hardware-Requirements.md) | **Hardware Requirements**: GPU/VRAM sizing, dual-GPU upgrade path, cloud/hybrid cost analysis. |
| **Truth** | [ADR-0005](adr/ADR-0005-gRPC-Service-Contracts.md) | **gRPC Service Contracts**: proto definitions, transport strategies, timeout budgets, error handling. |
| **Truth** | [ADR-0006](adr/ADR-0006-Observability-and-Monitoring.md) | **Observability & Monitoring**: Prometheus, Loki, Jaeger, Grafana stack, alerting rules. |
| **Code** | `cli/_service_base.py` | Core automation framework (includes `queue watch`, `queue stats` CLI). |
| **Lib** | `src/lib/gladys_client/` | Shared client library — DB queries, gRPC clients (orchestrator, cache, health). |
| **Code** | `cli/_orchestrator.py` | Orchestrator CLI commands (thin wrapper over gladys_client). |
| **Tool** | `tools/docsearch/` | **DocSearch**. Context packing tool for AI sessions. |
| **Test** | `tests/integration/test_llm_response_flow.py` | End-to-end integration test (Orchestrator â†” Executive). |
| **Design** | [LOGGING_STANDARD.md](design/LOGGING_STANDARD.md) | Standardized structured logging conventions. |
| **Design** | [ROUTER_CONFIG.md](design/ROUTER_CONFIG.md) | **Extensibility**: Orchestrator router configuration (externalized from code). |

## ðŸŽ­ Executive & Personality

*Keywords: LLM, Decision Making, Traits, Response, OODA*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0014](adr/ADR-0014-Executive-Decision-Loop.md) | The OODA decision loop specification. |
| **Truth** | [ADR-0015](adr/ADR-0015-Personality-Subsystem.md) | Personality traits and response styles. |
| **Design** | [DESIGN.md#executive-subsystem](design/DESIGN.md#executive-subsystem) | Executive subsystem design and deviations from ADRs. |
| **Impl** | `src/services/executive/gladys_executive/server.py` | Executive gRPC server (TD learning, heuristic writes). |
| **Config** | [Templates](design/PERSONALITY_TEMPLATES.md) | Specific personality configurations (Murderbot, Butler). |
| **Design** | [EXECUTIVE_DESIGN.md](design/EXECUTIVE_DESIGN.md) | Generalized executive subsystem: decision-making, response generation, learning. |
| **Design** | [LLM_PROVIDER.md](design/LLM_PROVIDER.md) | **Extensibility**: Abstract LLM provider interface (swappable without modifying decision logic). |
| **Design** | [DECISION_STRATEGY.md](design/DECISION_STRATEGY.md) | **Extensibility**: Executive decision strategy — heuristic vs LLM path selection, candidate ranking. |

## ðŸ”Œ Plugins & World

*Keywords: Sensors, Actuators, Manifest, Safety, Audit, Subscription, Dashboard*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Truth** | [ADR-0003](adr/ADR-0003-Plugin-Manifest-Specification.md) | `manifest.yaml` structure for Plugins. |
| **Design** | [SENSOR_ARCHITECTURE.md](design/SENSOR_ARCHITECTURE.md) | **Sensor protocol**: multi-sensor pipeline, language-agnostic contract, per-language SDKs, delivery patterns, capture/replay. |
| **SDK** | `sdk/python/gladys-sensor-sdk/` | Python sensor SDK -- async client, event dispatch, command handling, flow control, sensor lifecycle. |
| **SDK** | `sdk/java/gladys-sensor-sdk/` | Java sensor SDK -- gRPC client, event dispatch, command handling, flow control. |
| **SDK** | `sdk/js/gladys-sensor-sdk/` | TypeScript sensor SDK -- same API surface, ts-proto generated stubs. |
| **Truth** | [ADR-0011](adr/ADR-0011-Actuator-Subsystem.md) | Actuator safety bounds and permissions. |
| **Truth** | [ADR-0012](adr/ADR-0012-Audit-Logging.md) | Immutable audit logging requirements. |
| **Design** | [DESIGN.md#orchestrator-subsystem](design/DESIGN.md#orchestrator-subsystem) | Orchestrator routing and plugin management design. |
| **Impl** | `src/services/orchestrator/gladys_orchestrator/event_queue.py` | Priority queue with async worker and timeout scanner. |
| **Impl** | `src/services/orchestrator/gladys_orchestrator/server.py` | Orchestrator gRPC server (routing, subscriptions, store callbacks). |
| **UI** | `src/services/dashboard/` | Dashboard V2 (FastAPI + htmx + Alpine.js). See [DASHBOARD_V2.md](design/DASHBOARD_V2.md). |
| **UI** | [DASHBOARD_COMPONENT_ARCHITECTURE.md](design/DASHBOARD_COMPONENT_ARCHITECTURE.md) | Rendering patterns (Pattern A, widget macros) — prevents htmx/Alpine bugs. |
| **UI** | [DASHBOARD_WIDGET_SPEC.md](design/DASHBOARD_WIDGET_SPEC.md) | Widget macro specification for self-contained, testable components. |
| **UI** | [DASHBOARD_HEURISTICS_TAB.md](design/DASHBOARD_HEURISTICS_TAB.md) | Heuristics tab design (server-side rendering fix). |
| **UI** | [DASHBOARD_RESPONSE_DATA.md](design/DASHBOARD_RESPONSE_DATA.md) | Response and Heuristics tab data model. |
| **API** | `src/services/fun_api/` | JSON API routers (imported by dashboard). See [DASHBOARD.md](codebase/DASHBOARD.md). |
| **UI (legacy)** | *(removed)* | Streamlit V1 dashboard deleted; replaced by V2 above. |

---

## ðŸ”¬ Research

*Keywords: Theory, Cognitive Science, Neuroscience, Academic, Open Questions*

| Type | File | Purpose |
| :--- | :--- | :--- |
| **Theory** | [THEORETICAL_FOUNDATIONS.md](research/THEORETICAL_FOUNDATIONS.md) | Cognitive science and RL foundations — how the architecture maps to neuroscience. |
| **Questions** | [OPEN_QUESTIONS.md](research/OPEN_QUESTIONS.md) | Unsolved research problems where expert input would help. |
| **Backlog** | [RESEARCH_BACKLOG.md](research/RESEARCH_BACKLOG.md) | Literature research tasks we can do ourselves. |

## ðŸ” Validation & Metrics

*Where to check if things actually work.*

- **Benchmarking**: [BENCHMARK_STRATEGY.md](design/BENCHMARK_STRATEGY.md) (polyglot architecture validation)
- **E2E Status**: [INTEGRATION_TEST_RESULTS.md](validation/INTEGRATION_TEST_RESULTS.md)
- **LLM Quality**: [prediction_quality_report.md](validation/prediction_quality_report.md)
- **Heuristic Quality**: [heuristic_quality_report.md](validation/heuristic_quality_report.md) (LLM heuristic extraction validation across 8 domains)
- **Integration Scenarios**: [integration_test_scenarios.md](validation/integration_test_scenarios.md) (7 learning loop scenarios: happy path, correction, fuzzy matching, domain safety)
- **Dictionary**: [GLOSSARY.md](design/GLOSSARY.md) (Definitions of Terms)
- **Tech Debt**: [GitHub Issues](https://github.com/divinity10/GLADyS/issues) (label: tech-debt)

---

## Codebase Reference

*Detailed codebase documentation split by topic. Read only what you need.*

| File | Content |
| :--- | :--- |
| [SERVICE_TOPOLOGY.md](codebase/SERVICE_TOPOLOGY.md) | Architecture diagram, event/heuristic data flows, data ownership |
| [CONCURRENCY.md](codebase/CONCURRENCY.md) | Per-service threading model, async boundaries, known race conditions |
| [DOMAIN_CONVENTIONS.md](codebase/DOMAIN_CONVENTIONS.md) | Heuristic matching, field semantics, salience vector, proto vs DB gaps |
| [DASHBOARD.md](codebase/DASHBOARD.md) | Dual-router architecture, rendering patterns, data access paths |
| [DOCKER.md](codebase/DOCKER.md) | Build requirements, volume mounts, proto/build contexts |
| [DB_MANAGEMENT.md](codebase/DB_MANAGEMENT.md) | Migration workflow, schema sync rules |
| [LOGGING.md](codebase/LOGGING.md) | Trace ID propagation, log locations, env vars |
| [LEARNING_MODULE.md](codebase/LEARNING_MODULE.md) | Implicit feedback, outcome watcher, LearningModule interface |
| [TESTING.md](codebase/TESTING.md) | Testing strategy, priorities, patterns, coverage expectations |
| [TROUBLESHOOTING.md](codebase/TROUBLESHOOTING.md) | Common mistakes, diagnostic steps, quick commands |

---

## ðŸ›ï¸ Archive

*Superseded designs. Do not implement based on these.*

- `docs/design/archive/`
- `docs/archive/`
