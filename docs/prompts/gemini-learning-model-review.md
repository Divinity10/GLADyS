# Task: Review Learning Model Design

## Context

GLADyS is a self-learning AI assistant. We've been designing the heuristic learning infrastructure and want your critical review of the approach.

## The Design Discussion Summary

### Current Implementation
- Event arrives → check for matching heuristic (System 1)
- No match → LLM reasons → produces response (System 2)
- User gives positive feedback → LLM extracts pattern → stores as new heuristic

### Problem Identified
This only learns from **user feedback**. We're missing **outcome-based learning** - learning from what happens in the world without explicit user input.

Example: Player attacks monster and wins. GLADyS observes this. No feedback given, but there's a learnable pattern: "player at level X with weapon Y can defeat monster Z."

### Proposed Three-Path Learning Model

| Path | Trigger | When | Cost |
|------|---------|------|------|
| **Immediate** | User feedback | Real-time | 1 LLM call |
| **Observed** | World outcome | Real-time logging, batch analysis | Logging only |
| **Consolidated** | Idle/sleep | Background Pattern Detector | Deferred LLM calls |

### Key Insight: Predictions Enable TD Learning

For TD (Temporal Difference) learning, you need:
```
prediction_error = actual_outcome - predicted_outcome
```

No prediction = no error signal = no learning.

**Proposed solution**: Include prediction request in the reasoning prompt:

```json
{
  "response": "Watch out! Low health.",
  "prediction": {
    "type": "user_feedback",
    "expected": "positive"
  },
  "confidence": 0.8
}
```

### PoC Strategy: Instrument Now, Analyze Later

Even if we don't USE predictions for learning in PoC, we should COLLECT them:
- Measure performance impact of structured output
- Assess prediction accuracy (is LLM well-calibrated?)
- Model what TD learning WOULD have done with this data
- Make informed decisions about learning model post-PoC

## Your Task

Please review this design and provide:

1. **Critique**: What problems do you see with this approach?

2. **Alternatives**: Are there other learning paradigms we should consider?
   - Reinforcement learning variants beyond TD?
   - Approaches from cognitive science or neuroscience?
   - Production systems that solve similar problems?

3. **Prediction Quality**: Do you think LLMs can make well-calibrated predictions?
   - Are there known issues with LLM confidence estimation?
   - Should we structure the prediction request differently?

4. **Outcome Detection**: For "world outcome" learning, how do we know an outcome occurred?
   - Combat result is clear (win/lose event)
   - But "user found this helpful" without feedback is ambiguous
   - What outcome signals should we watch for?

5. **Pattern Detector Design**: The background consolidation job needs to:
   - Find correlations in logged observations
   - Propose candidate heuristics
   - Avoid overfitting to noise

   Any recommendations on algorithms or approaches?

## Files to Reference
- `src/executive/stub_server.py` - Current reasoning prompts and pattern extraction
- `docs/design/OPEN_QUESTIONS.md` - Sections 20-23 cover heuristic learning design
- `docs/design/LEARNING_VALIDATION_OPTIONS.md` - Validation roadmap

## Output
Write your analysis to `docs/reviews/learning_model_review.md`
