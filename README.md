# GLADyS

**G**eneralized **L**ogical **A**daptive **Dy**namic **S**ystem

A local-first, privacy-focused AI assistant that learns and adapts. Not just a chatbot—a system that remembers, learns, and acts.

*Neurotoxin module sold separately.*

## Concept

GLADyS is an AI assistant that perceives its environment through **sensors** (game state, smart home devices, calendars) and interacts through **actuators** (sending messages, controlling devices, triggering actions).

The architecture draws from:
- **Neuroscience**: Hippocampal memory consolidation, complementary learning systems
- **Cognitive science**: System 1 (fast/intuitive) and System 2 (slow/deliberate) thinking
- **Reinforcement learning**: Learning from outcomes, not just instructions

Key principles:
- **Learns, doesn't just respond**: Builds heuristics from experience, remembers context across sessions
- **Configurable personality**: Some users want a cheerful helper. Others want an antisocial introvert who will save your life but would rather be watching shows—and please don't make eye contact.
- **Local-first**: Your data stays on your machine; you control what (if anything) leaves

## Vision

- **Gaming**: Minecraft, RuneScape, game state awareness. *What else? WoW, FFXIV, Path of Exile? [Let us know!](https://github.com/Divinity10/GLADyS/issues)*
- **Smart home**: Doorbell, thermostats, lighting
- **Productivity**: Calendar and email awareness
- **Health**: CGM, smartwatch, fitness data

## Current Focus

1. Memory subsystem (PoC complete)
2. Orchestrator
3. Learning pipeline
4. First sensor integration

## Status

| Component | Status |
|-----------|--------|
| Architecture Design | 🔄 Core defined, evolving |
| Memory Subsystem | 🧪 Proof of concept |
| Orchestrator | 🧪 Proof of concept |
| Executive | 🧪 Proof of concept (stub) |
| Sensors | ⏳ Not started |

## Tech Stack

| Component | Technology |
|-----------|------------|
| Orchestrator | Python |
| Memory | Rust + Python + PostgreSQL |
| Executive | Python (stub; production: C#) |
| Sensors/Skills | Various |
| Communication | gRPC |

## Documentation

| Doc | Purpose |
|-----|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to get involved |
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Development setup |
| [docs/adr/](docs/adr/) | Architecture decisions |
| [docs/design/questions/](docs/design/questions/) | Active design discussions |

## Quick Start

```bash
# With Docker (recommended - no Rust required)
python cli/docker.py start all
python cli/docker.py status
python cli/docker.py health       # Verify gRPC endpoints respond

# With local Rust + PostgreSQL
python cli/local.py start all
python cli/local.py status
python cli/local.py health        # Verify gRPC endpoints respond
```

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for full setup.

## Owners

- **Mike Mulcahy** (Divinity10) - Lead
- **Scott Mulcahy** (scottcm)

## Contributors

- **Leah DeYoung** (LDeYoung17)

---

<p align="center">
  <i>Named in memory of Gladys — grandmother, great-grandmother, inspiration.<br/>
  Any resemblance to murderous AI constructs is purely coincidental. The cake is not a lie.</i>
</p>
