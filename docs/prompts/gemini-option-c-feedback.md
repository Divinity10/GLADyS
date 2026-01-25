# Feedback on Integration Test Scenarios (Option C)

You created `docs/validation/integration_test_scenarios.md`. Good work on the overall structure - Scenarios 1-3 and 5 are solid. Here's feedback to address before we implement.

## Issues to Fix

### 1. Missing Scenario: Ambiguous Attribution
The original prompt requested testing "ambiguous attribution" - what happens when multiple heuristics fired recently and a single feedback event arrives. Add a scenario for this:
- Initial state: H1 and H2 both fired within last 30 seconds
- Feedback arrives (positive or negative)
- Expected behavior: Define how credit/blame is distributed

### 2. Scenario 4 (Domain Safety): Design Decision Made
We discussed this and decided: **embed domain context in the condition string itself** rather than adding a separate domain filter field.

Update Scenario 4 to test this approach:
- Heuristic condition should be: `"gaming: high score achieved"` (with domain prefix)
- The cross-domain event `"work: Credit Score report: 800"` should NOT match because the embeddings for "gaming: high score" and "work: credit score" will be sufficiently distant
- This tests that domain-prefixed conditions naturally separate in embedding space

### 3. Scenario 1 Step 3: Make Deterministic
"Might still hit LLM" is not testable. Pick one:
- **Option A**: Assert it DOES hit LLM (confidence 0.3 < threshold), then verify confidence increases
- **Option B**: Skip this step, go directly from Step 2 to Step 4 (manual boost)

Recommend Option A - it explicitly tests the sub-threshold behavior.

### 4. Threshold Value: Confirm or Parameterize
You used 0.5 as the confidence threshold. Either:
- Cite where this comes from in the codebase, OR
- Note that tests should read the threshold from config (not hardcode)

### 5. Add Instrumentation Scenario
Our "Instrument Now, Analyze Later" decision means we record predictions even before acting on them. Add a scenario (can be simple):
- Send an event that triggers LLM reasoning
- Verify that `predicted_success` and `prediction_confidence` fields are recorded in the episode/response
- No behavioral assertion needed - just data capture verification

## Deliverable
Update `docs/validation/integration_test_scenarios.md` with these changes. Don't create the Python test file yet - we'll review the updated plan first.
