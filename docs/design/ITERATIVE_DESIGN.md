# GLADyS Iterative Design Framework

**Status**: Living document
**Owners**: Mike Mulcahy, Scott Mulcahy

## Design Philosophy

GLADyS uses **hypothesis-driven incremental development**. We do not build throwaway prototypes; we build production-quality increments that answer specific architectural or product questions.

- **Iterative Design**: "Think -> Design -> Exploratory Code -> Build" cycle.
- **Phase-based Scope**: Each phase limits *what* we build, not *how well* we build it.
- **Hypothesis-Driven**: Every phase is designed to answer a specific question.
- **Abort Signals**: We define clear failure conditions that trigger a design rethink.

## Phase Lifecycle

Each phase follows a structured lifecycle to ensure we are learning and adapting:

1. **Planning**: Review lessons learned from previous phases and define the next question.
2. **Implementation**: Iterative development of features to address the phase's question.
3. **Validation**: Testing against success criteria and documenting proven vs. assumed facts.
4. **Learning**: Formalizing findings and feeding them into the next planning session.

## Current and Planned Phases

- **[PoC 0: Exploratory](phases/phase0.md)** (COMPLETE) - Can we build individual subsystems and get them communicating?
- **[Phase 1: Closed-Loop Learning](phases/phase1.md)** (ACTIVE) - Can the system learn from experience with real data?
- **[Phase 2: Multi-Sensor Pipeline](phases/phase2.md)** (PLANNING) - Can we handle concurrent multi-domain sensors and scoped learning?

See the [Future Roadmap](#future-roadmap) for upcoming topics.

## Testing & Validation Philosophy

If a success criterion is not observable, it isn't proven. We build validation tooling (Dashboard extensions, CLI scripts) alongside the core features to make claims verifiable.

- **Convergence Tests**: End-to-end scenarios that prove multiple workstreams meet.
- **Baseline Metrics**: Measuring performance before and after changes.
- **Honesty about Gaps**: Explicitly documenting what was NOT proven in a phase.

## Future Roadmap

Potential future phases include:
- **Learning Maturity**: Sleep-mode consolidation, heuristic decay, and scale.
- **Actuators**: Response execution and conflict resolution.
- **Personality**: Behavioral profiles and tone consistency.
- **Episodic Memory**: Temporal context and event segmentation.

---
*This document replaces the legacy `POC_LIFECYCLE.md`.*
