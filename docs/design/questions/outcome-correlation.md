# Outcome Correlation

## Open Questions

### Q: How does the system match decisions to outcome events?

**Status**: Open
**Priority**: High
**Created**: 2026-02-08

When GLADyS makes a decision (fire a heuristic or generate an LLM response), we need to later detect whether the suggested action was taken and whether it produced a good outcome. This requires correlating decisions with follow-up events.

**Examples**:

- Response: "Use a healing potion" → Follow-up event: "Player used healing potion" → Action was taken
- Response: "Read this email from your boss" → Follow-up event: "User opened email from boss" → Action was taken
- Response: "Attack the skeleton" → Follow-up event: "Player died to skeleton" → Action taken but outcome bad

**Design constraints**:

- ADR-0010 §3.11 defines OutcomeEvaluator with `correlation_window_ms` for temporal matching
- ADR-0003 §6.4 defines skill manifest `outcome_signals` with event types and valence
- The `heuristic_fires` table has `outcome` (success/fail/unknown) and `feedback_source` columns ready for this
- No RPC currently exists for skills to report outcomes back to memory/orchestrator

**Sub-questions**:

1. How do we match a suggested action to a follow-up event? Embedding similarity between action text and event text? Domain skill defines explicit mappings?
2. What time window is appropriate? Domain-specific (games: seconds, email: hours)?
3. How do we handle coincidental matches (user was already going to do that)?
4. Should action-taken rate be a separate metric from success rate?

### Q: How do we retroactively evaluate non-fired heuristics after an outcome?

**Status**: Open
**Priority**: Medium
**Created**: 2026-02-08

After observing an outcome (action taken + result known), we can evaluate ALL heuristics that matched the context — not just the one that fired. This is experience replay: each outcome teaches the system about multiple heuristics simultaneously.

**Mechanism**:

1. Event arrives → heuristic H1 fires (or LLM responds) → user takes action → outcome observed
2. Query all heuristics that matched this event's context (by condition embedding similarity)
3. For each: would this heuristic's action have produced the correct outcome?
4. Boost heuristics whose actions align with the successful outcome; penalize those that don't

**Design constraints**:

- Requires knowing which action was "correct" (depends on outcome evaluator)
- Requires embedding similarity between heuristic actions and the successful action
- Same pgvector infrastructure used for bootstrapping comparison
- Must be source-filtered (same domain only)

**Open**: Is counterfactual evaluation (what would have happened if H2 fired instead of H1) tractable, or should we limit to "does H2's action match the observed successful action"?

**Related**: CONFIDENCE_BOOTSTRAPPING.md §Three Measurement Dimensions, ADR-0010 §3.11, §3.12 (deferred validation queue)
