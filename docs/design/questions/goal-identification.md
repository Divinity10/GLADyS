# Goal Identification

## Open Questions

### Q: How does the system identify and use the user's current goals?
**Status**: Open
**Priority**: Medium
**Created**: 2026-02-08

Success is goal-dependent. "Killing teammates" is a success if that's the player's goal. The system needs to know the user's goals to:
1. Generate goal-directed LLM responses (goal context in prompt)
2. Evaluate outcome correctness (did the action achieve the goal?)
3. Select appropriate heuristics (which heuristic serves this goal?)
4. Assess urgency (is this event relevant to active goals?)

**Current state**: `EXECUTIVE_GOALS` env var (semicolon-separated strings). Static, manually configured. `DecisionContext.goals` carries them to the decision strategy. Goals are injected into the LLM system prompt.

**Goal types to consider**:
- **Explicit**: User declares ("I want to level up mining")
- **Inferred**: System observes behavior ("user keeps fighting monsters" → combat progression goal)
- **Domain-default**: Skill pack provides typical goals ("survive", "progress", "optimize")
- **Changing**: Goals shift mid-session ("was grinding, now exploring")
- **Conflicting**: "Level up fast" vs "have fun" (sometimes these conflict)

**Impact on other systems**:
- **LLM prompts**: Goal context affects response generation. Without goal awareness, the LLM optimizes for generic "helpfulness" rather than the user's actual objective.
- **Outcome evaluation**: Domain skill evaluators need to know the goal to judge success. A gaming evaluator judging "did the player survive?" assumes survival is the goal.
- **Heuristic pre-builds**: Pre-built heuristics are designed for common goals. Their starting confidence should reflect how well they serve a particular goal profile.
- **Success rate**: `success_count / fire_count` is meaningless without goal context — success relative to WHAT goal?

**Sub-questions**:
1. For Phase 2, is static goal configuration sufficient? Or do we need at minimum per-domain goals from the skill manifest?
2. How should goal changes be detected? User declares? Behavioral inference? Domain skill detects?
3. Should goals be hierarchical (long-term: "beat the game", short-term: "survive this fight")?
4. How does goal context flow through the pipeline? Event metadata? Separate context channel?

**Phase 2 approach**: Static per-domain goals from config. Dynamic selection deferred. Design interfaces to accept goal context so future implementations can provide richer goal awareness.

**Related**: EXECUTIVE_DESIGN.md, DECISION_STRATEGY.md (F-07), CONFIDENCE_BOOTSTRAPPING.md §Three Measurement Dimensions, ADR-0010 §3.11 (outcome evaluation)

