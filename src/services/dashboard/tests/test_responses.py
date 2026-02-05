import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys

import grpc

# Module-level mock for proto availability
from backend import env as env_module

# Test Response Router
@pytest.mark.anyio
async def test_list_responses():
    """Test listing responses."""
    
    # Mock gRPC response
    mock_resp = MagicMock()
    mock_resp.error = ""
    mock_summary = MagicMock()
    mock_summary.event_id = "evt1"
    mock_summary.timestamp_ms = 1700000000000
    mock_summary.source = "test"
    mock_summary.raw_text = "hello"
    mock_summary.decision_path = "heuristic"
    mock_summary.matched_heuristic_id = "h1"
    mock_summary.response_text = "hi"
    mock_resp.responses = [mock_summary]

    mock_stub = MagicMock()
    mock_stub.ListResponses = AsyncMock(return_value=mock_resp)

    # Patch memory_pb2 in the router module
    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.responses.memory_pb2", MagicMock(), create=True) as mock_pb2:
        from backend.routers.responses import list_responses
        from fastapi import Request
        
        # Mock Request
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        
        # Call function
        response = await list_responses(mock_request, limit=10)
        
        # Verify
        assert response.status_code == 200
        # Check context
        assert len(response.context["responses"]) == 1
        assert response.context["responses"][0]["event_id"] == "evt1"
        assert response.context["responses"][0]["decision_path"] == "HEURISTIC"

@pytest.mark.anyio
async def test_get_response_detail():
    """Test getting response detail."""
    
    # Mock gRPC response
    mock_resp = MagicMock()
    mock_resp.error = ""
    mock_detail = MagicMock()
    mock_detail.event_id = "evt1"
    mock_detail.timestamp_ms = 1700000000000
    mock_detail.source = "test"
    mock_detail.raw_text = "hello"
    mock_detail.decision_path = "llm"
    mock_detail.matched_heuristic_id = ""
    mock_detail.matched_heuristic_confidence = 0.0
    mock_detail.llm_prompt_text = "prompt"
    mock_detail.response_text = "response"
    mock_detail.fire_id = ""
    mock_resp.detail = mock_detail

    mock_stub = MagicMock()
    mock_stub.GetResponseDetail = AsyncMock(return_value=mock_resp)

    # Patch memory_pb2 in the router module
    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.responses.memory_pb2", MagicMock(), create=True) as mock_pb2:
        from backend.routers.responses import get_response_detail
        from fastapi import Request
        
        # Mock Request
        mock_request = MagicMock(spec=Request)
        
        # Call function
        response = await get_response_detail(mock_request, "evt1")
        
        # Verify
        assert response.status_code == 200
        assert response.context["detail"]["event_id"] == "evt1"
        assert response.context["detail"]["llm_prompt_text"] == "prompt"


@pytest.mark.anyio
async def test_bulk_delete_responses_success():
    """Test bulk delete returns 200 with deleted count on success."""
    # Mock gRPC response
    mock_resp = MagicMock()
    mock_resp.error = ""
    mock_resp.deleted_count = 3

    mock_stub = MagicMock()
    mock_stub.DeleteResponses = AsyncMock(return_value=mock_resp)

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.responses.memory_pb2", MagicMock(), create=True):
        from backend.routers.responses import bulk_delete_responses, BulkDeleteRequest
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        body = BulkDeleteRequest(event_ids=["evt1", "evt2", "evt3"])

        response = await bulk_delete_responses(mock_request, body)

        assert response.status_code == 200
        import json
        data = json.loads(response.body)
        assert data["deleted"] == 3


@pytest.mark.anyio
async def test_bulk_delete_responses_grpc_error():
    """Test bulk delete returns error on gRPC failure."""
    # Create a mock RpcError that has code() method
    class MockRpcError(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.INTERNAL

    mock_stub = MagicMock()
    mock_stub.DeleteResponses = AsyncMock(side_effect=MockRpcError())

    with patch.object(env_module.env, "memory_stub", return_value=mock_stub), \
         patch("backend.routers.responses.memory_pb2", MagicMock(), create=True):
        from backend.routers.responses import bulk_delete_responses, BulkDeleteRequest
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        body = BulkDeleteRequest(event_ids=["evt1"])

        response = await bulk_delete_responses(mock_request, body)

        assert response.status_code == 500
        import json
        data = json.loads(response.body)
        assert "detail" in data


@pytest.mark.anyio
async def test_bulk_delete_responses_no_stub():
    """Test bulk delete returns 500 when memory stub unavailable."""
    with patch.object(env_module.env, "memory_stub", return_value=None):
        from backend.routers.responses import bulk_delete_responses, BulkDeleteRequest
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        body = BulkDeleteRequest(event_ids=["evt1"])

        response = await bulk_delete_responses(mock_request, body)

        assert response.status_code == 500
        import json
        data = json.loads(response.body)
        assert "detail" in data


@pytest.mark.anyio
async def test_bulk_delete_request_model_validates():
    """Test BulkDeleteRequest pydantic model accepts valid input."""
    from backend.routers.responses import BulkDeleteRequest

    # Valid request
    req = BulkDeleteRequest(event_ids=["id1", "id2"])
    assert req.event_ids == ["id1", "id2"]

    # Empty list is valid
    req_empty = BulkDeleteRequest(event_ids=[])
    assert req_empty.event_ids == []


@pytest.mark.anyio
async def test_bulk_delete_request_model_rejects_invalid():
    """Test BulkDeleteRequest pydantic model rejects invalid input."""
    from backend.routers.responses import BulkDeleteRequest
    from pydantic import ValidationError

    # Missing field
    with pytest.raises(ValidationError):
        BulkDeleteRequest()

    # Wrong type
    with pytest.raises(ValidationError):
        BulkDeleteRequest(event_ids="not-a-list")
