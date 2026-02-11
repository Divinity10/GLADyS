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
