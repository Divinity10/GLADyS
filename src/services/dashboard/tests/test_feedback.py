"""Minimal test for feedback endpoint response_id forwarding.

Tests the critical path: response_id must be passed to executive_stub.ProvideFeedback.
Uses proper pytest fixtures — no sys.modules manipulation.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend import env as env_module


@pytest.mark.anyio
async def test_feedback_forwards_response_id():
    """Verify response_id from request body is forwarded to ProvideFeedback."""

    # Mock executive stub response
    mock_resp = MagicMock()
    mock_resp.created_heuristic_id = ""
    mock_resp.error_message = ""

    mock_stub = MagicMock()
    mock_stub.ProvideFeedback = AsyncMock(return_value=mock_resp)

    # Patch executive_stub and executive_pb2 in the events router
    with patch.object(env_module.env, "executive_stub", return_value=mock_stub), \
         patch("backend.routers.events.executive_pb2", create=True) as mock_exec_pb2:

        from backend.routers.events import submit_feedback
        from fastapi import Request

        # Mock Request with JSON body containing response_id
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"content-type": "application/json"}
        mock_request.json = AsyncMock(return_value={
            "event_id": "evt-123",
            "response_id": "resp-456",
            "feedback": "good",
        })

        # Call the endpoint
        response = await submit_feedback(mock_request)

        # Verify ProvideFeedbackRequest was called with correct response_id
        mock_exec_pb2.ProvideFeedbackRequest.assert_called_once_with(
            event_id="evt-123",
            positive=True,
            response_id="resp-456",
        )

        # Verify stub was called
        mock_stub.ProvideFeedback.assert_called_once()

        # Verify success response
        assert response.status_code == 200
