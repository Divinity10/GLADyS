"""Unit tests for MemoryStorage.list_events() and get_event().

Tests query construction and row conversion using a mocked asyncpg pool.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gladys_memory.storage import MemoryStorage


@pytest.fixture
def storage():
    """MemoryStorage with a mocked connection pool."""
    s = MemoryStorage()
    s._pool = AsyncMock()
    return s


def _make_row(**overrides):
    """Build a dict mimicking an asyncpg Record for episodic_events."""
    defaults = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc),
        "source": "test-sensor",
        "raw_text": "something happened",
        "salience": {"novelty": 0.5, "threat": 0.0},
        "response_text": "response here",
        "response_id": "resp-001",
        "predicted_success": 0.75,
        "prediction_confidence": 0.8,
        "matched_heuristic_id": None,
    }
    defaults.update(overrides)
    return defaults


class TestListEvents:
    async def test_basic_query(self, storage):
        row = _make_row()
        storage._pool.fetch.return_value = [row]

        result = await storage.list_events(limit=10, offset=0)

        assert len(result) == 1
        assert result[0]["source"] == "test-sensor"
        # Verify query was called
        storage._pool.fetch.assert_called_once()

    async def test_default_excludes_archived(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events()

        query = storage._pool.fetch.call_args[0][0]
        assert "e.archived = false" in query

    async def test_include_archived(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events(include_archived=True)

        query = storage._pool.fetch.call_args[0][0]
        assert "archived" not in query

    async def test_source_filter(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events(source="minecraft")

        query = storage._pool.fetch.call_args[0][0]
        assert "e.source = $" in query
        # Source should be in params
        args = storage._pool.fetch.call_args[0]
        assert "minecraft" in args

    async def test_pagination_params(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events(limit=25, offset=50)

        args = storage._pool.fetch.call_args[0]
        assert 25 in args
        assert 50 in args

    async def test_order_by_timestamp_desc(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events()

        query = storage._pool.fetch.call_args[0][0]
        assert "ORDER BY e.timestamp DESC" in query

    async def test_left_join_heuristic_fires(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_events()

        query = storage._pool.fetch.call_args[0][0]
        assert "LEFT JOIN heuristic_fires" in query
        assert "matched_heuristic_id" in query

    async def test_null_fields_in_row(self, storage):
        """Rows with NULL values should convert cleanly."""
        row = _make_row(
            response_text=None,
            response_id=None,
            predicted_success=None,
            prediction_confidence=None,
            matched_heuristic_id=None,
        )
        storage._pool.fetch.return_value = [row]

        result = await storage.list_events()
        assert result[0]["response_text"] is None
        assert result[0]["matched_heuristic_id"] is None

    async def test_not_connected_raises(self):
        s = MemoryStorage()
        s._pool = None
        with pytest.raises(RuntimeError, match="Not connected"):
            await s.list_events()


class TestGetEvent:
    async def test_found(self, storage):
        event_id = str(uuid.uuid4())
        row = _make_row(id=uuid.UUID(event_id))
        storage._pool.fetchrow.return_value = row

        result = await storage.get_event(event_id)

        assert result is not None
        assert str(result["id"]) == event_id

    async def test_not_found(self, storage):
        storage._pool.fetchrow.return_value = None

        result = await storage.get_event(str(uuid.uuid4()))
        assert result is None

    async def test_uuid_conversion(self, storage):
        """Event ID string should be converted to UUID for the query."""
        event_id = str(uuid.uuid4())
        storage._pool.fetchrow.return_value = None

        await storage.get_event(event_id)

        args = storage._pool.fetchrow.call_args[0]
        # Second positional arg should be a UUID
        assert isinstance(args[1], uuid.UUID)
        assert str(args[1]) == event_id

    async def test_not_connected_raises(self):
        s = MemoryStorage()
        s._pool = None
        with pytest.raises(RuntimeError, match="Not connected"):
            await s.get_event("some-id")
