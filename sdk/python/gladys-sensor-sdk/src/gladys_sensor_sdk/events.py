"""Event building and dispatch.

EventBuilder provides a fluent API for constructing Event messages.
EventDispatcher handles configurable send strategies (immediate, scheduled, hybrid).
Intent constants define event intent categories.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .client import GladysClient
from .flow_control import FlowStrategy, NoOpStrategy

logger = logging.getLogger(__name__)


class Intent:
    """Intent constants for events."""

    ACTIONABLE = "actionable"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


@dataclass
class EmitResult:
    sent: int
    suppressed: int


class EventBuilder:
    """Fluent builder for Event messages.

    Example::

        event = (EventBuilder(source="sensor-123")
                .text("Player took damage: 50 HP")
                .structured({"damage": 50, "player_id": "xyz"})
                .intent(Intent.ACTIONABLE)
                .build())
    """

    def __init__(self, source: str) -> None:
        """Initialize builder with required source field.

        Args:
            source: Sensor ID (component_id).
        """
        self._data: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "intent": Intent.UNKNOWN,
        }
        self._salience: dict[str, Any] = {}

    def text(self, raw_text: str) -> EventBuilder:
        """Set natural language description.

        Args:
            raw_text: Human-readable event description.

        Returns:
            Self for chaining.
        """
        self._data["raw_text"] = raw_text
        return self

    def structured(self, data: dict[str, Any]) -> EventBuilder:
        """Set structured domain-specific data.

        Args:
            data: Dictionary of domain-specific fields.

        Returns:
            Self for chaining.
        """
        self._data["structured"] = data
        return self

    def intent(self, intent_value: str) -> EventBuilder:
        """Set event intent (actionable/informational/unknown).

        Args:
            intent_value: Intent constant (use Intent.ACTIONABLE, etc.).

        Returns:
            Self for chaining.
        """
        self._data["intent"] = intent_value
        return self

    def threat(self, is_threat: bool = True) -> EventBuilder:
        """Mark event as threat (bypasses habituation in hybrid mode).

        Args:
            is_threat: Whether event represents a threat.

        Returns:
            Self for chaining.
        """
        self._salience["threat"] = is_threat
        return self

    def evaluation_data(self, data: dict[str, Any]) -> EventBuilder:
        """Set evaluation data (solution/cheat data, stripped before executive).

        Args:
            data: Evaluation data dictionary.

        Returns:
            Self for chaining.
        """
        self._data["evaluation_data"] = data
        return self

    def build(self) -> dict[str, Any]:
        """Build and return the Event data.

        When proto stubs are available, this returns a proto Event message.
        Otherwise returns a dict representation.

        Returns:
            Constructed Event (dict or proto message).
        """
        event = dict(self._data)
        if self._salience:
            event["salience"] = dict(self._salience)
        return event

    @property
    def is_threat(self) -> bool:
        """Check if this event is marked as a threat."""
        return bool(self._salience.get("threat", False))


class EventDispatcher:
    """Configurable event dispatch with three modes.

    Modes:
        - Immediate (flush_interval_ms=0): Every emit() calls publish_event() now.
        - Scheduled (flush_interval_ms>0): Collect events, flush on timer.
        - Hybrid (scheduled + immediate_on_threat=True): Scheduled + threat bypass.

    Example::

        # Immediate (default)
        dispatcher = EventDispatcher(client, source="email-sensor-1")

        # Scheduled (600ms flush interval for game tick alignment)
        dispatcher = EventDispatcher(client, source="game-sensor-1",
                                     flush_interval_ms=600)

        # Hybrid (scheduled + threat bypass)
        dispatcher = EventDispatcher(client, source="game-sensor-1",
                                     flush_interval_ms=600,
                                     immediate_on_threat=True)
    """

    def __init__(
        self,
        client: GladysClient,
        source: str,
        flush_interval_ms: int = 0,
        immediate_on_threat: bool = True,
        strategy: FlowStrategy | None = None,
        priority_fn: Callable[[Any], float] | None = None,
    ) -> None:
        """Initialize event dispatcher.

        Args:
            client: GladysClient instance for publishing.
            source: Sensor source ID.
            flush_interval_ms: Flush interval in ms. 0 = immediate mode.
            immediate_on_threat: In scheduled mode, send threat events immediately.
            strategy: Flow control strategy, defaults to NoOpStrategy.
            priority_fn: Optional priority tiebreaker used only when batch
                candidates exceed the available token budget.
        """
        self.client = client
        self.source = source
        self.flush_interval_ms = flush_interval_ms
        self.immediate_on_threat = immediate_on_threat
        self._strategy: FlowStrategy = strategy or NoOpStrategy()
        self._priority_fn = priority_fn

        self._buffer: list[Any] = []
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._events_filtered: int = 0
        self._events_published: int = 0

    @property
    def is_immediate(self) -> bool:
        """True if dispatcher sends events immediately."""
        return self.flush_interval_ms <= 0

    @property
    def is_scheduled(self) -> bool:
        """True if dispatcher buffers and flushes on timer."""
        return self.flush_interval_ms > 0

    @property
    def buffered_count(self) -> int:
        """Number of events currently buffered."""
        return len(self._buffer)

    @property
    def events_filtered(self) -> int:
        """Number of events suppressed by flow control."""
        return self._events_filtered

    @property
    def events_published(self) -> int:
        """Number of events accepted for dispatch."""
        return self._events_published

    async def start(self) -> None:
        """Start the flush timer (only needed for scheduled/hybrid mode)."""
        if self.is_immediate or self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop the flush timer and flush remaining events."""
        self._running = False
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush remaining buffered events
        if self._buffer:
            await self.flush()

    async def emit(self, event: Any) -> bool:
        """Emit an event using the configured strategy.

        Args:
            event: Event to emit (dict or proto message).
        """
        is_threat = _is_threat(event)

        # Hybrid mode: threat events bypass the buffer
        if (
            self.is_scheduled
            and self.immediate_on_threat
            and is_threat
        ):
            await self.client.publish_event(event)
            self._events_published += 1
            return True

        # Threat events bypass flow control strategy checks.
        if not is_threat and not self._strategy.should_publish(event):
            self._events_filtered += 1
            return False

        # Immediate mode: send right away
        if self.is_immediate:
            await self.client.publish_event(event)
            self._events_published += 1
            return True

        # Scheduled mode: buffer for batch flush
        self._buffer.append(event)
        self._events_published += 1
        return True

    def set_strategy(self, strategy: FlowStrategy) -> None:
        """Replace the active flow control strategy."""
        self._strategy = strategy

    async def emit_batch(self, events: list[Any]) -> EmitResult:
        """Emit a batch with selective filtering when budget is exceeded."""
        if not events:
            return EmitResult(sent=0, suppressed=0)

        threats, candidates = self._partition_threats(events)

        if not candidates:
            to_send = self._reorder_original(events, threats, [])
            await self._send(to_send)
            self._events_published += len(to_send)
            return EmitResult(sent=len(to_send), suppressed=0)

        budget = self._strategy.available_tokens()

        if budget >= len(candidates):
            self._strategy.consume(len(candidates))
            kept = list(candidates)
            suppressed = 0
        elif budget <= 0:
            kept = []
            suppressed = len(candidates)
            self._events_filtered += suppressed
        else:
            kept = self._select_by_priority(candidates, budget)
            self._strategy.consume(len(kept))
            suppressed = len(candidates) - len(kept)
            self._events_filtered += suppressed

        to_send = self._reorder_original(events, threats, kept)
        await self._send(to_send)
        self._events_published += len(to_send)
        return EmitResult(sent=len(to_send), suppressed=suppressed)

    def _partition_threats(
        self,
        events: list[Any],
    ) -> tuple[list[tuple[int, Any]], list[tuple[int, Any]]]:
        threats: list[tuple[int, Any]] = []
        candidates: list[tuple[int, Any]] = []

        for index, event in enumerate(events):
            if _is_threat(event):
                threats.append((index, event))
            else:
                candidates.append((index, event))

        return threats, candidates

    def _select_by_priority(
        self,
        candidates: list[tuple[int, Any]],
        budget: int,
    ) -> list[tuple[int, Any]]:
        if self._priority_fn is None:
            return list(candidates[:budget])

        scored = [
            (index, event, self._priority_fn(event))
            for index, event in candidates
        ]
        scored.sort(key=lambda x: (-x[2], x[0]))
        selected = scored[:budget]
        selected.sort(key=lambda x: x[0])
        return [(index, event) for index, event, _ in selected]

    def _reorder_original(
        self,
        original: list[Any],
        threats: list[tuple[int, Any]],
        kept: list[tuple[int, Any]],
    ) -> list[Any]:
        selected_indices = {
            index for index, _ in threats
        } | {index for index, _ in kept}
        return [
            event
            for index, event in enumerate(original)
            if index in selected_indices
        ]

    async def _send(self, events: list[Any]) -> None:
        if not events:
            return

        if self.is_immediate:
            if len(events) == 1:
                await self.client.publish_event(events[0])
            else:
                await self.client.publish_events(events)
            return

        if self.immediate_on_threat:
            buffered: list[Any] = []
            for event in events:
                if _is_threat(event):
                    await self.client.publish_event(event)
                else:
                    buffered.append(event)
            self._buffer.extend(buffered)
            return

        self._buffer.extend(events)

    async def flush(self) -> None:
        """Force-flush all buffered events."""
        if not self._buffer:
            return

        events = list(self._buffer)
        self._buffer.clear()

        if len(events) == 1:
            await self.client.publish_event(events[0])
        else:
            await self.client.publish_events(events)

    async def _flush_loop(self) -> None:
        """Background flush loop for scheduled mode."""
        interval = self.flush_interval_ms / 1000.0
        while self._running:
            await asyncio.sleep(interval)
            try:
                await self.flush()
            except Exception:
                logger.error("Flush failed", exc_info=True)


def _is_threat(event: Any) -> bool:
    """Check if an event is marked as a threat.

    Supports both dict and proto Event formats.
    """
    if isinstance(event, dict):
        salience = event.get("salience", {})
        if isinstance(salience, dict):
            return bool(salience.get("threat", False))
        # Proto-like object
        return bool(getattr(salience, "threat", False))

    # Proto Event object
    salience = getattr(event, "salience", None)
    if salience is not None:
        return bool(getattr(salience, "threat", False))

    return False
