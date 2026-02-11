# Phase 1: Closed-Loop Learning with Real Data

**Status**: Active
**Successor**: [Phase 2](phase2.md)

### Question to answer

Can the system learn from experience with real data flowing through it?

This is the core value proposition: "the second time is faster." It requires multiple co-dependent workstreams that must converge - you can't test learning without real data, and you can't get meaningful data without real sensors.    

### Framing: Accuracy-Latency Tradeoff

Phase 1 doesn't need to solve the general resource allocation problem, but it lays the foundation. The heuristic firing threshold IS an accuracy-latency tradeoff decision - "when is a cached answer good enough to skip reasoning?" Getting this framing right now prevents rework in Phase 2 when real volume arrives.

### Workstreams

#### W1: One Real Sensor
Build one real sensor that produces events without human intervention. Must emit events through the Orchestrator pipeline via gRPC.

#### W2: Learning Module
Orchestrator-owned module with clean interface. Implements outcome channel consumption, confidence updates, and pattern extraction.

#### W3: Feedback Pipeline Fixes
- Add `feedback_source` to `UpdateHeuristicConfidenceRequest`.
- Add `GetHeuristic` RPC.
- Fix cache to be authoritative for heuristic matching.

#### W4: Heuristic Creation from Feedback
LLM extracts generalizable pattern from successful reasoning. New heuristics start at confidence 0.3.

### Success Criteria

| # | Criterion | Observable evidence |
|---|-----------|-------------------|
| 1 | Heuristic creation works | Positive feedback -> new heuristic in DB with confidence=0.3 |
| 2 | Semantic matching works | Heuristic fires on semantically similar events with >0.6 similarity |
| 3 | Confidence tracks reality | 10+ fires with pos/neg feedback reflects in confidence score |
| 4 | Bad heuristics decay | Repeated negative feedback -> confidence drops below firing threshold (0.7) |

### Abort Signals

- **Embeddings don't discriminate**: Similar events don't match, or dissimilar events match too broadly.
- **LLM generates bad condition_text**: Conditions are consistently too vague or too specific.
- **Confidence oscillates**: Beta-Binomial doesn't converge - swings wildly with each feedback signal.
