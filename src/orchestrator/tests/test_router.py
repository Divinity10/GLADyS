"""Tests for the EventRouter."""

import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from gladys_orchestrator.router import EventRouter
from gladys_orchestrator.config import OrchestratorConfig


@dataclass
class MockEvent:
    """Mock event for testing."""
    id: str
    source: str = "test-sensor"
    raw_text: str = ""


class TestEventRouter:
    """Test cases for EventRouter."""

    def test_router_initialization(self):
        """Router initializes with config."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        assert router.config == config
        assert router._subscribers == {}

    @pytest.mark.asyncio
    async def test_route_event_returns_queued(self):
        """Events without high-conf heuristic are marked for queuing."""
        config = OrchestratorConfig(high_salience_threshold=0.7)
        router = EventRouter(config)

        event = MockEvent(id="test-1")

        # No heuristic match, no salience service → queued
        result = await router.route_event(event)

        assert result["accepted"] is True
        assert result.get("queued") is True
        assert "_salience" in result  # Salience included for queue priority

    @pytest.mark.asyncio
    async def test_route_high_salience_queued_with_priority(self):
        """High salience events are queued with higher priority (salience value)."""
        config = OrchestratorConfig(high_salience_threshold=0.7)
        router = EventRouter(config)

        # Create event with high salience attached
        @dataclass
        class HighSalienceEvent:
            id: str
            source: str = "test-sensor"
            salience: object = None

        @dataclass
        class MockSalience:
            threat: float = 0.9  # HIGH salience
            opportunity: float = 0.0
            humor: float = 0.0
            novelty: float = 0.0
            goal_relevance: float = 0.0
            social: float = 0.0
            emotional: float = 0.0
            actionability: float = 0.0
            habituation: float = 0.0

        event = HighSalienceEvent(id="urgent-1", salience=MockSalience())

        result = await router.route_event(event)

        assert result["accepted"] is True
        # Now ALL events without heuristic are queued (high salience = higher priority)
        assert result.get("queued") is True
        assert result.get("_salience", 0) >= 0.7  # High salience captured

    def test_add_subscriber(self):
        """Subscribers can be added."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        queue = router.add_subscriber("sub-1", source_filters=["sensor-a"])

        assert "sub-1" in router._subscribers
        assert queue is not None

    def test_remove_subscriber(self):
        """Subscribers can be removed."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        router.add_subscriber("sub-1")
        router.remove_subscriber("sub-1")

        assert "sub-1" not in router._subscribers

    @pytest.mark.asyncio
    async def test_broadcast_to_subscribers(self):
        """Events are broadcast to matching subscribers."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        queue1 = router.add_subscriber("sub-1")
        queue2 = router.add_subscriber("sub-2", source_filters=["other-sensor"])

        event = MockEvent(id="test-1", source="test-sensor")

        await router._broadcast_to_subscribers(event)

        # sub-1 has no filter, should receive
        assert queue1.qsize() == 1
        # sub-2 filters for "other-sensor", should not receive
        assert queue2.qsize() == 0

    def test_get_max_salience(self):
        """Max salience correctly excludes habituation."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        salience = {
            "threat": 0.5,
            "opportunity": 0.3,
            "humor": 0.2,
            "novelty": 0.1,
            "goal_relevance": 0.0,
            "social": 0.0,
            "emotional": -0.8,  # negative, should use abs
            "actionability": 0.0,
            "habituation": 0.9,  # should be excluded
        }

        max_val = router._get_max_salience(salience)

        # Should be abs(-0.8) = 0.8, not 0.9 (habituation excluded)
        assert max_val == 0.8
