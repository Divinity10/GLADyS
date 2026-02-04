"""Unit tests for MemoryStorage event queries.

Tests query construction and row conversion using a mocked asyncpg pool.
Covers list_events, get_event, list_responses, and get_response_detail.
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
        assert "ORDER BY sub.timestamp DESC" in query

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


def _make_response_row(**overrides):
    """Build a dict mimicking a list_responses query row."""
    defaults = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
        "source": "sudoku",
        "raw_text": "player made a move",
        "decision_path": "heuristic",
        "response_text": "Try row 3",
        "matched_heuristic_id": str(uuid.uuid4()),
        "matched_heuristic_condition": "player stuck on puzzle",
    }
    defaults.update(overrides)
    return defaults


def _make_detail_row(**overrides):
    """Build a dict mimicking a get_response_detail query row."""
    row = _make_response_row(**overrides)
    row.setdefault("llm_prompt_text", None)
    row.setdefault("matched_heuristic_confidence", 0.85)
    row.setdefault("fire_id", uuid.uuid4())
    row.setdefault("feedback_source", "explicit")
    row.setdefault("outcome", "success")
    return row


class TestListResponses:
    async def test_basic_query(self, storage):
        row = _make_response_row()
        storage._pool.fetch.return_value = [row]

        result = await storage.list_responses()

        assert len(result) == 1
        assert result[0]["decision_path"] == "heuristic"
        storage._pool.fetch.assert_called_once()

    async def test_decision_path_filter(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses(decision_path="llm")

        query = storage._pool.fetch.call_args[0][0]
        assert "e.decision_path = $" in query
        args = storage._pool.fetch.call_args[0]
        assert "llm" in args

    async def test_source_filter(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses(source="melvor")

        query = storage._pool.fetch.call_args[0][0]
        assert "e.source = $" in query
        args = storage._pool.fetch.call_args[0]
        assert "melvor" in args

    async def test_search_filter(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses(search="stuck")

        query = storage._pool.fetch.call_args[0][0]
        assert "ILIKE" in query
        args = storage._pool.fetch.call_args[0]
        assert "%stuck%" in args

    async def test_combined_filters(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses(decision_path="heuristic", source="sudoku", search="move")

        query = storage._pool.fetch.call_args[0][0]
        assert "e.decision_path = $" in query
        assert "e.source = $" in query
        assert "ILIKE" in query

    async def test_pagination(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses(limit=10, offset=20)

        args = storage._pool.fetch.call_args[0]
        assert 10 in args
        assert 20 in args

    async def test_default_excludes_archived(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses()

        query = storage._pool.fetch.call_args[0][0]
        assert "e.archived = false" in query

    async def test_joins_heuristics_table(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses()

        query = storage._pool.fetch.call_args[0][0]
        assert "LEFT JOIN heuristics h" in query
        assert "matched_heuristic_condition" in query

    async def test_order_by_timestamp_desc(self, storage):
        storage._pool.fetch.return_value = []
        await storage.list_responses()

        query = storage._pool.fetch.call_args[0][0]
        assert "ORDER BY sub.timestamp DESC" in query

    async def test_not_connected_raises(self):
        s = MemoryStorage()
        s._pool = None
        with pytest.raises(RuntimeError, match="Not connected"):
            await s.list_responses()


class TestGetResponseDetail:
    async def test_found(self, storage):
        event_id = str(uuid.uuid4())
        row = _make_detail_row(id=uuid.UUID(event_id))
        storage._pool.fetchrow.return_value = row

        result = await storage.get_response_detail(event_id)

        assert result is not None
        assert str(result["id"]) == event_id
        assert result["decision_path"] == "heuristic"
        assert result["matched_heuristic_confidence"] == 0.85
        assert result["outcome"] == "success"

    async def test_not_found(self, storage):
        storage._pool.fetchrow.return_value = None
        result = await storage.get_response_detail(str(uuid.uuid4()))
        assert result is None

    async def test_includes_fire_data(self, storage):
        row = _make_detail_row(
            fire_id=uuid.uuid4(),
            feedback_source="implicit",
            outcome="fail",
        )
        storage._pool.fetchrow.return_value = row

        result = await storage.get_response_detail(str(row["id"]))
        assert result["feedback_source"] == "implicit"
        assert result["outcome"] == "fail"

    async def test_null_fire_data(self, storage):
        row = _make_detail_row(fire_id=None, feedback_source=None, outcome=None)
        storage._pool.fetchrow.return_value = row

        result = await storage.get_response_detail(str(row["id"]))
        assert result["fire_id"] is None
        assert result["outcome"] is None

    async def test_llm_path_with_prompt(self, storage):
        row = _make_detail_row(
            decision_path="llm",
            llm_prompt_text="You are an assistant...",
        )
        storage._pool.fetchrow.return_value = row

        result = await storage.get_response_detail(str(row["id"]))
        assert result["decision_path"] == "llm"
        assert result["llm_prompt_text"] == "You are an assistant..."

    async def test_joins_heuristics_and_fires(self, storage):
        storage._pool.fetchrow.return_value = None
        await storage.get_response_detail(str(uuid.uuid4()))

        query = storage._pool.fetchrow.call_args[0][0]
        assert "LEFT JOIN heuristic_fires hf" in query
        assert "LEFT JOIN heuristics h" in query
        assert "matched_heuristic_confidence" in query

    async def test_not_connected_raises(self):
        s = MemoryStorage()
        s._pool = None
        with pytest.raises(RuntimeError, match="Not connected"):
            await s.get_response_detail("some-id")
