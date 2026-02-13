# Phase 9: Personality

**Status**: Planned
**Predecessor**: [Phase 8](phase8.md)

## Question to answer

Can GLADyS maintain consistent behavioral patterns and tone - responding in ways that reflect user preferences, adapting personality per domain, and ensuring responses feel coherent over time?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Tone consistency measurable | Responses in same domain maintain consistent formality/humor/verbosity; blind A/B test shows user can identify "same assistant." |
| 2 | Domain-specific personalities work | Gaming domain uses casual tone, work domain uses formal tone; no cross-contamination. |
| 3 | User preferences persist | User adjusts personality settings (e.g., "more concise"); future responses reflect changes. |
| 4 | Personality doesn't override correctness | Tone/style changes don't degrade accuracy; system prioritizes right answer over stylistic consistency. |
| 5 | Learning preserves personality | Heuristic reinforcement doesn't flatten personality; distinct response styles remain distinguishable. |
| 6 | Episodic context informs tone | Personality adapts based on recent interactions (e.g., user seems stressed → more supportive tone). |

### Abort Signals

- **Personality is noise**: User testing shows tone consistency doesn't improve satisfaction or trust.
- **Configuration explosion**: Per-domain, per-user, per-context settings become unmaintainable.
- **LLM cannot maintain consistency**: Model drift or prompt engineering limitations prevent reliable tone control.
- **Conflicts with correctness**: Personality constraints force incorrect or unhelpful responses.
- **Episodic adaptation backfires**: Tone changes based on context feel unpredictable or inappropriate.

### Dependencies

- Phase 3 domain skills define appropriate tone per context
- Phase 5 episodic memory provides interaction history
- Phase 8 response model must support tone/style metadata
- Requires user preference storage and retrieval
- Need LLM prompt engineering or fine-tuning infrastructure

---

**Note**: This builds on actuators (responses are being executed) and episodic memory (tone adapts to history). Workstreams defined during planning.
