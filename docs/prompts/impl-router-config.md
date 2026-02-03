# Implementation: Router Config Extraction

**Read `CLAUDE.md` first, then `docs/design/ROUTER_CONFIG.md` (the spec), then this prompt.**

## Task

Move hardcoded magic numbers from `router.py` into `OrchestratorConfig` so they're configurable via environment variables.

## Branch

```bash
git checkout main && git pull
git checkout -b refactor/router-config
```

## What to Implement

Follow `docs/design/ROUTER_CONFIG.md` exactly. This is a small, mechanical change.

### 1. Add Config Fields

In `src/services/orchestrator/gladys_orchestrator/config.py`, add to `OrchestratorConfig`:

```python
# Emergency fast-path thresholds (default values, override via env)
# When both conditions are met, Orchestrator bypasses Executive entirely
emergency_confidence_threshold: float = 0.95
emergency_threat_threshold: float = 0.9

# Fallback novelty when Salience service is unavailable
# Must be >= salience_threshold to ensure events still route
fallback_novelty: float = 0.8
```

### 2. Update EventRouter

In `src/services/orchestrator/gladys_orchestrator/router.py`:

**Change 1** — Emergency fast-path (around line 162):

```python
# Before:
if confidence >= 0.95 and threat >= 0.9:

# After:
if (confidence >= self._config.emergency_confidence_threshold
        and threat >= self._config.emergency_threat_threshold):
```

Also update the log message to include the thresholds.

**Change 2** — Default salience fallback (around line 319):

```python
# Before:
"novelty": 0.8,

# After:
"novelty": self._config.fallback_novelty,
```

### 3. Ensure Config is Passed

The `EventRouter` constructor should already receive `config: OrchestratorConfig`. Verify this and use `self._config` for the new fields.

## Constraints

- Do NOT change any behavior — just move literals to config.
- Default values must match the current hardcoded values exactly.
- The router must continue to work if env vars aren't set (uses defaults).

## Testing

- Add unit tests verifying:
  - Emergency fast-path fires when both thresholds exceeded
  - Emergency fast-path does NOT fire when only one threshold exceeded
  - `_default_salience()` uses config value
- Tests go in existing `tests/unit/test_router.py` or new file if needed

## Files to Change

| File | Change |
|------|--------|
| `config.py` (orchestrator) | Add 3 fields |
| `router.py` | Replace 3 hardcoded values with `self._config.*` |
| `test_router.py` | Add/update tests |

## Definition of Done

- [ ] Config fields added with correct defaults
- [ ] Router uses config instead of literals
- [ ] Unit tests pass
- [ ] `make test` passes for orchestrator
- [ ] Manual test: events still route correctly

## Working Memory

Use `gemini_memory.md` (gitignored) as your working scratchpad. Do NOT write to `CLAUDE.md`, `claude_memory.md`, or any other project file as a memory store.
