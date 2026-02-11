# Phase 6: Advanced Learning + Sleep Cycle

**Status**: Planned
**Predecessor**: [Phase 5](phase5.md)

### Question to answer

Can GLADyS maintain learning quality at scale - consolidating knowledge during idle periods using episodic patterns, implementing heuristic decay, and handling thousands of heuristics without performance degradation?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Sleep-mode consolidation works | Heuristics merge/prune during idle periods using episodic context; embedding space density decreases without losing coverage. |
| 2 | Heuristic decay prevents staleness | Low-confidence or unused heuristics degrade over time; system doesn't accumulate dead weight. |
| 3 | Scale doesn't degrade performance | 1000+ heuristics in DB; selection still <500ms p95 on heuristic path. |
| 4 | Consolidation improves accuracy | Post-consolidation accuracy >= pre-consolidation on skill-validated test set. |
| 5 | System recovers from bad learning | Negative feedback loop (repeated failures) triggers rollback or heuristic removal. |
| 6 | Episodic patterns inform consolidation | Similar episodes lead to heuristic merging; dissimilar episodes prevent over-generalization. |

### Abort Signals

- **Consolidation destroys knowledge**: Merging heuristics loses critical distinctions; accuracy drops significantly.
- **Scale breaks selection**: Performance degrades linearly/exponentially with heuristic count despite indexing.
- **Decay too aggressive**: System forgets valid patterns before they can be reinforced.
- **No clear consolidation strategy**: Cannot define merge criteria that preserve accuracy using episodic context.
- **Sleep cycle unreliable**: Idle detection fails or consolidation runs during active use, degrading UX.

### Dependencies

- Phase 5 episodic memory must provide segmentation and patterns
- Phase 4 skill-based learning provides accuracy metrics
- Need observability into heuristic similarity and usage patterns
- Requires metrics infrastructure for tracking accuracy/confidence over time

---

**Note**: This is the first phase leveraging episodic memory for learning improvements. Workstreams defined during planning.
