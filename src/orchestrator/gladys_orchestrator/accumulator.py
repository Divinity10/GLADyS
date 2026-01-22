"""Moment accumulation for the Orchestrator.

Accumulates low-salience events into "moments" that are sent
to Executive on a configurable tick (default 100ms).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .config import OrchestratorConfig

logger = logging.getLogger(__name__)


@dataclass
class Moment:
    """A collection of events accumulated within a time window."""

    events: list[Any] = field(default_factory=list)
    start_time_ms: int = 0
    end_time_ms: int = 0

    def add(self, event: Any) -> None:
        """Add an event to this moment."""
        self.events.append(event)
        now = int(time.time() * 1000)
        if self.start_time_ms == 0:
            self.start_time_ms = now
        self.end_time_ms = now


class MomentAccumulator:
    """
    Accumulates low-salience events into moments.

    Events are grouped by time window (configurable, default 100ms).
    When flush() is called, the current moment is returned and a new one starts.

    Architecture note (2026-01-21):
    - 1Hz (1000ms) moments are too slow for responsive UX
    - Target: 50-100ms for real-time scenarios
    - High-salience events bypass this entirely (go immediate to Executive)
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self._current_moment = Moment()
        self._event_count = 0

    def add_event(self, event: Any) -> None:
        """Add an event to the current moment."""
        self._current_moment.add(event)
        self._event_count += 1
        logger.debug(
            f"Accumulated event {getattr(event, 'id', 'unknown')} "
            f"(moment has {len(self._current_moment.events)} events)"
        )

    def flush(self) -> Moment | None:
        """
        Flush the current moment and start a new one.

        Returns the flushed moment, or None if empty.
        """
        moment = self._current_moment

        # Start new moment
        self._current_moment = Moment()

        if not moment.events:
            return None

        logger.debug(f"Flushing moment with {len(moment.events)} events")
        return moment

    @property
    def current_event_count(self) -> int:
        """Number of events in current moment."""
        return len(self._current_moment.events)

    @property
    def total_events_accumulated(self) -> int:
        """Total events accumulated since start."""
        return self._event_count
