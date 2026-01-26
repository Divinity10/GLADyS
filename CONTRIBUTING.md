# Contributing to GLADyS

GLADyS (**G**eneralized **L**ogical **A**daptive **Dy**namic **S**ystem) is a general-purpose adaptive AI assistant. We're building it to be local-first, privacy-focused, and user-controlled.

## What We're Building

GLADyS learns and adapts to help with:
- **Gaming**: Minecraft companion, game state awareness
- **Smart home**: Sensors, thermostats, lighting automation
- **Productivity**: Calendar awareness, task management
- **Health/Wellness**: Activity tracking, habit formation

It's not just a chatbot—it's a system that remembers, learns, and acts.

## What We Need

We're looking for contributors with experience in:

| Area | Technologies | What You'd Work On |
|------|--------------|-------------------|
| **Core systems** | Rust | Orchestrator, fast paths, performance-critical code |
| **ML/Storage** | Python, PostgreSQL | Memory subsystem, embeddings, semantic search |
| **User interface** | C#/.NET | Executive layer, user interactions |
| **Integrations** | Various | Sensors (Discord, Minecraft, Home Assistant, etc.) |
| **DevOps** | Docker, gRPC | Build systems, deployment, observability |

Don't see your skillset? Open an issue—we might have something.

## How to Get Involved

1. **Read the architecture**: Start with [docs/adr/](docs/adr/) to understand design decisions
2. **Pick an area**: Look at open issues or ask what needs help
3. **Set up locally**: See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
4. **Make small PRs**: Fix a bug, improve docs, add tests—build trust first

## First-Time Setup

After cloning the repo, run these commands to ensure cross-platform compatibility:

```bash
# Use the shared git hooks (strips AI co-author lines per CLAUDE.md)
git config core.hooksPath hooks

# Normalize line endings (prevents CRLF/LF issues)
git add --renormalize .
```

**Why?**
- The `hooks/` directory contains git hooks that work on Windows, Mac, and Linux
- Line ending normalization ensures consistent files across platforms
- The `.editorconfig` file configures most editors automatically

## Project Tracking

GitHub's UI hides these in different places, so here are direct links:

| What | Where | Purpose |
|------|-------|---------|
| [Project Board](https://github.com/orgs/Divinity10/projects/4) | Orgs → Projects | Kanban view of all work (Backlog → In Progress → Done) |
| [Milestones](https://github.com/Divinity10/GLADyS/milestones) | Repo → Issues → Milestones | Group issues by release/phase (M0, M1, M2...) |
| [Issues](https://github.com/Divinity10/GLADyS/issues) | Repo → Issues | Individual tasks and bugs |
| [Labels](https://github.com/Divinity10/GLADyS/labels) | Repo → Issues → Labels | Categorize by subsystem and priority |

## How We Work

### Decision Making

Significant decisions are documented in **Architecture Decision Records (ADRs)** in `docs/adr/`. If you want to propose a change to architecture:

1. Open an issue to discuss
2. If there's consensus, draft an ADR
3. ADR gets reviewed and merged

### Code Style

- **Rust**: Standard rustfmt, clippy clean
- **Python**: PEP 8, type hints required
- **C#**: .NET conventions

### Commits

Format: `type(scope): message`

```
feat(orchestrator): add sensor registration
fix(memory): correct embedding dimension
doc(ADR): add actuator specification
```

### Pull Requests

- Keep PRs focused (one feature/fix per PR)
- Include tests for new functionality
- Update docs if behavior changes
- Reference related issues

## Development Workflows

### Regenerating Proto Stubs

All proto definitions live in a single shared directory: `proto/` at the project root. When `.proto` files change, regenerate stubs:

```bash
# From project root
python scripts/proto_gen.py
```

This script:
1. Finds a Python environment with `grpc_tools` installed
2. Regenerates all Python stubs from `proto/` to service-specific `generated/` directories
3. Fixes import issues (absolute → relative) in generated files
4. Verifies generated files have valid Python syntax

**Proto locations:**
- `proto/*.proto` → Source of truth for all proto definitions
- `src/memory/python/gladys_memory/generated/` → Python stubs for memory service
- `src/orchestrator/gladys_orchestrator/generated/` → Python stubs for orchestrator

### Configuration

The Memory subsystem uses Pydantic Settings for configuration. Settings can come from:
1. Environment variables (highest priority)
2. `.env` file in the module directory
3. Code defaults (lowest priority)

**Environment variable prefixes:**
- `STORAGE_*` - Database connection (host, port, database, user, password)
- `EMBEDDING_*` - Embedding model (model_name, embedding_dim)
- `SALIENCE_*` - Salience evaluation (thresholds, time windows)
- `GRPC_*` - gRPC server (host, port, max_workers)

Example:
```bash
export STORAGE_HOST=postgres.local
export STORAGE_PORT=5432
export SALIENCE_NOVELTY_SIMILARITY_THRESHOLD=0.9
```

See `src/memory/python/gladys_memory/config.py` for all available settings.

## Project Owners

- **Mike Mulcahy** (Divinity10) - Lead
- **Scott Mulcahy** (scottcm)

## Questions?

Open an issue or check existing discussions. We're happy to help you find a good first contribution.
