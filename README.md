# GLADyS

**G**eneralized **L**ogical **A**daptive **Dy**namic **S**ystem

> ⚠️ **DRAFT STATUS**: This project is currently in the design phase. All documentation represents proposed architecture and is subject to change. No implementation code exists yet.

## Overview

GLADyS is a local-first, brain-inspired AI assistant designed to observe, learn, and assist users in real-time contexts such as gaming, productivity, and smart home control.

### Key Characteristics

| Characteristic | Description |
|----------------|-------------|
| **Local-first** | All data stays on your device by default |
| **Privacy-focused** | Explicit opt-in for any cloud features |
| **Extensible** | Plugin system for sensors and skills |
| **Adaptive** | Learns user preferences over time |
| **Personality-driven** | Configurable personalities (e.g., Murderbot, Helpful Assistant) |

## Project Status

```
[██░░░░░░░░] 20% - Design Phase
```

| Phase | Status | Description |
|-------|--------|-------------|
| **Architecture Design** | ✅ Complete | Core architecture decisions documented |
| **Security Design** | ✅ Complete | Permission model, sandboxing, privacy policies |
| **API Design** | ✅ Complete | gRPC service contracts defined |
| **Implementation** | ⏳ Not Started | Waiting on design finalization |
| **Testing** | ⏳ Not Started | — |
| **Alpha Release** | ⏳ Not Started | — |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           GLADyS                                │
│                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                        │
│  │ Visual  │  │  Audio  │  │  Game   │   SENSORS              │
│  │ Sensor  │  │ Sensor  │  │(Aperture│   (Python)             │
│  └────┬────┘  └────┬────┘  └────┬────┘                        │
│       │            │            │                              │
│       └────────────┼────────────┘                              │
│                    ▼                                           │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              ORCHESTRATOR (Rust)                        │  │
│  │  • Shared memory for images                             │  │
│  │  • Security enforcement                                 │  │
│  │  • Plugin lifecycle                                     │  │
│  └─────────────────────────┬───────────────────────────────┘  │
│                            │                                   │
│       ┌────────────────────┼────────────────────┐             │
│       ▼                    ▼                    ▼             │
│  ┌─────────┐        ┌───────────┐        ┌──────────┐        │
│  │SALIENCE │        │  MEMORY   │        │EXECUTIVE │        │
│  │ GATEWAY │        │ CONTROLLER│        │  (C#)    │        │
│  │(Python) │        │ (Python)  │        │          │        │
│  └─────────┘        └───────────┘        └────┬─────┘        │
│                                               │               │
│                                               ▼               │
│                                        ┌──────────┐          │
│                                        │  OUTPUT  │          │
│                                        │  (TTS)   │          │
│                                        └──────────┘          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Documentation

### Architecture Decision Records

All architectural decisions are documented as ADRs in [`docs/adr/`](docs/adr/README.md).

| ADR | Title |
|-----|-------|
| [0001](docs/adr/ADR-0001-GLADyS-Architecture.md) | GLADyS Architecture |
| [0002](docs/adr/ADR-0002-Hardware-Requirements.md) | Hardware Requirements |
| [0003](docs/adr/ADR-0003-Plugin-Manifest-Specification.md) | Plugin Manifest Specification |
| [0004](docs/adr/ADR-0004-Memory-Schema-Details.md) | Memory Schema Details |
| [0005](docs/adr/ADR-0005-gRPC-Service-Contracts.md) | gRPC Service Contracts |
| [0006](docs/adr/ADR-0006-Observability-and-Monitoring.md) | Observability and Monitoring |
| [0007](docs/adr/ADR-0007-Adaptive-Algorithms.md) | Adaptive Algorithms |
| [0008](docs/adr/ADR-0008-Security-and-Privacy.md) | Security and Privacy |

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Orchestrator | Rust | Performance, memory safety |
| Sensors | Python | ML ecosystem, rapid development |
| Salience Gateway | Python | ML models |
| Memory Controller | Python | ML models, PostgreSQL integration |
| Executive | C# | Strong LLM tooling |
| Database | PostgreSQL + pgvector | Relational + vector search |
| Communication | gRPC | Performance, strong typing |
| Observability | Prometheus, Loki, Jaeger, Grafana | Industry standard |

## Hardware Requirements

### Minimum (Phase 1)

- CPU: Modern 6+ core
- RAM: 32GB DDR4
- GPU: RTX 2070 8GB or equivalent
- Storage: 100GB SSD

### Recommended (Phase 2)

- CPU: Modern 8+ core
- RAM: 64GB DDR4
- GPU: RTX 3090 24GB (or dual GPU setup)
- Storage: 250GB NVMe SSD

See [ADR-0002](docs/adr/ADR-0002-Hardware-Requirements.md) for details.

## Security & Privacy

Security is a foundational design principle, not an afterthought.

| Principle | Implementation |
|-----------|----------------|
| Local-first | Data stays on device by default |
| Minimal collection | Only collect what's needed, discard raw data |
| Fail closed | Deny by default |
| Defense in depth | Multiple security layers |
| Transparency | Users can see what's collected |

### Age Restrictions

| Age | Access Level |
|-----|--------------|
| 13-15 | Game sensors only, limited permissions |
| 16-17 | All 1st party, signed 3rd party |
| 18+ | Full access |

See [ADR-0008](docs/adr/ADR-0008-Security-and-Privacy.md) for the complete security model.

## Game Integration

GLADyS can integrate with games through **Aperture**, a bridge mod that exposes game data via local APIs. This provides more accurate data than screen capture alone.

See [ADR-0008 Section 13](docs/adr/ADR-0008-Security-and-Privacy.md#13-game-mod-integration) for details.

## Contributing

> 🚧 Contribution guidelines will be added once implementation begins.

At this stage, contributions are focused on:

- Architecture feedback via GitHub Issues
- ADR review and discussion
- Use case proposals

## License

TBD

## Contact

- **Owner**: Mike Mulcahy (Divinity10)
- **Contributors**: Scott

---

<p align="center">
  <i>Named in memory of Gladys — grandmother, inspiration.</i>
</p>
