# Learning Loop Design

**Status**: Draft
**Created**: 2026-01-26
**Authors**: Scott, Mike, Claude

## Overview

This document captures the design for GLADyS's learning loop — how heuristics are matched, scored, and improved over time.

**Related**: [POC_ROADMAP.md](POC_ROADMAP.md) Scenarios 4 & 5 validate this design. See also [ADR-0010](../adr/ADR-0010-Learning-Pipeline.md) for architectural decisions.

## Core Insight

Heuristics are **fast shortcuts** that provide immediate responses. Deep Bayesian analysis happens **offline** during idle time. Real-time updates are "best effort" - wrong sometimes, refined later.

---

## Milestone 1: Basic Learning Loop (POC Target)

**Goal**: Demonstrate end-to-end learning works.

**Success criteria**:
- [ ] Event → heuristic match → response (fast path works)
- [ ] Explicit feedback (good/bad buttons) updates confidence
- [ ] Confidence changes persist and affect future matching
- [ ] Fire records stored for analysis

**Cutoff**: If semantic matching doesn't work reliably, fall back to explicit feedback only.

### What's blocking us now

1. **Heuristic matching fails** - Events don't match heuristics despite 0.72 similarity
2. **Need to debug**: Rust → Python query flow

### Immediate actions

1. Fix the heuristic matching issue (debug salience pipeline)
2. Verify explicit feedback path works (dashboard good/bad buttons)
3. Test confidence updates persist

---

## Milestone 2: Richer Scoring (Post-POC)

**Goal**: Better heuristic selection using multiple signals.

**Signals to incorporate**:
- Historical success rate (fire_count, success_count)
- Recency (last_fired, last_success)
- Source/domain match
- Origin weight (skill_pack > llm > unknown)
- Fire frequency (habituation penalty)

**Composite score**:
```python
score = (
    confidence
    * (1 + source_match * 0.2)
    * recency_decay(last_success)
    * origin_weight[heuristic.origin]
    * habituation_penalty(fire_rate)
)
```

---

## Milestone 3: Outcome Detection (Future)

**Goal**: Implicit feedback from observed outcomes.

**Realistic ceiling**: ~50% accuracy for text pattern matching alone.

**Role**: Supplementary signal, not primary. Explicit feedback remains most reliable.

**Defer until**: Milestone 1 and 2 are working.

---

## Milestone 4: Dynamic Urgency (Future)

**Goal**: Escalate warnings based on context.

**Concepts**:
- Time-to-action estimation
- Urgency escalation for repeated threats
- Heuristic + reasoning hybrid (draft → refine)

**Defer until**: Core learning loop is solid.

---

## Architecture Notes

### Where things live

| Capability | Location | Notes |
|------------|----------|-------|
| Heuristic matching | Rust Salience Gateway | Semantic similarity via Python |
| Scoring/ranking | Orchestrator | Needs enhancement |
| Outcome detection | OutcomeWatcher (Orchestrator) | Keep simple for now |
| Fire recording | Memory (heuristic_fires table) | Already exists |
| Offline learning | TBD | Future batch job |

### Data we need to capture

For offline analysis, record:
- Every heuristic fire (which heuristic, which event, context)
- Every outcome observation (which fire, what happened)
- Every explicit feedback (which response, good/bad)
- Similarity scores at match time

---

## Open Questions

1. Is 0.7 similarity threshold too high? Test with lower values.
2. Should we expose similarity scores in dashboard for debugging?
3. What's the right balance of explicit vs implicit feedback weight?

---

## Next Steps

1. **Now**: Debug why heuristic matching isn't returning matches
2. **Then**: Verify explicit feedback updates confidence
3. **Then**: Add fire recording if not already working
4. **Later**: Richer scoring, outcome detection, urgency
