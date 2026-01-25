# Gemini Task: Stub Server Prediction Instrumentation

**Date**: 2026-01-24
**Assigned by**: Scott
**Parallel work**: Claude is working on domain filtering + cache invalidation (memory subsystem)

---

## Your Task

Populate the `predicted_success` and `prediction_confidence` fields in the Executive Stub server responses. These fields were added to the proto schema but nothing currently populates them.

**Goal**: When the stub server processes an event via LLM, it should record a prediction about whether the suggested action will succeed, along with confidence in that prediction.

---

## Files You SHOULD Modify

| File | What to do |
|------|------------|
| `src/executive/stub_server.py` | Add prediction fields to `ProcessEventResponse` |
| `src/integration/test_scenario_5_learning_loop.py` | Update Scenario 7 to verify prediction fields |

---

## Files You MUST NOT Modify

Claude is actively working on these files. Do not touch them:

- `src/memory/proto/memory.proto`
- `src/memory/python/gladys_memory/*.py`
- `src/memory/rust/src/*.rs`
- `src/orchestrator/proto/memory.proto`

---

## Implementation Details

### 1. stub_server.py Changes

The `ProcessEvent` RPC handler should:

1. After getting the LLM response, ask the LLM for a prediction about success
2. Parse the prediction into `predicted_success` (0.0-1.0) and `prediction_confidence` (0.0-1.0)
3. Include these in the `ProcessEventResponse`

**Suggested approach** (simple, testable):

```python
# After getting llm_response, ask for prediction
prediction_prompt = f"""Given this situation and response:
Situation: {event.raw_text}
Response: {llm_response}

Predict the probability this action will succeed (0.0-1.0) and your confidence in that prediction (0.0-1.0).
Return ONLY JSON: {{"success": 0.X, "confidence": 0.Y}}"""

prediction_json = await self._call_ollama(prediction_prompt)
# Parse and handle errors gracefully (default to 0.5/0.5 if parsing fails)
```

**Important**:
- Don't fail the request if prediction parsing fails - use defaults (0.5, 0.5)
- Log prediction parsing errors for debugging
- The prediction is informational only at this stage ("Instrument Now, Analyze Later")

### 2. Test Changes (Scenario 7)

Current Scenario 7 says "[Pass] Implicitly verified by Scenario 1 success" - this is a placeholder.

Replace with explicit verification:
1. Send an event that triggers LLM processing
2. Assert `ProcessEventResponse` contains non-default `predicted_success` and `prediction_confidence`
3. Optionally: Store the event and verify the fields persist to Memory (requires calling `StoreEvent`)

---

## Code Conventions

- Python: PEP 8, type hints
- Async: Use `async/await` consistently (stub_server.py is already async)
- Error handling: Log and continue, don't crash on non-critical failures
- Comments: Only where logic isn't self-evident

---

## Session State

**Read**: `memory.md` - for context on project state, decisions, what Claude is working on
**Write**: `gemini_memory.md` - your session notes (pre-populated with initial context)

Both files are gitignored. Update `gemini_memory.md` frequently with:
- What you've done
- Decisions made
- Any blockers or questions

**Important**: Do NOT write to `memory.md` - that's Claude's file.

---

## Testing

After your changes:

```bash
cd src/integration
python test_scenario_5_learning_loop.py
```

Scenario 7 should show explicit verification of prediction fields, not just "implicitly verified".

---

## Questions?

If you need clarification on:
- Proto field definitions → Read `src/memory/proto/memory.proto` (but don't modify)
- Executive proto → Read `src/executive/proto/executive.proto`
- How stub_server works → It's already well-structured, follow existing patterns

If you're blocked on something architectural, note it in `gemini_memory.md` and proceed with what you can do.

---

## Definition of Done

- [ ] `stub_server.py` returns `predicted_success` and `prediction_confidence` in `ProcessEventResponse`
- [ ] Scenario 7 explicitly verifies these fields (not just "implicitly verified")
- [ ] All existing tests still pass
- [ ] `gemini_memory.md` updated with session notes
