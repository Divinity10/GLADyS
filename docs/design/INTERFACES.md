# GLADyS Interface Specifications

**Status**: Living document — evolves as implementation reveals what works.
**Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md) for decisions and rationale.

This document defines the contracts between subsystems, plugin interfaces, and data structures. Developers implementing plugins or connecting subsystems should reference this file.

---

## Plugin Interface Composition

All plugins implement a base interface. Type-specific interfaces layer on top. The Supervisor calls `health()` uniformly on all plugin types without needing type-specific knowledge.

### BasePlugin (all plugins)

```
health() → HealthStatus          # status reporting (used by Supervisor)
capabilities() → [Capability]    # what this plugin can do
start() → void                   # lifecycle: initialize and begin
stop() → void                    # lifecycle: clean shutdown
```

### SensorPlugin = BasePlugin + SensorInterface

```
emit_events() → EventStream      # event stream to Orchestrator
get_state() → busy | idle | error
```

### ActuatorPlugin = BasePlugin + ActuatorInterface

```
execute(action) → Result         # perform the action
get_state() → busy | idle | error
interrupt(priority) → bool       # whether preemption succeeded
```

### SkillPlugin = BasePlugin + SkillInterface

```
process(event, context) → Decision
confidence_estimate(event) → float
evaluate_outcome(episode, outcome) → OutcomeEvaluation
```

---

## OutcomeEvaluation

Returned by `SkillPlugin.evaluate_outcome()`. Used by the learning module to weight Bayesian confidence updates.

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

---

## Codebase Directory Structure

Target layout after restructure (ARCHITECTURE.md §9).

```
GLADys/
├── proto/                      # Shared proto definitions (unchanged)
├── src/
│   ├── lib/                    # Shared libraries (imported, not deployed)
│   │   ├── gladys_common/      # Logging, shared utils
│   │   └── gladys_client/      # Unified service client
│   │
│   ├── services/               # Runtime subsystems (each is deployable)
│   │   ├── orchestrator/
│   │   ├── memory/             # MemoryStorage only
│   │   ├── salience/           # SalienceGateway (Rust) — own home
│   │   ├── executive/
│   │   ├── fun_api/            # REST gateway + dev/QA UI
│   │   └── supervisor/         # Future: health monitoring
│   │
│   └── db/
│       └── migrations/         # Schema (not memory-owned)
│
├── packs/                      # Plugin ecosystem (domain-first)
│   ├── core/
│   ├── personalities/
│   └── ...
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
└── docs/
```

### Key principles

- **`src/lib/`** — shared libraries, separate from services
- **`src/services/`** — each subsystem gets its own directory, independently deployable
- **`packs/`** — plugin/sensor work has a home from day one
- **`cli/`** — pure CLI tools, no shared library code (that goes in `src/lib/`)
- **`src/db/migrations/`** — database schema is a shared concern, not memory-owned
- **`tests/`** — consolidated, not scattered across service directories