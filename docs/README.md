# GLADyS Documentation

**Start here** for understanding the GLADyS architecture.

---

## Reading Order

| Phase | Document | Time | Purpose |
|-------|----------|------|---------|
| **1. Overview** | [SUBSYSTEM_OVERVIEW.md](design/SUBSYSTEM_OVERVIEW.md) | 15 min | What each subsystem does, how they connect |
| **2. Terminology** | [GLOSSARY.md](design/GLOSSARY.md) | 10 min | Terms from neuroscience, ML, and project |
| **3. Architecture** | [ADR-0001](adr/ADR-0001-GLADyS-Architecture.md) | 30 min | Foundational architecture decisions |
| **4. Learning** | [ADR-0010](adr/ADR-0010-Learning-and-Inference.md) | 20 min | System 1/2 split, how GLADyS learns |
| **5. Deep Dive** | Other ADRs as needed | - | See [ADR Index](adr/README.md) |

---

## Quick Links

| What You Need | Where to Look |
|---------------|---------------|
| **Find any doc by topic** | [INDEX.md](INDEX.md) |
| High-level system understanding | [SUBSYSTEM_OVERVIEW.md](design/SUBSYSTEM_OVERVIEW.md) |
| **Running services (local/Docker)** | [GETTING_STARTED.md](GETTING_STARTED.md#running-the-full-stack) |
| Service ports | Run `codebase-info ports` |
| Concept-to-code map | [CONCEPT_MAP.md](../CONCEPT_MAP.md) |
| PoC phases & success criteria | [POC_LIFECYCLE.md](design/POC_LIFECYCLE.md) |
| Sensor protocol & SDK architecture | [SENSOR_ARCHITECTURE.md](design/SENSOR_ARCHITECTURE.md) |
| All ADRs indexed | [docs/adr/README.md](adr/README.md) |
| Open design questions | [design/questions/](design/questions/README.md) |
| Use cases and requirements | [USE_CASES.md](design/USE_CASES.md) |
| Personality templates | [PERSONALITY_TEMPLATES.md](design/PERSONALITY_TEMPLATES.md) |

---

## Common Developer Tasks

### Running & Managing Services
| I want to... | Command |
|--------------|---------|
| Start all services | `python cli/docker.py start all` |
| Check what's running | `python cli/docker.py status` |
| View service logs | `python cli/docker.py logs` |
| Reset everything | `python cli/docker.py reset` |

### Debugging & Investigation
| I want to... | See |
|--------------|-----|
| See events and heuristics visually | [Dashboard](../src/services/dashboard/) |
| Query the database directly | `python cli/docker.py psql` |
| Understand why confidence changed | [learning.md §20](design/questions/learning.md) |
| Check what's implemented vs planned | [ADR-0010 Status](adr/ADR-0010-Learning-and-Inference.md#implementation-status) |

### Building Features
| I want to... | See |
|--------------|-----|
| Build a sensor | [SENSOR_ARCHITECTURE.md](design/SENSOR_ARCHITECTURE.md), [GETTING_STARTED](GETTING_STARTED.md#i-want-to-build-a-sensor) |
| Build a skill/actuator | [ADR-0011](adr/ADR-0011-Actuator-Subsystem.md) |
| Add a database migration | [src/db/migrations/](../src/db/migrations/) |
| Change a proto contract | [CONTRIBUTING.md](../CONTRIBUTING.md#regenerating-proto-stubs) |

### Understanding the System
| I want to... | See |
|--------------|-----|
| Get the 30-second overview | [Key Concepts](#key-concepts-30-second-version) below |
| Understand System 1 vs System 2 | [ADR-0010](adr/ADR-0010-Learning-and-Inference.md) |
| See all architectural decisions | [ADR Index](adr/README.md) |

---

## Key Concepts (30-Second Version)

**GLADyS** = Generalized Logical Adaptive Dynamic System

- **Sensors** observe the world (games, smart home, audio)
- **Salience** filters what's worth paying attention to
- **Memory** stores context and learns preferences
- **Executive** decides when and how to respond
- **Actuators** take action (speech, device control)

**System 1 / System 2 Split**:
- System 1: Fast heuristics (<5ms) - handles familiar situations
- System 2: LLM deliberation (200-500ms) - handles novel situations
- GLADyS learns from System 2 to improve System 1 over time

**Local-First**: All user data stays on user's machine. Privacy by design.

---

## Document Types

| Type | Location | Purpose |
|------|----------|---------|
| **ADRs** | `docs/adr/` | Architecture Decision Records - why we made specific choices |
| **Design docs** | `docs/design/` | Working documents, overviews, open questions |
| **Archive** | `docs/archive/` | Preserved design work (deferred features, historical decisions) |
