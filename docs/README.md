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
| High-level system understanding | [SUBSYSTEM_OVERVIEW.md](design/SUBSYSTEM_OVERVIEW.md) |
| **Running services (local/Docker)** | [DEVELOPMENT.md](design/DEVELOPMENT.md) |
| All ADRs indexed | [docs/adr/README.md](adr/README.md) |
| Open design questions | [OPEN_QUESTIONS.md](design/OPEN_QUESTIONS.md) |
| Architecture review status | [ARCHITECTURE_REVIEW.md](design/ARCHITECTURE_REVIEW.md) |
| Use cases and requirements | [USE_CASES.md](design/USE_CASES.md) |
| Personality templates | [PERSONALITY_TEMPLATES.md](design/PERSONALITY_TEMPLATES.md) |

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
