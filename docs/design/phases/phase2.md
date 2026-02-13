# Phase 2: Multi-Sensor Pipeline

**Status**: Planning
**Predecessor**: [Phase 1](phase1.md)

### Question to answer

Can GLADyS operate as a multi-sensor system - multiple sensors from different domains, written in different languages, running concurrently with events processed correctly and learning scoped to domains?

### Workstreams

#### W5: Event Volume Management
Address the accuracy-latency tradeoff under real-world event volume. Concurrent event processing, deduplication, and suppression.

**Salience model**: Phase 2 uses the salience model defined in [`SALIENCE_MODEL.md`](../SALIENCE_MODEL.md) — 3 scalars (threat, salience, habituation) + 5 vector dimensions (novelty, goal_relevance, opportunity, actionability, social). Threat bypasses habituation and queue. Salience computed via weighted sum from vector.

#### W6: Second Sensor
Add sensors from different domains. Validates protocol-first architecture, cross-domain behavior, and concurrent sensor handling.

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Multiple sensors concurrent | RuneScape + Gmail sensors running simultaneously; no unaccounted drops. |
| 2 | Sensor protocol viable | Java and JS/TS sensors register and publish without unplanned proto changes. |
| 3 | Source-domain scoping | Zero cross-domain heuristic matches (e.g., RuneScape heuristic never fires on email). |
| 4 | Event volume manageable | Heuristic path <500ms p95; LLM path <10s p95. |
| 5 | Concurrent LLM requests | Executive handles multiple simultaneous LLM requests without serialization or starvation. |

### Abort Signals

- **Pipeline cannot keep up**: Sustained sensor output leads to silent event drops despite fixes.
- **Protocol inadequate**: SDK abstraction or protocol requires fundamental redesign for real sensors.
- **Embedding space crowded**: False-positive matches dominate despite source filtering.

---

## Phase 2 Retrospective

**Status**: To be completed at Phase 2 conclusion

### Technical Decisions

1. **Pattern usage**: Where did we use strategy pattern vs DI? Which choices were correct? Which need refactoring?
2. **Interface stability**: Which interfaces are stable enough to lock down (breaking changes require ADR)?
3. **Protocol changes**: What unplanned proto changes occurred? Were they avoidable with better upfront design?

### Design Learnings

1. **Salience calculation**: Did the weighted-sum approach work? Do we need runtime selection or just DI for swapping implementations?
2. **Multi-sensor handling**: What unexpected challenges emerged? How did we solve them?
3. **Learning scope**: Did source-domain scoping prevent cross-contamination as expected?

### Process & Refactoring

1. **Iteration pain**: What refactoring was most costly? Could stable interfaces have reduced churn?
2. **Test coverage**: Did our testing approach catch issues early? What gaps existed?
3. **Dashboard tooling**: What validation tooling did we build? What's still needed?

### Going Forward

1. **Lock down**: What interfaces/contracts should we stabilize before Phase 3?
2. **Keep flexible**: What should remain experimental?
3. **Refactoring debt**: What needs to be refactored before Phase 3? Prioritize by impact.
4. **Documentation needs**: What conventions should we document now (CONVENTIONS.md, STABLE_INTERFACES.md)?
