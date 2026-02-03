# Implementation: Decision Strategy Protocol

**Read `CLAUDE.md` first, then `docs/design/DECISION_STRATEGY.md` (the spec), then this prompt.**

**Depends on**: `refactor/llm-provider` branch must be merged first (or cherry-pick the Protocol definitions).

## Task

Extract a `DecisionStrategy` Protocol from the Executive's `ProcessEvent` logic. This creates an abstraction layer so PoC 2 can A/B test different decision strategies.

## Branch

```bash
git checkout main && git pull
git checkout -b refactor/decision-strategy
```

If `refactor/llm-provider` isn't merged yet, cherry-pick or rebase onto it.

## What to Implement

Follow `docs/design/DECISION_STRATEGY.md` exactly. Summary:

1. **Add Protocol and dataclasses**:
   - `DecisionPath` enum (HEURISTIC, LLM, FALLBACK, REJECTED)
   - `DecisionContext` dataclass (input)
   - `DecisionResult` dataclass (output)
   - `DecisionStrategy` Protocol

2. **Create `HeuristicFirstStrategy`** class:
   - Implements the Protocol
   - Owns `_trace_store` (moved from `ExecutiveServicer`)
   - Contains `_build_prompt()`, `_get_prediction()`, `_store_trace()` logic
   - Configurable via `HeuristicFirstConfig` dataclass

3. **Refactor `ExecutiveServicer`**:
   - Constructor takes `decision_strategy: DecisionStrategy`
   - `ProcessEvent` becomes a thin wrapper that:
     - Builds `DecisionContext` from request
     - Calls `self._strategy.decide(context, self._llm)`
     - Maps `DecisionResult` to proto response
   - Remove inline decision logic

4. **Add factory and config**:
   ```python
   def create_decision_strategy(strategy_type: str, **kwargs) -> DecisionStrategy
   ```
   - Reads `EXECUTIVE_DECISION_STRATEGY` env var (default: "heuristic_first")
   - Reads `EXECUTIVE_HEURISTIC_THRESHOLD` env var (default: 0.7)

5. **Update `serve()`** to use the factory.

## Constraints

- `ProvideFeedback` stays as-is for now. It can access traces via `self._strategy.get_trace()`.
- Keep the same external behavior — gRPC responses must be identical.
- The strategy owns `ReasoningTrace` storage. Move the dataclass and storage dict into the strategy.

## Testing

- Add unit tests for `HeuristicFirstStrategy`:
  - Test heuristic path (confidence >= threshold)
  - Test LLM path (confidence < threshold, LLM available)
  - Test rejected path (no LLM, not immediate)
  - Test fallback path (LLM returns None)
- Mock `LLMProvider` for deterministic tests
- Tests go in `src/services/executive/tests/test_decision_strategy.py`

## Files to Change

| File | Change |
|------|--------|
| `src/services/executive/gladys_executive/server.py` | Add Protocol, dataclasses, strategy class, refactor servicer |
| `src/services/executive/tests/test_decision_strategy.py` | New file — unit tests |

## Definition of Done

- [ ] `DecisionStrategy` Protocol exists
- [ ] `HeuristicFirstStrategy` implements it correctly
- [ ] `ExecutiveServicer.ProcessEvent` delegates to strategy
- [ ] `ProvideFeedback` can access traces via `get_trace()`
- [ ] Factory and config work
- [ ] Unit tests pass
- [ ] `make test` passes for executive service
- [ ] Manual test: run Executive, send event, verify response unchanged

## Working Memory

Use `claude_memory.md` (gitignored) as your working scratchpad.
