# Urgency and Heuristic Selection

## Open Questions

### Q: How should urgency modulate heuristic selection strategy?
**Status**: Open
**Priority**: High
**Created**: 2026-02-08

Current heuristic selection uses a binary confidence threshold (0.7) — above fires, below goes to LLM. This should be replaced with an urgency-modulated continuous threshold that adapts to how quickly a response is needed.

**Proposed model**:
```
effective_threshold = base_threshold - (urgency * threshold_reduction)
```

High urgency lowers the bar for heuristic firing; low urgency raises it (or keeps baseline, preferring LLM).

**Three behavioral tiers**:

| Tier | Trigger | Data source | Behavior |
|------|---------|-------------|----------|
| (a) Immediate | High urgency | Cache first, DB fallback | Fire any reasonable match — speed over quality |
| (b) Soon | Moderate urgency | DB always | Use weighted selection from full candidate pool |
| (c) Not urgent | Low urgency | DB + LLM preferred | Only fire singular high-match + high-confidence heuristic; otherwise LLM |

**Selection ranking**: Similarity-dominant (context match weighted more than confidence). Confidence is tiebreaker when similarities are close. A 0.3-confidence heuristic with 0.9 context match beats a 0.7-confidence heuristic with 0.6 context match.

**Urgency sources** (two-phase):
1. Pre-routing (fast): Sensor-provided urgency + salience threat score. Coarse but immediate. Decides cache vs DB vs LLM path.
2. In-executive (rich): Domain skill assesses full urgency with domain knowledge. Affects response strategy, not routing.

Urgency is domain-specific: real-time games need sub-second, email can wait minutes.

**Sub-questions**:
1. What is the formula for combining similarity and confidence in selection? Weighted sum? Multiplicative?
2. Should urgency be a new field on Event, a salience dimension, or derived from existing fields?
3. Where does the sensor declare its urgency profile? Manifest? Registration? Per-event?
4. Should there be "salience heuristics" — learned condition-to-salience mappings that enrich urgency over time?

### Q: Should the Rust heuristic cache be used for Phase 2?
**Status**: Resolved
**Decision**: No cache for Phase 2. Encapsulate heuristic lookup behind an interface that could add a cache layer later. DB is sole source of truth. If a cache is added in future, it must be read-through only (never write-back) and domain-partitioned.
**Rationale**: The cache saves 1-10ms on a local PostgreSQL query. This is meaningful only for tier (a) immediate responses. Cache coherence adds complexity (syncing confidence updates between cache and DB). The DB round-trip is not the bottleneck — LLM latency is. Keep infrastructure, don't invest in making it smarter until performance data shows need.
**Date**: 2026-02-08

**Related**: CONFIDENCE_BOOTSTRAPPING.md, DECISION_STRATEGY.md, SALIENCE_MODEL.md, SENSOR_ARCHITECTURE.md (urgency metadata)

