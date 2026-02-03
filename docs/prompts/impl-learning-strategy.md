# Implementation: Learning Strategy Protocol

**Read `CLAUDE.md` first, then `docs/design/LEARNING_STRATEGY.md` (the spec), then this prompt.**

## Task

Extract a `LearningStrategy` Protocol from the `LearningModule`'s signal interpretation logic. This creates an abstraction layer so PoC 2 can test alternative learning models (e.g., reinforcement learning).

## Branch

```bash
git checkout main && git pull
git checkout -b refactor/learning-strategy
```

## What to Implement

Follow `docs/design/LEARNING_STRATEGY.md` exactly. Summary:

1. **Add Protocol and dataclasses** to `src/services/orchestrator/gladys_orchestrator/learning.py`:
   - `SignalType` enum (POSITIVE, NEGATIVE, NEUTRAL)
   - `FeedbackSignal` dataclass
   - `LearningStrategy` Protocol

2. **Create `BayesianStrategy`** class:
   - Implements the Protocol
   - Configurable via `BayesianStrategyConfig` dataclass
   - Move signal interpretation logic from `LearningModule`:
     - `interpret_explicit_feedback()` — straightforward mapping
     - `interpret_timeout()` — timeout = POSITIVE
     - `interpret_event_for_undo()` — keyword matching, returns list
     - `interpret_ignore()` — threshold check

3. **Refactor `LearningModule`**:
   - Constructor takes `strategy: LearningStrategy` (default: `BayesianStrategy()`)
   - Add `_apply_signal(signal)` helper that calls Memory
   - Delegate `_check_undo_signal` → `self._strategy.interpret_event_for_undo`
   - Delegate `on_heuristic_ignored` → `self._strategy.interpret_ignore`
   - Delegate timeout in `cleanup_expired` → `self._strategy.interpret_timeout`
   - Remove module-level constants `UNDO_WINDOW_SEC`, `IGNORED_THRESHOLD`

4. **Add config to `OrchestratorConfig`**:
   ```python
   learning_strategy: str = "bayesian"
   learning_undo_window_sec: float = 60.0
   learning_ignored_threshold: int = 3
   learning_undo_keywords: str = "undo,revert,cancel,rollback,nevermind,never mind"
   ```

5. **Add factory function**:
   ```python
   def create_learning_strategy(config: OrchestratorConfig) -> LearningStrategy
   ```

6. **Update `server.py`** (orchestrator) to pass strategy to `LearningModule`.

## Cleanup (Part of This PR)

The spec also requires removing unused parameters from Memory's `update_heuristic_confidence`:

1. **`memory.proto`**: Remove `learning_rate` and `predicted_success` from `UpdateHeuristicConfidenceRequest`
2. **`storage.py`**: Remove unused params from `update_heuristic_confidence()`
3. **`grpc_server.py`**: Update RPC handler
4. **Regenerate proto stubs** after proto change

## Constraints

- Keep the same external behavior — confidence updates must work identically.
- `OutcomeWatcher` is unchanged — it's orthogonal to the strategy.
- The strategy interprets signals; Memory still does the Bayesian math.

## Testing

- Add unit tests for `BayesianStrategy`:
  - Test `interpret_explicit_feedback()` — positive/negative mapping
  - Test `interpret_timeout()` — always returns POSITIVE
  - Test `interpret_event_for_undo()` — keyword matching, empty list if no keywords
  - Test `interpret_ignore()` — threshold boundary (2 = NEUTRAL, 3 = NEGATIVE)
- Tests go in `src/services/orchestrator/tests/test_learning_strategy.py`

## Files to Change

| File | Change |
|------|--------|
| `learning.py` | Add Protocol, dataclasses, `BayesianStrategy`, refactor `LearningModule` |
| `config.py` (orchestrator) | Add strategy config fields |
| `server.py` (orchestrator) | Pass strategy to `LearningModule` |
| `memory.proto` | Remove unused fields |
| `storage.py` | Remove unused params |
| `grpc_server.py` | Update RPC handler |
| `test_learning_strategy.py` | New file — unit tests |

## Definition of Done

- [ ] `LearningStrategy` Protocol exists
- [ ] `BayesianStrategy` implements it correctly
- [ ] `LearningModule` delegates to strategy
- [ ] Config fields added and factory works
- [ ] Unused Memory params removed (proto + code)
- [ ] Proto stubs regenerated
- [ ] Unit tests pass
- [ ] `make test` passes for orchestrator and memory services
- [ ] Manual test: feedback flow still updates confidence

## Working Memory

Use `claude_memory.md` (gitignored) as your working scratchpad.
