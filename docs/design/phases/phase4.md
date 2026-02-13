# Phase 4: Skill-Based Learning

**Status**: Planned
**Predecessor**: [Phase 3](phase3.md)

## Question to answer

Can the learning system use domain skill feedback to improve accuracy - deriving success from skill evaluations rather than manual ratings, and adapting confidence based on skill-validated outcomes?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Skills drive learning | Heuristic confidence updates based on skill success/failure verdicts, not just user ratings. |
| 2 | Accuracy improves per domain | Success rate increases over time within each domain (measured by skill evaluations). |
| 3 | Skills don't interfere | Learning in Sudoku domain doesn't degrade Melvor performance; domains remain independent. |
| 4 | Skill feedback is timely | Success evaluation happens <1s after response; learning pipeline doesn't stall waiting for feedback. |
| 5 | Mixed feedback handled | System integrates both skill verdicts and user ratings; conflicting signals don't break learning. |

### Abort Signals

- **Skill feedback too noisy**: Success evaluations are inconsistent or incorrect; learning degrades instead of improving.
- **Latency kills learning**: Skill evaluation too slow; response-to-feedback loop breaks down.
- **Skills conflict with users**: User rates response highly but skill says failure (or vice versa); no resolution strategy.
- **Learning doesn't generalize**: Improvements on skill-tested scenarios don't transfer to real usage.

### Dependencies

- Phase 3 domain skills must be implemented and stable
- Need Phase 1/2 learning pipeline working
- Requires metrics to measure skill-based accuracy improvements

---

**Note**: This validates that domain skills are useful for learning, not just action safety. Workstreams defined during planning.
