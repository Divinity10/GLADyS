"""Tests for the EventRouter."""

import pytest
import asyncio
from dataclasses import dataclass
from typing import Any
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
            threat: float = 0.9
            salience: float = 0.9
            habituation: float = 0.0
            vector: dict[str, float] = None

            def __post_init__(self):
                if self.vector is None:
                    self.vector = {
                        "novelty": 0.0,
                        "goal_relevance": 0.0,
                        "opportunity": 0.0,
                        "actionability": 0.0,
                        "social": 0.0,
                    }

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
        """Routing salience uses the scalar score directly."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        salience = {
            "salience": 0.8,
            "threat": 0.5,
            "habituation": 0.9,
            "vector": {"novelty": 0.1},
        }

        max_val = router._get_max_salience(salience)
        assert max_val == 0.8

    def test_get_max_salience_falls_back_to_threat(self):
        """When scalar salience is zero, threat is used as fallback priority."""
        config = OrchestratorConfig()
        router = EventRouter(config)

        salience = {
            "salience": 0.0,
            "threat": 0.65,
            "habituation": 0.4,
            "vector": {"novelty": 0.9},
        }

        max_val = router._get_max_salience(salience)
        assert max_val == 0.65

    @pytest.mark.asyncio
    async def test_emergency_both_thresholds(self):
        """Emergency fast-path fires when both thresholds exceeded."""
        config = OrchestratorConfig(
            emergency_confidence_threshold=0.9,
            emergency_threat_threshold=0.8
        )
        # Mock memory client to return high confidence heuristic
        memory_client = AsyncMock()
        memory_client.get_heuristic.return_value = {
            "id": "h1",
            "confidence": 0.95,
            "effects_json": '{"message": "Run!"}',
            "condition_text": "Monster appeared"
        }
        
        # Mock salience client to return high threat
        salience_client = AsyncMock()
        salience_client.evaluate_salience.return_value = {
            "threat": 0.85,
            "_matched_heuristic": "h1"
        }

        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)
        
        # Use a simple class for event that doesn't trigger _has_explicit_salience
        class SimpleEvent:
            def __init__(self):
                self.id = "e1"
                self.source = "test"
                self.salience = None # No salience attribute or set to None

        event = SimpleEvent()
        result = await router.route_event(event)

        assert result["response_text"] == "Run!"
        assert result["queued"] is False

    @pytest.mark.asyncio
    async def test_emergency_one_threshold_not_enough(self):
        """Emergency fast-path does NOT fire when only one threshold exceeded."""
        config = OrchestratorConfig(
            emergency_confidence_threshold=0.95,
            emergency_threat_threshold=0.9
        )
        # High confidence, but low threat
        memory_client = AsyncMock()
        memory_client.get_heuristic.return_value = {
            "id": "h1",
            "confidence": 0.99,
            "effects_json": '{"message": "Action"}',
            "condition_text": "Condition"
        }
        
        salience_client = AsyncMock()
        salience_client.evaluate_salience.return_value = {
            "threat": 0.5,
            "_matched_heuristic": "h1"
        }

        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)
        
        class SimpleEvent:
            def __init__(self):
                self.id = "e1"
                self.source = "test"
                self.salience = None

        event = SimpleEvent()
        result = await router.route_event(event)

        # Should be queued for Executive, not immediate response
        assert result["accepted"] is True
        assert result.get("response_text", "") == ""
        assert result["queued"] is True

    def test_default_salience_returns_neutral_result(self):
        """_default_salience() returns SalienceResult-shaped neutral values."""
        config = OrchestratorConfig(fallback_novelty=0.99)
        router = EventRouter(config)

        salience = router._default_salience()
        assert salience["threat"] == pytest.approx(0.5)
        assert salience["salience"] == pytest.approx(0.5)
        assert salience["habituation"] == pytest.approx(0.5)
        assert salience["vector"]["novelty"] == pytest.approx(0.5)
        assert salience["vector"]["goal_relevance"] == pytest.approx(0.5)
        assert salience["vector"]["opportunity"] == pytest.approx(0.5)
        assert salience["vector"]["actionability"] == pytest.approx(0.5)
        assert salience["vector"]["social"] == pytest.approx(0.5)

    def test_config_defaults(self):
        """Verify new config fields have correct defaults."""
        config = OrchestratorConfig()
        assert config.emergency_confidence_threshold == 0.95
        assert config.emergency_threat_threshold == 0.9
        assert config.fallback_novelty == 0.8
