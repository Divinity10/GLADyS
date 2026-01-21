# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the GLADyS project.

> **New to GLADyS?** Start with [docs/README.md](../README.md) for the recommended reading order. Read [SUBSYSTEM_OVERVIEW.md](../design/SUBSYSTEM_OVERVIEW.md) before diving into ADRs.

## What is an ADR?

An ADR is a document that captures an important architectural decision made along with its context and consequences. ADRs help us:

- Remember why decisions were made
- Onboard new team members
- Revisit decisions when context changes
- Maintain consistency across the system

## ADR Index

| ADR | Title | Module | Status | Summary |
|-----|-------|--------|--------|---------|
| [0001](ADR-0001-GLADyS-Architecture.md) | GLADyS Architecture | Core | Accepted | Brain-inspired architecture, language decisions, component hierarchy |
| [0002](ADR-0002-Hardware-Requirements.md) | Hardware Requirements | Platform | Accepted | GPU requirements, dual-GPU upgrade path, cloud deployment options |
| [0003](ADR-0003-Plugin-Manifest-Specification.md) | Plugin Manifest Specification | Plugins | Accepted | YAML manifests for sensors, skills, personalities, packs |
| [0004](ADR-0004-Memory-Schema-Details.md) | Memory Schema Details | Memory | Accepted | L0-L4 hierarchy, PostgreSQL + pgvector, EWMA profiling |
| [0005](ADR-0005-gRPC-Service-Contracts.md) | gRPC Service Contracts | Contracts | Accepted | Proto definitions, transport strategies, latency budgets |
| [0006](ADR-0006-Observability-and-Monitoring.md) | Observability and Monitoring | Observability | Accepted | Prometheus, Loki, Jaeger, Grafana stack |
| [0007](ADR-0007-Adaptive-Algorithms.md) | Adaptive Algorithms | Intelligence | Accepted | EWMA adaptation, Bayesian confidence, user controls |
| [0008](ADR-0008-Security-and-Privacy.md) | Security and Privacy | Security | Accepted | Permissions, sandboxing, age restrictions, data retention |
| [0009](ADR-0009-Memory-Contracts-and-Compaction-Policy.md) | Memory Contracts and Compaction | Memory | Accepted | Episodic ingest/query, compaction tiers, provenance |
| [0010](ADR-0010-Learning-and-Inference.md) | Learning and Inference | Intelligence | Accepted | System 1/2 split, outcome evaluation, deferred validation |
| [0011](ADR-0011-Actuator-Subsystem.md) | Actuator Subsystem | Actuators | Accepted | Device control, trust tiers, safety, rate limiting |
| [0012](ADR-0012-Audit-Logging.md) | Audit Logging | Security | Accepted | Append-only audit, Merkle trees, retention policy |
| [0013](ADR-0013-Salience-Subsystem.md) | Salience Subsystem | Salience | Accepted | Attention filtering, habituation, budget allocation |
| [0014](ADR-0014-Executive-Decision-Loop.md) | Executive Decision Loop | Executive | Accepted | Decision framework, skill orchestration, proactive scheduling |
| [0015](ADR-0015-Personality-Subsystem.md) | Personality Subsystem | Personality | Accepted | Response Model traits, humor, user customization |

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

For those new to the project:

1. **[SUBSYSTEM_OVERVIEW.md](../design/SUBSYSTEM_OVERVIEW.md)** - Start here for high-level understanding
2. **[GLOSSARY.md](../design/GLOSSARY.md)** - Key terminology
3. **ADR-0001** - Foundational architecture and language decisions
4. **ADR-0010** - Learning architecture (System 1/2 split)
5. **ADR-0004 + ADR-0009** - Memory system
6. **ADR-0013 + ADR-0014** - Salience and Executive (decision pipeline)
7. **Other ADRs as needed** - Reference by topic

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
ADR-0001 (Architecture) ─────────────────────────────────────────┐
    │                                                            │
    ├──► ADR-0002 (Hardware)                                     │
    │                                                            │
    ├──► ADR-0003 (Plugin Manifest) ◄─── ADR-0008 (Security)     │
    │         │                              │                   │
    │         ▼                              │                   │
    ├──► ADR-0004 (Memory Schema) ◄─────────┤                   │
    │         │                              │                   │
    │         ├──► ADR-0009 (Memory Contracts)                   │
    │         │                                                  │
    │         └──► ADR-0010 (Learning) ◄── ADR-0007 (Adaptive)  │
    │                   │                                        │
    │                   └──► ADR-0003 (outcome_evaluator)        │
    │                                                            │
    ├──► ADR-0005 (gRPC Contracts)                               │
    │                                                            │
    ├──► ADR-0006 (Observability)                                │
    │                                                            │
    ├──► ADR-0011 (Actuators) ◄───── ADR-0008 (Security)        │
    │         │                                                  │
    │         └──► ADR-0012 (Audit)                              │
    │                                                            │
    ├──► ADR-0013 (Salience) ◄────── ADR-0007 (Adaptive)        │
    │         │                                                  │
    │         └──► ADR-0014 (Executive) ◄── ADR-0015 (Personality)
    │                                                            │
    └────────────────────────────────────────────────────────────┘
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
