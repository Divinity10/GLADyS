# GLADyS Codebase Map

Maps brain-inspired concepts to implementing code. Answers: **"Where is the code for X?"**

For live data (ports, RPCs, schema, routers), run `codebase-info <command>`. For documentation by topic, see [docs/INDEX.md](docs/INDEX.md).

---

## Core Pipeline

GLADyS models cognitive processing. Each service maps to a brain-inspired role.
Visual: [SERVICE_TOPOLOGY.md](docs/codebase/SERVICE_TOPOLOGY.md)

| Concept | Module | Lang | Role |
|---------|--------|------|------|
| Sensory organs (input) | `sdk/`, `packs/sensors/` | Java, TS, Py | Sensor SDKs; external processes publish events via gRPC |
| Thalamus (routing) | `src/services/orchestrator/` | Python | Routes sensor events through salience evaluation to executive |
| Salience network + amygdala (filtering) | `src/services/salience/` | Rust | Fast-path heuristic matching, multi-dimension scoring, LRU cache |
| Hippocampus (memory) | `src/services/memory/` | Python | Heuristic/event storage, semantic search via embeddings |
| Prefrontal cortex (reasoning) | `src/services/executive/` | Python | LLM-based reasoning, response generation, heuristic creation |
| Basal ganglia (habit learning) | *in executive* | Python | TD learning, confidence updates, heuristic extraction |
| Personality (behavioral style) | *TBD* | -- | Response tone, trait evolution, style preferences |

## User Interfaces

| Module | Role |
|--------|------|
| `src/services/dashboard/` | Dev UI: event simulation, response history, heuristic management (FastAPI + htmx) |
| `src/services/fun_api/` | JSON REST API for programmatic access (mounted in dashboard app) |

## Protocol & Shared Code

| Module | Role |
|--------|------|
| `proto/` | gRPC service contracts — source of truth for all inter-service RPCs |
| `src/lib/gladys_common/` | Cross-service Python utilities (logging, config) |
| `src/lib/gladys_client/` | DB queries, gRPC client helpers |
| `src/db/migrations/` | PostgreSQL schema (numbered .sql files, applied automatically) |

## Sensors & Packs

| Module | Role |
|--------|------|
| `sdk/java/gladys-sensor-sdk/` | Java sensor SDK (game sensors: RuneScape, Melvor) |
| `sdk/js/gladys-sensor-sdk/` | TypeScript sensor SDK (browser sensors: Gmail) |
| `packs/` | Skill packs, sensor configs, output templates, personalities |

## Developer Tools

| Module | Role |
|--------|------|
| `cli/` | Service management (`local.py`, `docker.py`), migration, health checks |
| `tools/codebase-info/` | Live codebase reference: RPCs, ports, schema, tree, routers |
| `tools/codebase-drift/` | Validates this map against actual codebase |
| `tools/docsearch/` | Documentation search and audit |
| `tools/questions-report/` | Generates report of open design questions |
| `tools/dashboard/` | Dashboard development utilities |

## Finding Information

| Need | Where |
|------|-------|
| Ports, RPCs, schema, tree, routers | `codebase-info <command>` (live from source) |
| Architecture, data flows, concurrency | `docs/codebase/` (9 topic files) |
| ADRs, design docs by concept | [docs/INDEX.md](docs/INDEX.md) |
| Coding conventions | [docs/CONVENTIONS.md](docs/CONVENTIONS.md) |
