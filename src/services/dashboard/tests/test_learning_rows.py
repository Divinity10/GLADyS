"""Tests for learning (fires) rows endpoint."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend import env as env_module


@pytest.fixture
def mock_fires():
    """Sample fire data."""
    return [
        {
            "id": "fire-001",
            "heuristic_id": "h-001",
            "heuristic_name": "Test Heuristic",
            "event_id": "evt-001",
            "condition_text": "when user says hello",
            "outcome": "success",
            "feedback_source": "explicit",
            "confidence": 0.75,
            "fired_at_ms": 1706961600000,
        },
        {
            "id": "fire-002",
            "heuristic_id": "h-002",
            "heuristic_name": "Another Heuristic",
            "event_id": "evt-002",
            "condition_text": "when timer expires",
            "outcome": "failure",
            "feedback_source": "implicit",
            "confidence": 0.60,
            "fired_at_ms": 1706958000000,
        },
    ]


def _make_mock_stub(fires_data):
    """Create mock memory stub that returns fires via ListFires."""
    mock_fires = []
    for f in fires_data:
        fire_proto = MagicMock()
        fire_proto.id = f["id"]
        fire_proto.heuristic_id = f["heuristic_id"]
        fire_proto.heuristic_name = f.get("heuristic_name", "")
        fire_proto.event_id = f["event_id"]
        fire_proto.condition_text = f.get("condition_text", "")
        fire_proto.outcome = f["outcome"]
        fire_proto.feedback_source = f.get("feedback_source", "")
        fire_proto.confidence = f.get("confidence", 0.0)
        fire_proto.fired_at_ms = f.get("fired_at_ms", 0)
        mock_fires.append(fire_proto)

    mock_resp = MagicMock()
    mock_resp.fires = mock_fires
    mock_resp.total_count = len(mock_fires)

    mock_stub = MagicMock()
    mock_stub.ListFires = AsyncMock(return_value=mock_resp)
    return mock_stub


@pytest.mark.anyio
async def test_fires_rows_returns_html(mock_fires):
    """Endpoint returns HTML with rendered rows."""
    mock_stub = _make_mock_stub(mock_fires)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request)

        assert hasattr(response, "template")
        assert response.template.name == "components/learning_rows.html"
        assert "fires" in response.context
        assert len(response.context["fires"]) == 2


@pytest.mark.anyio
async def test_fires_rows_filters_by_outcome(mock_fires):
    """Server-side filtering by outcome works."""
    # Only return success fires
    success_fires = [f for f in mock_fires if f["outcome"] == "success"]
    mock_stub = _make_mock_stub(success_fires)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request, outcome="success")

        fires = response.context["fires"]
        assert len(fires) == 1
        assert fires[0]["outcome"] == "success"


@pytest.mark.anyio
async def test_fires_rows_filters_by_search(mock_fires):
    """Server-side search filtering works."""
    mock_stub = _make_mock_stub(mock_fires)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request, search="timer")

        fires = response.context["fires"]
        assert len(fires) == 1
        assert "timer" in fires[0]["condition_text"]


@pytest.mark.anyio
async def test_fires_rows_no_stub_returns_error():
    """When stub unavailable, returns error HTML."""
    with patch.object(env_module.env, "memory_stub", return_value=None):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request)

        assert isinstance(response, HTMLResponse)
        assert "not available" in response.body.decode().lower()


@pytest.mark.anyio
async def test_fires_rows_grpc_error_returns_error_html(mock_fires):
    """gRPC error returns error HTML, not HTTP 500."""
    import grpc

    mock_stub = MagicMock()
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
    mock_stub.ListFires = AsyncMock(side_effect=mock_error)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request)

        assert isinstance(response, HTMLResponse)
        assert "error" in response.body.decode().lower()


@pytest.mark.anyio
async def test_fires_rows_timestamp_conversion(mock_fires):
    """Timestamps are converted to ISO format."""
    mock_stub = _make_mock_stub(mock_fires)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request)

        fires = response.context["fires"]
        # First fire has fired_at_ms, should be converted to ISO string
        assert fires[0]["fired_at"] is not None
        assert "2024" in fires[0]["fired_at"]  # Year from timestamp


@pytest.mark.anyio
async def test_cross_tab_link_heuristic_id_present(mock_fires):
    """Heuristic ID is present for cross-tab link to Heuristics tab."""
    mock_stub = _make_mock_stub(mock_fires)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.fires.memory_pb2", MagicMock(), create=True):
        from backend.routers.fires import list_fires_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_fires_rows(mock_request)

        fires = response.context["fires"]
        assert len(fires) == 2

        # Each fire should have a heuristic_id for cross-tab links
        for f in fires:
            assert "heuristic_id" in f
            assert f["heuristic_id"]  # Not empty

        # Verify specific IDs from fixture
        ids = [f["heuristic_id"] for f in fires]
        assert "h-001" in ids
        assert "h-002" in ids
