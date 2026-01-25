# Task: Design Integration Test Scenarios (Option C)

## Context

Option B (heuristic extraction quality) passed with high quality. Now we need to test the **full learning loop** end-to-end:

1. Event arrives from sensor
2. Heuristic matches (fast path) or doesn't (LLM fallback)
3. Action fires
4. User provides feedback (explicit or implicit)
5. Confidence updates (or heuristic forms)

## Background

- **Option B Results**: 8/8 scenarios extracted generalizable heuristics
- **§22**: CBR matching with `condition_embedding` similarity
- **§27**: Hybrid prediction baseline (interpolation + extrapolation)
- **§23**: Credit assignment UX (silent learning by default)

## Your Task

Design **6-8 integration test scenarios** that exercise the complete learning loop.

### Scenario Types to Cover

1. **Heuristic cache hit** - Event matches existing heuristic, fires immediately (fast path)
2. **Heuristic cache miss** - No match, falls back to LLM reasoning
3. **Positive feedback** - User says "thanks" or follows through → confidence increase
4. **Negative feedback (undo)** - User immediately reverses action → confidence decrease
5. **Heuristic formation** - Positive feedback on LLM response → new heuristic extracted
6. **Similar-but-not-exact matching** - Event is close to heuristic but not identical
7. **Confidence threshold** - Heuristic exists but confidence too low to fire
8. **Ambiguous attribution** - Multiple heuristics fired recently, feedback arrives

### For Each Scenario, Define:

```markdown
## Scenario X: [Name]

**Purpose**: What this tests

### Initial State
- Existing heuristics (id, condition_text, confidence, fire_count)
- Episodic events (if needed for extrapolation)

### Input
- Event source and payload
- Simulated time

### Expected Behavior
- Which path: fast (heuristic) or slow (LLM)?
- Which heuristic matches (if any)?
- What action fires?

### Feedback
- Type: explicit/implicit/undo/none
- Timing: immediate/delayed
- Content: "thanks" / undo action / silence

### Expected Final State
- Confidence changes
- New heuristics created?
- Fire count updates
```

### Test Data Guidelines

Use the same domains as Option B for consistency:
- **Gaming**: Minecraft health, high scores
- **Smart Home**: Lights, temperature, motion
- **Productivity**: Calendar, meetings
- **Social**: Friend status

### Edge Cases to Consider

- What happens when similarity is 0.68 vs 0.72 (near threshold)?
- What if two heuristics both match with similar scores?
- What if heuristic fires but user is silent (no feedback)?
- What if LLM produces a heuristic that's nearly identical to existing one?

## Files to Reference

- `docs/design/OPEN_QUESTIONS.md` §22, §23, §27
- `docs/validation/heuristic_quality_report.md` - Option B results
- `docs/validation/ollama_extraction_results.json` - Actual Ollama output
- `src/executive/stub_server.py` - PATTERN_EXTRACTION_PROMPT

## Output

Write to `docs/validation/integration_test_scenarios.md`

Include:
1. Overview of what the test suite covers
2. 6-8 detailed scenarios
3. Expected test infrastructure requirements
4. Success criteria for each scenario
