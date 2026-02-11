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
- **[Phase 1: Closed-Loop Learning](phases/phase1.md)** (COMPLETE) - Can the system learn from experience with real data?
- **[Phase 2: Multi-Sensor Pipeline](phases/phase2.md)** (ACTIVE) - Can we handle concurrent multi-domain sensors and scoped learning?
- **[Phase 3: Domain Skills](phases/phase3.md)** (PLANNED) - Can we define skill interfaces for success evaluation and action boundaries?
- **[Phase 4: Skill-Based Learning](phases/phase4.md)** (PLANNED) - Can learning improve using domain skill feedback?
- **[Phase 5: Episodic Memory](phases/phase5.md)** (PLANNED) - Can we reason about temporal context and past experiences?
- **[Phase 6: Advanced Learning + Sleep Cycle](phases/phase6.md)** (PLANNED) - Can we consolidate knowledge at scale using episodic patterns?
- **[Phase 7: Design Evaluation & Tech Debt](phases/phase7.md)** (PLANNED) - Is the architecture sustainable, or do we need major refactoring?
- **[Phase 8: Response Model & Actuators](phases/phase8.md)** (PLANNED) - Can we safely execute responses in external systems?
- **[Phase 9: Personality](phases/phase9.md)** (PLANNED) - Can we maintain consistent behavioral patterns and tone?
- **[Phase 10: Dynamic Tuning](phases/phase10.md)** (PLANNED) - Can the system adaptively tune its own configuration?

**Note**: This is a rough draft roadmap. Phase ordering and focus will evolve based on learnings from earlier phases.

## Testing & Validation Philosophy

If a success criterion is not observable, it isn't proven. We build validation tooling (Dashboard extensions, CLI scripts) alongside the core features to make claims verifiable.

- **Convergence Tests**: End-to-end scenarios that prove multiple workstreams meet.
- **Baseline Metrics**: Measuring performance before and after changes.
- **Honesty about Gaps**: Explicitly documenting what was NOT proven in a phase.

## Beyond Phase 10

Additional exploration areas not yet scoped into phases:
- **Multi-User Support**: User profiles, preference isolation, shared vs personal knowledge
- **Cross-Domain Synthesis**: Insights from one domain informing another (e.g., work stress patterns affecting health recommendations)
- **Proactive Suggestions**: System-initiated responses based on predicted needs
- **Federated Learning**: Optional cross-device knowledge sharing with privacy preservation

---
*This document replaces the legacy `POC_LIFECYCLE.md`.*
