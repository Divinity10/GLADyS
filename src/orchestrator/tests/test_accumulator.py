"""Tests for the MomentAccumulator."""

import pytest
from dataclasses import dataclass

from gladys_orchestrator.accumulator import MomentAccumulator
from gladys_orchestrator.config import OrchestratorConfig


@dataclass
class MockEvent:
    """Mock event for testing."""
    id: str
    source: str = "test-sensor"


class TestMomentAccumulator:
    """Test cases for MomentAccumulator."""

    def test_add_event(self):
        """Events can be added to accumulator."""
        config = OrchestratorConfig()
        acc = MomentAccumulator(config)

        event = MockEvent(id="test-1")
        acc.add_event(event)

        assert acc.current_event_count == 1
        assert acc.total_events_accumulated == 1

    def test_flush_returns_moment(self):
        """Flush returns accumulated events."""
        config = OrchestratorConfig()
        acc = MomentAccumulator(config)

        event1 = MockEvent(id="test-1")
        event2 = MockEvent(id="test-2")
        acc.add_event(event1)
        acc.add_event(event2)

        moment = acc.flush()

        assert moment is not None
        assert len(moment.events) == 2
        assert moment.events[0].id == "test-1"
        assert moment.events[1].id == "test-2"

    def test_flush_empty_returns_none(self):
        """Flush returns None when no events accumulated."""
        config = OrchestratorConfig()
        acc = MomentAccumulator(config)

        moment = acc.flush()

        assert moment is None

    def test_flush_clears_accumulator(self):
        """Flush clears the current moment."""
        config = OrchestratorConfig()
        acc = MomentAccumulator(config)

        acc.add_event(MockEvent(id="test-1"))
        acc.flush()

        assert acc.current_event_count == 0

    def test_flush_preserves_total_count(self):
        """Flush preserves total event count."""
        config = OrchestratorConfig()
        acc = MomentAccumulator(config)

        acc.add_event(MockEvent(id="test-1"))
        acc.add_event(MockEvent(id="test-2"))
        acc.flush()
        acc.add_event(MockEvent(id="test-3"))

        assert acc.total_events_accumulated == 3
        assert acc.current_event_count == 1
