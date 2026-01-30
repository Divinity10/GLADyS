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
