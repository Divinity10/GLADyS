# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the GLADyS project.

## What is an ADR?

An ADR is a document that captures an important architectural decision made along with its context and consequences. ADRs help us:

- Remember why decisions were made
- Onboard new team members
- Revisit decisions when context changes
- Maintain consistency across the system

## ADR Index

| ADR | Title | Module | Status | Summary |
|-----|-------|--------|--------|---------|
| [0001](ADR-0001-GLADyS-Architecture.md) | GLADyS Architecture | Core | Proposed | Brain-inspired architecture with sensors, salience gateway, memory system, executive, security module, and orchestration layer |
| [0002](ADR-0002-Hardware-Requirements.md) | Hardware Requirements | Platform | Proposed | GPU requirements, dual-GPU upgrade path, cloud deployment options |
| [0003](ADR-0003-Plugin-Manifest-Specification.md) | Plugin Manifest Specification | Plugins | Proposed | YAML-based manifest structure for sensors and skills |
| [0004](ADR-0004-Memory-Schema-Details.md) | Memory Schema Details | Memory | Proposed | Hierarchical L0-L4 memory, PostgreSQL + pgvector, EWMA user profiling |
| [0005](ADR-0005-gRPC-Service-Contracts.md) | gRPC Service Contracts | Contracts | Proposed | Proto definitions, transport strategies, timeout budgets, circuit breakers |
| [0006](ADR-0006-Observability-and-Monitoring.md) | Observability and Monitoring | Observability | Proposed | Prometheus, Loki, Jaeger, Grafana stack with alerting |
| [0007](ADR-0007-Adaptive-Algorithms.md) | Adaptive Algorithms | Intelligence | Proposed | EWMA adaptation, Bayesian confidence, feedback collection, user controls |
| [0008](ADR-0008-Security-and-Privacy.md) | Security and Privacy | Security | Proposed | Permission system, sandboxing, shared memory, age restrictions, data retention |
| [0009](ADR-0009-Memory-Contracts-and-Compaction-Policy.md) | Memory Contracts and Compaction Policy | Memory | Proposed | Episodic ingest/query contracts, configurable compaction tiers, provenance |

## ADR Status Lifecycle

```
Proposed → Accepted → Deprecated
                   ↘ Superseded (by ADR-XXXX)
```

| Status | Meaning |
|--------|---------|
| **Proposed** | Under discussion, not yet approved |
| **Accepted** | Approved and in effect |
| **Deprecated** | No longer relevant |
| **Superseded** | Replaced by a newer ADR |

## Reading Order

For those new to the project, we recommend reading in this order:

1. **ADR-0001** - Start here for system overview
2. **ADR-0008** - Security principles that influence all other decisions
3. **ADR-0003** - Plugin system (how sensors and skills work)
4. **ADR-0004** - Memory system
5. **ADR-0005** - Communication between components
6. **ADR-0006** - How we monitor the system
7. **ADR-0007** - How the system learns and adapts
8. **ADR-0002** - Hardware requirements (reference as needed)

## Creating a New ADR

1. Copy the template: `cp _template.md ADR-XXXX-Title.md`
2. Fill in all sections
3. Submit for review
4. Update this README index

## ADR Template

```markdown
# ADR-XXXX: Title

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | YYYY-MM-DD |
| **Owner** | Name |
| **Contributors** | Names |
| **Module** | Core/Memory/Security/etc |
| **Tags** | comma, separated, tags |
| **Depends On** | ADR-XXXX, ADR-YYYY |

## 1. Context and Problem Statement

What is the issue that we're seeing that is motivating this decision?

## 2. Decision Drivers

- Driver 1
- Driver 2

## 3. Decision

What is the change that we're proposing and/or doing?

## 4. Consequences

### Positive
### Negative
### Risks

## 5. Related Decisions

- ADR-XXXX: Related decision
```

## Dependencies Between ADRs

```
ADR-0001 (Architecture)
    │
    ├──► ADR-0002 (Hardware)
    │
    ├──► ADR-0003 (Plugin Manifest) ◄─── ADR-0008 (Security)
    │         │
    │         ▼
    ├──► ADR-0004 (Memory Schema)
    │         │
    │         ▼
    ├──► ADR-0005 (gRPC Contracts) ◄─── ADR-0008 (Security)
    │         │
    │         ▼
    ├──► ADR-0006 (Observability) ◄──── ADR-0007 (Adaptive)
    │
    └──► ADR-0007 (Adaptive Algorithms)
              │
              ▼
         ADR-0008 (Security & Privacy)
```

## Key Terminology

| Term | Meaning |
|------|---------|
| **GLADyS** | Generalized Logical Adaptive Dynamic System - the project name |
| **Aperture** | Bridge mod for game integration (exposes game data via local API) |
| **Sensor** | Plugin that observes the environment (screen, audio, game state) |
| **Skill** | Plugin that provides capabilities to the executive (knowledge, actions) |
| **Executive** | The decision-making component that generates responses |
| **Salience** | How important/relevant an event is to the user's current context |
