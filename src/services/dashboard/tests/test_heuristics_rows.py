"""Tests for heuristics rows endpoint (server-side rendering).

IMPORTANT: QueryHeuristics returns HeuristicMatch wrappers, not raw Heuristic.
The response structure is: resp.matches[i].heuristic
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend import env as env_module


@pytest.fixture
def mock_heuristics():
    """Sample heuristics for testing."""
    return [
        {
            "id": "h-001-learned",
            "name": "Test Learned",
            "condition_text": "when user says hello",
            "effects_json": "{}",
            "confidence": 0.75,
            "origin": "learned",
            "origin_id": "evt-123",
            "fire_count": 5,
            "success_count": 3,
            "created_at_ms": 1705315200000,
            "updated_at_ms": 0,
        },
        {
            "id": "h-002-user",
            "name": "Test User",
            "condition_text": "when timer expires",
            "effects_json": "{}",
            "confidence": 0.90,
            "origin": "user",
            "origin_id": "",
            "fire_count": 10,
            "success_count": 8,
            "created_at_ms": 1704880800000,
            "updated_at_ms": 1705747200000,
        },
        {
            "id": "h-003-inactive",
            "name": "Test Inactive",
            "condition_text": "when something happens",
            "effects_json": "{}",
            "confidence": 0.30,
            "origin": "learned",
            "origin_id": "evt-456",
            "fire_count": 2,
            "success_count": 0,
            "created_at_ms": 1704448800000,
            "updated_at_ms": 0,
        },
    ]


def _make_mock_stub(heuristics_data):
    """Create a mock memory stub that returns heuristics via QueryHeuristics.

    QueryHeuristics returns resp.matches where each match is a HeuristicMatch
    with a .heuristic field containing the actual Heuristic proto.
    """
    mock_matches = []
    for h in heuristics_data:
        # Create mock Heuristic proto
        heuristic_proto = MagicMock()
        heuristic_proto.id = h["id"]
        heuristic_proto.name = h["name"]
        heuristic_proto.condition_text = h["condition_text"]
        heuristic_proto.effects_json = h.get("effects_json", "{}")
        heuristic_proto.confidence = h["confidence"]
        heuristic_proto.origin = h["origin"]
        heuristic_proto.origin_id = h.get("origin_id", "")
        heuristic_proto.fire_count = h["fire_count"]
        heuristic_proto.success_count = h["success_count"]
        heuristic_proto.created_at_ms = h["created_at_ms"]
        heuristic_proto.updated_at_ms = h.get("updated_at_ms", 0)

        # Wrap in HeuristicMatch
        match = MagicMock()
        match.heuristic = heuristic_proto
        match.score = 1.0  # Not used but present in real response
        mock_matches.append(match)

    mock_resp = MagicMock()
    mock_resp.matches = mock_matches

    mock_stub = MagicMock()
    mock_stub.QueryHeuristics = AsyncMock(return_value=mock_resp)
    return mock_stub


@pytest.mark.anyio
async def test_heuristics_rows_returns_html(mock_heuristics):
    """Endpoint returns HTML with rendered rows."""
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        # Should return TemplateResponse
        assert hasattr(response, "template")
        assert response.template.name == "components/heuristics_rows.html"
        assert "heuristics" in response.context
        assert len(response.context["heuristics"]) == 3


@pytest.mark.anyio
async def test_heuristics_rows_filters_by_origin(mock_heuristics):
    """Server-side filtering by origin works."""
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request, origin="user")

        # Should only have 1 heuristic (the user-origin one)
        heuristics = response.context["heuristics"]
        assert len(heuristics) == 1
        assert heuristics[0]["origin"] == "user"


@pytest.mark.anyio
async def test_heuristics_rows_filters_by_search(mock_heuristics):
    """Server-side search filtering works."""
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request, search="timer")

        heuristics = response.context["heuristics"]
        assert len(heuristics) == 1
        assert "timer" in heuristics[0]["condition_text"]


@pytest.mark.anyio
async def test_heuristics_rows_no_stub_returns_error():
    """When stub unavailable, returns error HTML."""
    with patch.object(env_module.env, "memory_stub", return_value=None):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        assert isinstance(response, HTMLResponse)
        assert "not available" in response.body.decode().lower()


@pytest.mark.anyio
async def test_heuristics_rows_grpc_error_returns_error_html(mock_heuristics):
    """gRPC error returns error HTML, not HTTP 500."""
    import grpc

    mock_stub = MagicMock()
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
    mock_stub.QueryHeuristics = AsyncMock(side_effect=mock_error)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        assert isinstance(response, HTMLResponse)
        assert "error" in response.body.decode().lower()


@pytest.mark.anyio
async def test_heuristics_rows_timestamp_conversion(mock_heuristics):
    """Timestamps are converted to ISO format."""
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        heuristics = response.context["heuristics"]
        # First heuristic has created_at_ms = 1705315200000
        # Should be converted to ISO string
        assert heuristics[0]["created_at"] is not None
        assert "2024" in heuristics[0]["created_at"]  # Year from timestamp

        # Third heuristic has updated_at_ms = 0, should be None
        assert heuristics[2]["updated_at"] is None


@pytest.mark.anyio
async def test_cross_tab_link_contains_correct_id(mock_heuristics):
    """Fire count link dispatches to Response tab with correct heuristic ID.

    The template uses {{ h.id }} in the switch-tab CustomEvent dispatch.
    This test verifies the IDs are present in the context for the template to render.
    """
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        # Verify the template will have access to heuristic IDs for cross-tab links
        heuristics = response.context["heuristics"]
        assert len(heuristics) == 3

        # Each heuristic should have an ID that the template uses in switch-tab dispatch
        for h in heuristics:
            assert "id" in h
            assert h["id"]  # Not empty
            assert h["id"].startswith("h-")  # Matches expected format

        # Verify specific IDs from fixture
        ids = [h["id"] for h in heuristics]
        assert "h-001-learned" in ids
        assert "h-002-user" in ids


@pytest.mark.anyio
async def test_action_buttons_have_correct_ids(mock_heuristics):
    """Action buttons reference correct heuristic IDs for API calls.

    The template uses {{ h.id }} in:
    - deleteHeuristic('{{ h.id }}') for delete button
    - saveHeuristic('{{ h.id }}', ...) for condition save
    - saveConfidence('{{ h.id }}', ...) for confidence save

    This test verifies IDs are present and valid in the context.
    """
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await list_heuristics_rows(mock_request)

        # Verify heuristics have IDs for action button JavaScript functions
        heuristics = response.context["heuristics"]
        assert len(heuristics) > 0

        for h in heuristics:
            # ID must be present and non-empty for delete/save buttons
            assert "id" in h
            assert h["id"]
            # ID should be a string (used in JS function calls)
            assert isinstance(h["id"], str)


@pytest.mark.anyio
async def test_heuristics_rows_filters_by_active(mock_heuristics):
    """Server-side filtering by active status works.

    Note: The 'active' field is derived from the proto. Since our mock
    doesn't set it, all heuristics default to active=True.
    """
    mock_stub = _make_mock_stub(mock_heuristics)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", MagicMock(), create=True):
        from backend.routers.heuristics import list_heuristics_rows
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        # Filter for active heuristics (default, all should be active)
        response = await list_heuristics_rows(mock_request, active="active")
        heuristics = response.context["heuristics"]
        assert len(heuristics) == 3  # All default to active

        # Filter for inactive (none in mock data)
        response = await list_heuristics_rows(mock_request, active="inactive")
        heuristics = response.context["heuristics"]
        assert len(heuristics) == 0


# --- Create Heuristic Tests ---

@pytest.mark.anyio
async def test_create_heuristic_success():
    """Create heuristic returns refreshed list on success."""
    # Mock successful StoreHeuristic response
    mock_store_resp = MagicMock()
    mock_store_resp.success = True
    mock_store_resp.error = ""

    # Mock QueryHeuristics for the refresh after create
    mock_query_resp = MagicMock()
    mock_query_resp.matches = []  # Empty list is fine for this test

    mock_stub = MagicMock()
    mock_stub.StoreHeuristic = AsyncMock(return_value=mock_store_resp)
    mock_stub.QueryHeuristics = AsyncMock(return_value=mock_query_resp)

    # Need to mock memory_pb2.Heuristic and memory_pb2.StoreHeuristicRequest
    mock_pb2 = MagicMock()

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", mock_pb2, create=True):
        from backend.routers.heuristics import create_heuristic
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await create_heuristic(
            mock_request,
            condition_text="when user greets",
            response_text="say hello back",
            confidence=85
        )

        # Should call StoreHeuristic
        mock_stub.StoreHeuristic.assert_called_once()

        # Should return template response (refreshed list)
        assert hasattr(response, "template")
        assert response.template.name == "components/heuristics_rows.html"


@pytest.mark.anyio
async def test_create_heuristic_grpc_error():
    """Create heuristic returns error HTML on gRPC failure."""
    import grpc

    class MockRpcError(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.INTERNAL

    mock_stub = MagicMock()
    mock_stub.StoreHeuristic = AsyncMock(side_effect=MockRpcError())

    mock_pb2 = MagicMock()

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", mock_pb2, create=True):
        from backend.routers.heuristics import create_heuristic
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await create_heuristic(
            mock_request,
            condition_text="test",
            response_text="test",
            confidence=80
        )

        assert isinstance(response, HTMLResponse)
        assert "error" in response.body.decode().lower()


@pytest.mark.anyio
async def test_create_heuristic_no_stub():
    """Create heuristic returns error when stub unavailable."""
    with patch.object(env_module.env, "memory_stub", return_value=None):
        from backend.routers.heuristics import create_heuristic
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await create_heuristic(
            mock_request,
            condition_text="test",
            response_text="test",
            confidence=80
        )

        assert isinstance(response, HTMLResponse)
        assert "not available" in response.body.decode().lower()


@pytest.mark.anyio
async def test_create_heuristic_store_failure():
    """Create heuristic handles StoreHeuristic returning success=False."""
    # Mock failed StoreHeuristic response
    mock_store_resp = MagicMock()
    mock_store_resp.success = False
    mock_store_resp.error = "Duplicate heuristic"

    mock_stub = MagicMock()
    mock_stub.StoreHeuristic = AsyncMock(return_value=mock_store_resp)

    mock_pb2 = MagicMock()

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", mock_pb2, create=True):
        from backend.routers.heuristics import create_heuristic
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await create_heuristic(
            mock_request,
            condition_text="test",
            response_text="test",
            confidence=80
        )

        assert isinstance(response, HTMLResponse)
        assert "duplicate" in response.body.decode().lower()


@pytest.mark.anyio
async def test_create_heuristic_confidence_clamping():
    """Create heuristic clamps confidence to 0.0-1.0 range."""
    mock_store_resp = MagicMock()
    mock_store_resp.success = True
    mock_store_resp.error = ""

    mock_query_resp = MagicMock()
    mock_query_resp.matches = []

    mock_stub = MagicMock()
    mock_stub.StoreHeuristic = AsyncMock(return_value=mock_store_resp)
    mock_stub.QueryHeuristics = AsyncMock(return_value=mock_query_resp)

    mock_pb2 = MagicMock()

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.heuristics.memory_pb2", mock_pb2, create=True):
        from backend.routers.heuristics import create_heuristic
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        # Test with over 100%
        await create_heuristic(mock_request, "test", "test", confidence=150)
        call_args = mock_pb2.Heuristic.call_args
        # Confidence should be clamped to 1.0
        assert call_args.kwargs.get("confidence", 1.0) <= 1.0

        # Test with negative
        await create_heuristic(mock_request, "test", "test", confidence=-10)
        call_args = mock_pb2.Heuristic.call_args
        assert call_args.kwargs.get("confidence", 0.0) >= 0.0
