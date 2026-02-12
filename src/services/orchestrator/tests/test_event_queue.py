"""Tests for EventQueue, focusing on timeout storage behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gladys_orchestrator.config import OrchestratorConfig
from gladys_orchestrator.event_queue import EventQueue


def make_config(**overrides):
    """Create config with short timeouts for testing."""
    defaults = {"event_timeout_ms": 100, "timeout_scan_interval_ms": 50}
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def make_event(event_id="evt-1", source="test"):
    ev = MagicMock()
    ev.id = event_id
    ev.source = source
    return ev


async def slow_process(event, suggestion=None):
    """Process callback that blocks longer than timeout, forcing timeout path."""
    await asyncio.sleep(10)
    return {"response_text": "should not happen"}


class TestTimeoutStorage:
    """Timed-out events must be stored to DB via store_callback."""

    @pytest.mark.asyncio
    async def test_timeout_calls_store_callback(self):
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()
        queue = EventQueue(
            config,
            process_callback=slow_process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        # Enqueue two events — worker blocks on first, second times out
        await queue.start()
        queue.enqueue(make_event("evt-block"), salience=0.9)
        await asyncio.sleep(0.01)  # let worker grab first event
        event = make_event("evt-timeout")
        queue.enqueue(event, salience=0.5)

        # Wait for timeout scanner to fire on second event
        await asyncio.sleep(0.3)
        await queue.stop()

        store.assert_called_once()
        call_args = store.call_args
        assert call_args[0][0] is event
        response = call_args[0][1]
        assert response["routing_path"] == "TIMEOUT"
        assert response["response_text"] == "(Request timed out)"

    @pytest.mark.asyncio
    async def test_timeout_broadcasts_after_store(self):
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()
        queue = EventQueue(
            config,
            process_callback=slow_process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        await queue.start()
        queue.enqueue(make_event("evt-block"), salience=0.9)
        await asyncio.sleep(0.01)
        queue.enqueue(make_event("evt-timeout"), salience=0.5)

        await asyncio.sleep(0.3)
        await queue.stop()

        broadcast.assert_called_once()
        assert broadcast.call_args[0][0]["routing_path"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_timeout_store_failure_does_not_block_broadcast(self):
        store = AsyncMock(side_effect=Exception("DB down"))
        broadcast = AsyncMock()
        config = make_config()
        queue = EventQueue(
            config,
            process_callback=slow_process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        await queue.start()
        queue.enqueue(make_event("evt-block"), salience=0.9)
        await asyncio.sleep(0.01)
        queue.enqueue(make_event("evt-timeout"), salience=0.5)

        await asyncio.sleep(0.3)
        await queue.stop()

        # Store failed but broadcast should still happen
        store.assert_called_once()
        broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_process_calls_store(self):
        """Sanity check: successful processing also stores."""
        response = {"response_id": "r1", "response_text": "hello", "predicted_success": 1.0, "prediction_confidence": 0.9}
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
        await queue.start()
        queue.enqueue(event, salience=0.5)

        await asyncio.sleep(0.2)
        await queue.stop()

        store.assert_called_once()
        call_args = store.call_args
        assert call_args[0][0] is event
        assert call_args[0][1] is response


class TestEventQueuePersistence:
    """Test EventQueue persistence behavior (Issue #175).

    EventQueue is intentionally in-memory only for Phase.
    These tests verify and document this design decision.
    """

    @pytest.mark.asyncio
    async def test_no_db_write_during_queue(self):
        """Events are NOT written to DB when enqueued."""
        process = AsyncMock(return_value={"response_text": "done"})
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

        # Enqueue event
        queue.enqueue(event, salience=0.5)

        # Verify queue has event (stats)
        stats = queue.stats
        assert stats["total_queued"] == 1

        # Store should NOT be called yet (event only queued, not processed)
        store.assert_not_called()

        await queue.stop()

    @pytest.mark.asyncio
    async def test_db_write_after_processing(self):
        """Events ARE written to DB after Executive processes."""
        response = {"response_text": "done", "routing_path": "LLM"}
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
        await queue.start()
        queue.enqueue(event, salience=0.5)

        # Wait for processing to complete
        await asyncio.sleep(0.2)
        await queue.stop()

        # Store should be called with event + response
        store.assert_called_once()
        call_args = store.call_args
        assert call_args[0][0] is event
        assert call_args[0][1] is response

    @pytest.mark.asyncio
    async def test_no_auto_load_on_startup(self):
        """EventQueue does NOT load existing DB events on startup.

        This documents the intentional in-memory design for Phase.
        Comment in event_queue.py:50-51 states:
        "For Phase: Pure in-memory, events lost on restart is acceptable."
        """
        store = AsyncMock()
        broadcast = AsyncMock()
        process = AsyncMock(return_value={"response_text": "done"})
        config = make_config()

        # Create queue and start it
        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )
        await queue.start()

        # Verify queue is empty on startup (no DB load)
        stats = queue.stats
        assert stats["total_queued"] == 0
        assert stats["total_processed"] == 0
        assert stats["total_timed_out"] == 0

        # Verify store_callback was NOT called during startup
        # (no attempt to query or load from DB)
        store.assert_not_called()

        await queue.stop()

    @pytest.mark.asyncio
    async def test_restart_loses_queued_events(self):
        """Queued events are lost on restart (in-memory only).

        This is expected Phase behavior, not a bug.
        """
        process = AsyncMock(return_value={"response_text": "done"})
        store = AsyncMock()
        broadcast = AsyncMock()
        config = make_config()
        queue = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )

        # Start queue, enqueue event
        await queue.start()
        event = make_event("evt-will-be-lost")
        queue.enqueue(event, salience=0.5)

        # Verify event is queued
        stats1 = queue.stats
        assert stats1["total_queued"] == 1

        # Simulate restart: stop and create new queue
        await queue.stop()

        queue2 = EventQueue(
            config,
            process_callback=process,
            broadcast_callback=broadcast,
            store_callback=store,
        )
        await queue2.start()

        # New queue should be empty (event lost)
        stats2 = queue2.stats
        assert stats2["total_queued"] == 0
        assert stats2["total_processed"] == 0

        await queue2.stop()
