"""Unit tests for ListEvents and GetEvent gRPC handlers.

Tests proto serialization round-trip: DB row → storage → handler → proto message.
Uses mocked storage to isolate the gRPC handler logic.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from gladys_memory import memory_pb2, types_pb2
from gladys_memory.grpc_server import MemoryStorageServicer


@pytest.fixture
def servicer():
    """MemoryStorageServicer with mocked storage and embeddings."""
    storage = AsyncMock()
    embeddings = MagicMock()
    return MemoryStorageServicer(storage, embeddings)


@pytest.fixture
def context():
    """Mock gRPC context with metadata."""
    ctx = AsyncMock()
    ctx.invocation_metadata = MagicMock(return_value=[])
    ctx.abort.side_effect = Exception("aborted")
    return ctx


def _make_db_row(**overrides):
    """Build a dict mimicking what storage.list_events() returns."""
    defaults = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc),
        "source": "test-sensor",
        "raw_text": "player opened inventory",
        "salience": {"novelty": 0.5, "threat": 0.0, "humor": 0.0,
                     "opportunity": 0.0, "goal_relevance": 0.3,
                     "social": 0.0, "emotional": 0.0,
                     "actionability": 0.0, "habituation": 0.0},
        "response_text": "noted",
        "response_id": "resp-001",
        "predicted_success": 0.85,
        "prediction_confidence": 0.9,
        "matched_heuristic_id": uuid.uuid4(),
    }
    defaults.update(overrides)
    return defaults


class TestListEvents:
    async def test_returns_events(self, servicer, context):
        row = _make_db_row()
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        assert len(resp.events) == 1
        ev = resp.events[0]
        assert ev.id == str(row["id"])
        assert ev.source == "test-sensor"
        assert ev.raw_text == "player opened inventory"

    async def test_timestamp_ms_conversion(self, servicer, context):
        ts = datetime(2026, 1, 31, 14, 30, 0, tzinfo=timezone.utc)
        row = _make_db_row(timestamp=ts)
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        ev = resp.events[0]
        assert ev.timestamp_ms == int(ts.timestamp() * 1000)

    async def test_salience_vector_populated(self, servicer, context):
        row = _make_db_row(salience={"novelty": 0.75, "threat": 0.0, "humor": 0.1})
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        ev = resp.events[0]
        assert ev.salience.novelty == pytest.approx(0.75, abs=1e-6)
        assert ev.salience.threat == 0.0
        assert ev.salience.humor == pytest.approx(0.1, abs=1e-6)

    async def test_zero_salience_preserved(self, servicer, context):
        """threat=0.0 should be in the proto, not dropped."""
        row = _make_db_row(salience={"threat": 0.0, "novelty": 0.5})
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        # proto3 defaults to 0.0, so threat=0.0 is correct
        assert resp.events[0].salience.threat == 0.0

    async def test_matched_heuristic_id_serialized(self, servicer, context):
        h_id = uuid.uuid4()
        row = _make_db_row(matched_heuristic_id=h_id)
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        assert resp.events[0].matched_heuristic_id == str(h_id)

    async def test_null_matched_heuristic_id(self, servicer, context):
        row = _make_db_row(matched_heuristic_id=None)
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        assert resp.events[0].matched_heuristic_id == ""

    async def test_null_prediction_fields(self, servicer, context):
        row = _make_db_row(predicted_success=None, prediction_confidence=None)
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        ev = resp.events[0]
        assert ev.predicted_success == 0.0
        assert ev.prediction_confidence == 0.0

    async def test_null_response_fields(self, servicer, context):
        row = _make_db_row(response_text=None, response_id=None)
        servicer.storage.list_events.return_value = [row]

        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        ev = resp.events[0]
        assert ev.response_text == ""
        assert ev.response_id == ""

    async def test_default_limit(self, servicer, context):
        servicer.storage.list_events.return_value = []
        request = memory_pb2.ListEventsRequest()
        await servicer.ListEvents(request, context)

        servicer.storage.list_events.assert_called_once_with(
            limit=50, offset=0, source=None, include_archived=False,
        )

    async def test_source_filter_passthrough(self, servicer, context):
        servicer.storage.list_events.return_value = []
        request = memory_pb2.ListEventsRequest(source="minecraft", limit=5)
        await servicer.ListEvents(request, context)

        servicer.storage.list_events.assert_called_once_with(
            limit=5, offset=0, source="minecraft", include_archived=False,
        )

    async def test_empty_result(self, servicer, context):
        servicer.storage.list_events.return_value = []
        request = memory_pb2.ListEventsRequest(limit=10)
        resp = await servicer.ListEvents(request, context)

        assert len(resp.events) == 0
        assert resp.error == ""

    async def test_storage_error_aborts(self, servicer, context):
        servicer.storage.list_events.side_effect = RuntimeError("DB down")
        request = memory_pb2.ListEventsRequest(limit=10)
        with pytest.raises(Exception, match="aborted"):
            await servicer.ListEvents(request, context)

        context.abort.assert_called_once()


class TestGetEvent:
    async def test_found(self, servicer, context):
        event_id = str(uuid.uuid4())
        row = _make_db_row(id=uuid.UUID(event_id))
        servicer.storage.get_event.return_value = row

        request = memory_pb2.GetEventRequest(event_id=event_id)
        resp = await servicer.GetEvent(request, context)

        assert resp.event.id == event_id
        assert resp.event.source == "test-sensor"
        assert resp.error == ""

    async def test_not_found(self, servicer, context):
        servicer.storage.get_event.return_value = None

        request = memory_pb2.GetEventRequest(event_id=str(uuid.uuid4()))
        resp = await servicer.GetEvent(request, context)

        assert resp.error == "Event not found"

    async def test_empty_event_id_aborts(self, servicer, context):
        request = memory_pb2.GetEventRequest(event_id="")
        with pytest.raises(Exception, match="aborted"):
            await servicer.GetEvent(request, context)

        # abort called at least once (may be called again by outer except block)
        assert context.abort.call_count >= 1

    async def test_salience_round_trip(self, servicer, context):
        """Salience dict from DB should serialize to proto correctly."""
        salience = {
            "threat": 0.1, "opportunity": 0.2, "humor": 0.3,
            "novelty": 0.4, "goal_relevance": 0.5,
            "social": 0.6, "emotional": 0.7,
            "actionability": 0.8, "habituation": 0.9,
        }
        row = _make_db_row(salience=salience)
        servicer.storage.get_event.return_value = row

        request = memory_pb2.GetEventRequest(event_id=str(row["id"]))
        resp = await servicer.GetEvent(request, context)

        s = resp.event.salience
        assert abs(s.threat - 0.1) < 1e-6
        assert abs(s.novelty - 0.4) < 1e-6
        assert abs(s.habituation - 0.9) < 1e-6

    async def test_non_dict_salience(self, servicer, context):
        """If salience is not a dict (corrupt data), should not crash."""
        row = _make_db_row(salience=None)
        servicer.storage.get_event.return_value = row

        request = memory_pb2.GetEventRequest(event_id=str(row["id"]))
        resp = await servicer.GetEvent(request, context)

        # Should get default zero salience vector
        assert resp.event.salience.threat == 0.0
