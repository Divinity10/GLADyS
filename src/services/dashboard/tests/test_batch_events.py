"""Unit tests for batch event upload (fun_api/routers/events.py).

Tests verify that gRPC errors during batch upload are logged, not swallowed.
This is the fix for issue #93.
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

# Import the module under test
from fun_api.routers import events as events_router


class MockRpcError(grpc.RpcError):
    """Mock gRPC error for testing."""

    def __init__(self, code=grpc.StatusCode.UNAVAILABLE, details="Service unavailable"):
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details

    def __str__(self):
        return f"<RpcError: {self._code.name}: {self._details}>"


@pytest.fixture
def mock_env():
    """Mock the env module."""
    with patch.object(events_router, "env") as mock:
        mock.sync_orchestrator_stub.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_protos():
    """Mock proto availability."""
    with patch.object(events_router, "PROTOS_AVAILABLE", True):
        with patch.object(events_router, "common_pb2") as mock_common:
            mock_common.Event = MagicMock()
            yield mock_common


class TestBatchSubmitErrorLogging:
    """Test that gRPC errors are logged during batch submit."""

    @pytest.mark.asyncio
    async def test_grpc_error_is_logged(self, mock_env, mock_protos):
        """gRPC errors during batch publish should be logged."""
        # Arrange
        mock_stub = MagicMock()
        mock_stub.PublishEvents.side_effect = MockRpcError()
        mock_env.sync_orchestrator_stub.return_value = mock_stub

        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = [{"text": "test event", "source": "test"}]

        captured_logs = []

        def mock_log_error(*args, **kwargs):
            captured_logs.append({"args": args, "kwargs": kwargs})

        # Act
        with patch.object(events_router.logger, "error", mock_log_error):
            response = await events_router.submit_batch(mock_request)

            # The response returns immediately (thread publishes async)
            assert response.status_code == 200

            # Wait for thread to execute and log
            import time
            time.sleep(0.2)

        # Assert - error should have been logged
        assert len(captured_logs) > 0, "Expected error to be logged"
        log_kwargs = captured_logs[0]["kwargs"]
        assert "event_id" in log_kwargs
        assert "error" in log_kwargs

    @pytest.mark.asyncio
    async def test_batch_returns_success_immediately(self, mock_env, mock_protos):
        """Batch submit returns success before publish completes.

        This is expected behavior - the response is async.
        The test verifies we return accepted count correctly.
        """
        mock_stub = MagicMock()
        mock_stub.PublishEvents.return_value = iter([MagicMock()])
        mock_env.sync_orchestrator_stub.return_value = mock_stub

        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = [
            {"text": "event 1", "source": "test"},
            {"text": "event 2", "source": "test"},
        ]

        response = await events_router.submit_batch(mock_request)

        assert response.status_code == 200
        # Parse JSON response
        import json
        body = json.loads(response.body)
        assert body["accepted"] == 2
        assert len(body["event_ids"]) == 2

    @pytest.mark.asyncio
    async def test_validation_error_returns_400(self, mock_env, mock_protos):
        """Invalid event data should return 400."""
        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = [{"invalid": "no text field"}]

        response = await events_router.submit_batch(mock_request)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_non_array_body_returns_400(self, mock_env, mock_protos):
        """Non-array JSON body should return 400."""
        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = {"text": "not an array"}

        response = await events_router.submit_batch(mock_request)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_exceeds_max_batch_size_returns_400(self, mock_env, mock_protos):
        """Batch size > 50 should return 400."""
        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = [{"text": f"event {i}"} for i in range(51)]

        response = await events_router.submit_batch(mock_request)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_proto_stubs_unavailable_returns_503(self, mock_env):
        """Missing proto stubs should return 503."""
        mock_env.sync_orchestrator_stub.return_value = None

        mock_request = AsyncMock(spec=Request)
        mock_request.json.return_value = [{"text": "test"}]

        response = await events_router.submit_batch(mock_request)

        assert response.status_code == 503
