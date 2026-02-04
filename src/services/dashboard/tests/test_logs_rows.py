"""Tests for logs lines endpoint (server-side rendering)."""

import pytest
from unittest.mock import MagicMock, patch, mock_open

from backend import env as env_module


@pytest.fixture
def mock_log_lines():
    """Sample log lines for testing."""
    return [
        "2026-02-03 10:00:00 INFO Starting service...",
        "2026-02-03 10:00:01 DEBUG Connecting to database",
        "2026-02-03 10:00:02 WARN Connection slow",
        "2026-02-03 10:00:03 ERROR Failed to connect",
        "2026-02-03 10:00:04 CRITICAL System failure",
    ]


@pytest.mark.anyio
async def test_logs_lines_returns_html(mock_log_lines):
    """Endpoint returns HTML with rendered lines."""
    log_content = "\n".join(mock_log_lines) + "\n"

    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        with patch("builtins.open", mock_open(read_data=log_content)):
            from backend.routers.logs import get_log_lines
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.headers = {}

            response = await get_log_lines(mock_request, "orchestrator", tail=100)

            # Should return TemplateResponse
            assert hasattr(response, "template")
            assert response.template.name == "components/logs_lines.html"
            assert "lines" in response.context
            assert response.context["count"] == 5
            assert response.context["error"] is None


@pytest.mark.anyio
async def test_logs_lines_classifies_levels(mock_log_lines):
    """Log lines are classified by level for styling."""
    log_content = "\n".join(mock_log_lines) + "\n"

    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        with patch("builtins.open", mock_open(read_data=log_content)):
            from backend.routers.logs import get_log_lines
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.headers = {}

            response = await get_log_lines(mock_request, "orchestrator")

            lines = response.context["lines"]

            # Check classification
            assert lines[0]["level"] == "info"
            assert lines[1]["level"] == "debug"
            assert lines[2]["level"] == "warn"
            assert lines[3]["level"] == "error"
            assert lines[4]["level"] == "error"  # CRITICAL maps to error


@pytest.mark.anyio
async def test_logs_lines_error_returns_error_html():
    """Missing log file returns error in template context."""
    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        from backend.routers.logs import get_log_lines
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        response = await get_log_lines(mock_request, "nonexistent")

        # Should return template with error context
        assert hasattr(response, "template")
        assert response.context["error"] is not None
        assert "No log file" in response.context["error"]
        assert response.context["lines"] == []


@pytest.mark.anyio
async def test_logs_lines_respects_tail_param(mock_log_lines):
    """Tail parameter limits number of lines."""
    log_content = "\n".join(mock_log_lines) + "\n"

    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        with patch("builtins.open", mock_open(read_data=log_content)):
            from backend.routers.logs import get_log_lines
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.headers = {}

            response = await get_log_lines(mock_request, "orchestrator", tail=2)

            # Should only have last 2 lines
            assert response.context["count"] == 2
            lines = response.context["lines"]
            # Last 2 lines are CRITICAL and ERROR
            assert lines[0]["text"] == "2026-02-03 10:00:03 ERROR Failed to connect"
            assert lines[1]["text"] == "2026-02-03 10:00:04 CRITICAL System failure"


@pytest.mark.anyio
async def test_logs_lines_read_error_returns_error():
    """File read error returns error in template context."""
    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            from backend.routers.logs import get_log_lines
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.headers = {}

            response = await get_log_lines(mock_request, "orchestrator")

            assert hasattr(response, "template")
            assert response.context["error"] is not None
            assert "Access denied" in response.context["error"]


@pytest.mark.anyio
async def test_logs_lines_preserves_line_text():
    """Log line text is preserved exactly."""
    special_line = "2026-02-03 10:00:00 INFO Special chars: <>&\"\n"
    log_content = special_line

    with patch("backend.routers.logs.LOG_DIR") as mock_log_dir:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_log_dir.__truediv__ = MagicMock(return_value=mock_path)

        with patch("builtins.open", mock_open(read_data=log_content)):
            from backend.routers.logs import get_log_lines
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.headers = {}

            response = await get_log_lines(mock_request, "orchestrator")

            lines = response.context["lines"]
            assert len(lines) == 1
            # Text should be stripped of trailing newline but otherwise preserved
            assert lines[0]["text"] == "2026-02-03 10:00:00 INFO Special chars: <>&\""
