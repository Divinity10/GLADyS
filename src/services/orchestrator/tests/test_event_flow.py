"""Integration tests for event publish → store flow.

Tests the complete event processing pipeline:
1. Event enqueued to EventQueue
2. EventQueue calls process_callback (Executive)
3. EventQueue calls store_callback (Memory)
4. Event stored with response data

These tests use mocked callbacks but exercise real EventQueue logic,
catching issues where events might be silently dropped.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gladys_orchestrator.config import OrchestratorConfig
from gladys_orchestrator.event_queue import EventQueue


def make_config(**overrides):
    """Create config with short timeouts for testing."""
    defaults = {"event_timeout_ms": 5000, "timeout_scan_interval_ms": 100}
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def make_event(event_id="evt-test", source="test"):
    """Create a mock event proto."""
    ev = MagicMock()
    ev.id = event_id
    ev.source = source
    ev.raw_text = "Test event text"
    return ev


class TestEventFlowWithExecutive:
    """Test event flow when Executive is available."""

    @pytest.mark.asyncio
    async def test_event_processed_and_stored(self):
        """Event should be processed by Executive and stored in memory."""
        # Arrange
        response = {
            "response_id": "resp-123",
            "response_text": "Test response",
            "predicted_success": 0.85,
            "prediction_confidence": 0.9,
            "decision_path": "llm",
        }
        process = AsyncMock(return_value=response)
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event()

        # Act
        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)  # Allow processing
        await queue.stop()

        # Assert
        process.assert_called_once()
        store.assert_called_once()

        # Verify stored data
        call_args = store.call_args
        stored_event = call_args[0][0]
        stored_response = call_args[0][1]

        assert stored_event is event
        assert stored_response["response_text"] == "Test response"
        assert stored_response["decision_path"] == "llm"

    @pytest.mark.asyncio
    async def test_broadcast_includes_response_data(self):
        """Broadcast should include response data for SSE subscribers."""
        response = {
            "response_id": "resp-456",
            "response_text": "Broadcast test",
            "predicted_success": 0.7,
            "prediction_confidence": 0.8,
        }
        process = AsyncMock(return_value=response)
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event(event_id="evt-broadcast")

        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)
        await queue.stop()

        broadcast.assert_called_once()
        broadcast_data = broadcast.call_args[0][0]
        assert broadcast_data["event_id"] == "evt-broadcast"
        assert broadcast_data["response_text"] == "Broadcast test"


class TestEventFlowWithoutExecutive:
    """Test event flow when Executive is unavailable (returns None)."""

    @pytest.mark.asyncio
    async def test_event_stored_when_executive_unavailable(self):
        """Event should still be stored when Executive returns None.

        This is the fix for issue #94 - previously events were silently dropped.
        """
        # Arrange - Executive returns None (unavailable)
        process = AsyncMock(return_value=None)
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event(event_id="evt-no-exec")

        # Act
        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)
        await queue.stop()

        # Assert - event should still be stored
        store.assert_called_once()

        call_args = store.call_args
        stored_event = call_args[0][0]
        stored_response = call_args[0][1]

        assert stored_event is event
        assert stored_response["decision_path"] == "no_executive"
        assert stored_response["response_text"] == "(Executive unavailable)"

    @pytest.mark.asyncio
    async def test_no_broadcast_when_executive_unavailable(self):
        """No broadcast should happen when Executive is unavailable.

        Broadcast only happens when there's a real response to send.
        """
        process = AsyncMock(return_value=None)
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event()

        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)
        await queue.stop()

        # No broadcast when no response
        broadcast.assert_not_called()


class TestEventFlowStoreFailure:
    """Test event flow when store fails."""

    @pytest.mark.asyncio
    async def test_store_failure_logged_not_raised(self):
        """Store failure should be logged but not crash the queue."""
        response = {"response_text": "Test"}
        process = AsyncMock(return_value=response)
        store = AsyncMock(side_effect=Exception("DB connection failed"))
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event()

        # Should not raise
        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)
        await queue.stop()

        # Store was called (and failed)
        store.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_still_happens_on_store_failure(self):
        """Broadcast should happen even if store fails."""
        response = {"response_text": "Test", "response_id": "r1"}
        process = AsyncMock(return_value=response)
        store = AsyncMock(side_effect=Exception("DB down"))
        broadcast = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        event = make_event()

        await queue.start()
        queue.enqueue(event, salience=0.5)
        await asyncio.sleep(0.3)
        await queue.stop()

        # Broadcast should still happen before store
        broadcast.assert_called_once()


class TestEventFlowWithHeuristicSuggestion:
    """Test event flow with heuristic suggestion context."""

    @pytest.mark.asyncio
    async def test_suggestion_passed_to_executive(self):
        """Heuristic suggestion should be passed to Executive."""
        response = {"response_text": "Used suggestion"}
        process = AsyncMock(return_value=response)
        store = AsyncMock()
        config = make_config()

        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=AsyncMock(),
            store_callback=store,
        )

        event = make_event()

        await queue.start()
        queue.enqueue(
            event,
            salience=0.5,
            matched_heuristic_id="heur-123",
            suggested_action="Do this",
            heuristic_confidence=0.7,
            condition_text="When X happens",
        )
        await asyncio.sleep(0.3)
        await queue.stop()

        # Verify suggestion was passed
        process.assert_called_once()
        call_args = process.call_args
        suggestion = call_args[0][1]  # Second positional arg

        assert suggestion is not None
        assert suggestion["heuristic_id"] == "heur-123"
        assert suggestion["suggested_action"] == "Do this"
        assert suggestion["confidence"] == 0.7
