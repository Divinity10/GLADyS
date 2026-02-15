"""Flow control strategies for event emission.

The orchestrator sends strategy config at registration time.
Each SDK implements strategies locally.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class FlowStrategy(Protocol):
    """Strategy interface — called before every event publish."""

    def should_publish(self, event: Any) -> bool:
        """Return True to publish the event, False to suppress it."""
        ...


class NoOpStrategy:
    """Passthrough strategy that always allows publishing."""

    def should_publish(self, event: Any) -> bool:
        return True


class RateLimitStrategy:
    """Token bucket rate limiter for event publishing."""

    def __init__(self, max_events: int, window_seconds: int) -> None:
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or max_events <= 0
        ):
            raise ValueError("max_events must be a positive integer")
        if (
            not isinstance(window_seconds, int)
            or isinstance(window_seconds, bool)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be a positive integer")

        self._max_events = float(max_events)
        self._refill_rate = self._max_events / float(window_seconds)
        self._tokens = self._max_events
        self._last_refill = time.monotonic()

    def should_publish(self, event: Any) -> bool:
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now

        self._tokens = min(
            self._max_events,
            self._tokens + (elapsed * self._refill_rate),
        )

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True

        return False


def create_strategy(config: dict[str, Any]) -> FlowStrategy:
    """Create a flow control strategy from config."""
    strategy_name = str(config.get("strategy", "none")).lower()

    if strategy_name == "none":
        return NoOpStrategy()

    if strategy_name == "rate_limit":
        return RateLimitStrategy(
            max_events=config["max_events"],
            window_seconds=config["window_seconds"],
        )

    logger.warning(
        "Unknown flow control strategy '%s', falling back to NoOpStrategy",
        strategy_name,
    )
    return NoOpStrategy()
