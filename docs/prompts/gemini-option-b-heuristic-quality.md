# Task: Validate Heuristic Extraction Quality (Option B)

## Context

GLADyS learns from user feedback by extracting "heuristics" - patterns the system can recognize in the future. The extraction happens in `src/executive/stub_server.py` via `PATTERN_EXTRACTION_PROMPT`.

The **concern**: We don't know if the LLM produces heuristics that are actually *matchable* by the fast path. A heuristic that's too verbose, too specific, or hallucinated won't fire when it should.

## Your Task

1. **Read** `src/executive/stub_server.py` to understand:
   - The `PATTERN_EXTRACTION_PROMPT` format
   - What fields are extracted (condition, action, name)
   - How they're used

2. **Create 8-10 diverse test scenarios** representing different domains:
   - Gaming (Minecraft): "Player health dropped to 3 hearts after creeper explosion"
   - Smart home: "User manually turned off the lights GLADyS just turned on"
   - Productivity: "User dismissed the meeting reminder without responding"
   - Social: "Friend Steve came online after being offline for a week"
   - Mix of positive and negative feedback contexts

3. **For each scenario**, manually run the extraction prompt (using Ollama or document what you'd expect) and evaluate:
   - Is the `condition` semantic enough to match similar future events?
   - Is it too specific (overfitting to this exact event)?
   - Is it too vague (would match unrelated events)?
   - Does the `action` make sense?

4. **Produce a report** (`docs/validation/heuristic_quality_report.md`) with:
   - Each scenario + the extracted heuristic
   - Quality rating (Good / Marginal / Bad)
   - Specific issues identified
   - Recommendations for prompt tuning if needed

## Success Criteria

A "good" heuristic:
- Condition uses **general terms** (e.g., "player health critical" not "player health exactly 3 hearts")
- Condition captures the **semantic meaning** (what happened) not surface details
- Action is **actionable** (clear what GLADyS should do)
- Would plausibly match a similar future event

## Files to Reference
- `src/executive/stub_server.py` - PATTERN_EXTRACTION_PROMPT
- `docs/design/LEARNING_VALIDATION_OPTIONS.md` - Context for this task
- `docs/design/OPEN_QUESTIONS.md` Section 22 - Heuristic data structure design

## Output
Write your findings to `docs/validation/heuristic_quality_report.md`
