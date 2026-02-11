# Phase 7: Design Evaluation & Tech Debt

**Status**: Planned
**Predecessor**: [Phase 6](phase6.md)

### Question to answer

Is the current architecture sustainable for future phases, or do we need major refactoring to address accumulated technical debt and design weaknesses discovered in Phases 1-6?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Tech debt is catalogued | Documented list of pain points, workarounds, and design compromises from Phases 1-6. |
| 2 | Design weaknesses identified | Clear understanding of what didn't scale, what's fragile, what violates principles. |
| 3 | Refactor vs. iterate decision made | Data-driven choice: continue with current design + minor fixes OR major refactor + migration plan. |
| 4 | If refactoring: scope defined | Clear boundaries on what gets rewritten, what stays, migration strategy, rollback plan. |
| 5 | If iterating: constraints documented | Explicit limits we're accepting (e.g., "won't scale beyond X sensors", "LLM latency bottleneck remains"). |
| 6 | Team consensus | Mike and Scott agree on the path forward; no unresolved architectural disagreements. |

### Abort Signals

- **Can't identify problems**: System seems fine but gut says it's not; no concrete issues to address.
- **Problems too vague**: "Everything feels messy" but can't pinpoint what's actually broken or limiting.
- **Refactor scope explodes**: Every issue connects to everything else; no bounded refactoring possible, only full rewrite.
- **Team can't agree**: Fundamental disagreement on what's broken or how to fix it.
- **No clear decision criteria**: Can't define what would make us choose refactor vs. continue.

### Dependencies

- Phases 1-6 must be complete with honest retrospectives
- Need working system to evaluate (can't assess tech debt in theory)
- Requires metrics showing where performance/complexity/maintainability suffer
- Should have attempted at least one cross-phase change to see coupling issues

---

**Note**: This is a checkpoint, not new features. Output is a decision (refactor or iterate) and a plan. If refactoring, Phases 8+ may shift significantly. If iterating, Phases 8+ proceed as planned with documented constraints.
