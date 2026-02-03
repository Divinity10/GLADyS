# Router Configuration Spec

**Status**: Proposed
**Date**: 2026-02-02
**Implements**: Extensibility Review item #5

## Purpose

Move hardcoded magic numbers from `router.py` into `OrchestratorConfig` so they're configurable via environment variables.

## Current State

`EventRouter` in `src/services/orchestrator/gladys_orchestrator/router.py` has two hardcoded values:

### Emergency Fast-Path Thresholds (line 162)

```python
if confidence >= 0.95 and threat >= 0.9:
    # Bypass Executive entirely
```

These thresholds determine when the Orchestrator short-circuits Executive and responds immediately. Currently hardcoded as literals.

### Default Salience Fallback (line 319)

```python
def _default_salience(self) -> dict:
    return {
        "novelty": 0.8,  # High enough to trigger immediate routing (threshold is 0.7)
        # ... other fields at 0.0
    }
```

When the Salience service is unavailable, this fallback ensures events still get routed. The 0.8 value is chosen to be above the routing threshold (0.7) but is hardcoded.

## Changes

### Add to OrchestratorConfig

In `src/services/orchestrator/gladys_orchestrator/config.py` (pydantic-settings reads from env vars / `.env` file):

```python
class OrchestratorConfig(BaseSettings):
    # ... existing fields ...

    # Emergency fast-path thresholds (default values, override via env)
    # When both conditions are met, Orchestrator bypasses Executive entirely
    emergency_confidence_threshold: float = 0.95
    emergency_threat_threshold: float = 0.9

    # Fallback novelty when Salience service is unavailable
    # Must be >= salience_threshold to ensure events still route
    fallback_novelty: float = 0.8
```

Corresponding environment variables (override defaults via `.env` or shell):
```
EMERGENCY_CONFIDENCE_THRESHOLD=0.95
EMERGENCY_THREAT_THRESHOLD=0.9
FALLBACK_NOVELTY=0.8
```

### Update EventRouter

```python
class EventRouter:
    def __init__(self, config: OrchestratorConfig, ...):
        self._config = config
        # ...

    async def route_event(self, event):
        # ...
        # Emergency fast-path: use config thresholds
        if (confidence >= self._config.emergency_confidence_threshold
                and threat >= self._config.emergency_threat_threshold):
            logger.info(
                "EMERGENCY_FASTPATH",
                event_id=event_id,
                heuristic_id=matched_heuristic_id,
                confidence=round(confidence, 3),
                threat=round(threat, 3),
                thresholds={
                    "confidence": self._config.emergency_confidence_threshold,
                    "threat": self._config.emergency_threat_threshold,
                },
            )
            # ...

    def _default_salience(self) -> dict:
        return {
            "threat": 0.0,
            "opportunity": 0.0,
            "humor": 0.0,
            "novelty": self._config.fallback_novelty,
            "goal_relevance": 0.0,
            "social": 0.0,
            "emotional": 0.0,
            "actionability": 0.0,
            "habituation": 0.0,
        }
```

## Environment Variables

```
EMERGENCY_CONFIDENCE_THRESHOLD=0.95
EMERGENCY_THREAT_THRESHOLD=0.9
FALLBACK_NOVELTY=0.8
```

## File Changes

| File | Change |
|------|--------|
| `config.py` (orchestrator) | Add 3 fields to `OrchestratorConfig` |
| `router.py` | Replace hardcoded `0.95`, `0.9`, `0.8` with `self._config.*` |

## Testing

- Unit test that emergency fast-path fires when both thresholds exceeded
- Unit test that emergency fast-path does NOT fire when only one threshold exceeded
- Unit test that `_default_salience()` uses config value

## Notes

This is a trivial change — no interface extraction, just moving literals to config. Effort: trivial.
