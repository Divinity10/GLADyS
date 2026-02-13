# Learning Module

**Location**: `src/services/orchestrator/gladys_orchestrator/learning.py`
**Integrated in**: `router.py` (via `LearningModule`), `server.py` (creation + cleanup loop)

Facade that consolidates all learning-related operations behind a clean interface. The router only interacts with `LearningModule` for learning operations -- not directly with `outcome_watcher` or `memory_client` for learning purposes.

## Implicit Feedback Signals

| Signal | Meaning | Implementation |
|--------|---------|----------------|
| **Timeout** | No complaint within timeout -> positive | `cleanup_expired()` sends positive feedback for expired outcome expectations |
| **Undo within 60s** | User undid the action -> negative | `_check_undo_signal()` detects undo keywords in events within 60s of a fire |
| **Ignored 3x** | Heuristic fired 3 times without engagement -> negative | `on_heuristic_ignored()` tracks consecutive ignores per heuristic |
| **Outcome pattern** | Expected event observed -> positive/negative | Delegates to `OutcomeWatcher.check_event()` |

## Interface

| Method | Purpose |
|--------|---------|
| `on_feedback()` | Handle explicit feedback (user thumbs up/down) |
| `on_fire()` | Register heuristic fire (flight recorder + outcome watcher) |
| `on_outcome()` | Handle implicit feedback signal |
| `check_event_for_outcomes()` | Check incoming event for outcome matches + undo signals |
| `on_heuristic_ignored()` | Track ignored suggestions (3x = negative) |
| `cleanup_expired()` | Timeout handling + positive feedback + stale fire cleanup |

## Integration Points

| Location | What Happens |
|----------|--------------|
| `router.py` | Every incoming event checked via `learning_module.check_event_for_outcomes()` |
| `router.py` | Heuristic fires registered via `learning_module.on_fire()` |
| `server.py` | LearningModule created with memory_client + outcome_watcher |
| `server.py` | Cleanup loop calls `learning_module.cleanup_expired()` every 30s |

## OutcomeWatcher (Internal)

**Location**: `src/services/orchestrator/gladys_orchestrator/outcome_watcher.py`

Internal dependency of LearningModule. Watches for pattern-based outcome events after heuristic fires.

## Configuration

| Config Key | Default | Purpose |
|------------|---------|---------|
| `outcome_watcher_enabled` | `True` | Enable/disable outcome watching |
| `outcome_cleanup_interval_sec` | `30` | How often to clean expired expectations |
| `outcome_patterns_json` | `'[]'` | JSON array of trigger->outcome patterns |

## Known Issues (to be fixed)

- **Race condition**: `_pending` list modified without lock in `register_fire()` and `cleanup_expired()`
- **None check**: `result.get('success')` could fail if client returns None
