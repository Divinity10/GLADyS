"""Tests for LLM API endpoints.

The LLM tab uses a valid pattern:
- htmx loads component template once
- Alpine fetches JSON via JavaScript fetch()
- x-for renders from Alpine reactive state

These tests verify the JSON API endpoints work correctly.
"""

import pytest
from unittest.mock import patch, MagicMock
import json


@pytest.fixture
def mock_ollama_config():
    """Mock Ollama configuration."""
    return {
        "endpoint": "local",
        "url": "http://localhost:11434",
        "model": "llama3.2",
    }


@pytest.fixture
def mock_ollama_tags_response():
    """Mock response from Ollama /api/tags."""
    return {
        "models": [
            {"name": "llama3.2:latest"},
            {"name": "mistral:latest"},
            {"name": "codellama:7b"},
        ]
    }


@pytest.fixture
def mock_ollama_ps_response():
    """Mock response from Ollama /api/ps (loaded models)."""
    return {
        "models": [
            {"name": "llama3.2:latest"},
        ]
    }


class TestLlmStatus:
    """Tests for GET /api/llm/status endpoint."""

    @pytest.mark.anyio
    async def test_status_connected_with_models(
        self, mock_ollama_config, mock_ollama_tags_response, mock_ollama_ps_response
    ):
        """Status returns connected with available and loaded models."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value=mock_ollama_config), \
             patch("fun_api.routers.llm._ollama_request") as mock_request:

            # First call is /api/tags, second is /api/ps
            mock_request.side_effect = [
                (200, mock_ollama_tags_response),
                (200, mock_ollama_ps_response),
            ]

            from fun_api.routers.llm import llm_status

            response = await llm_status()
            data = json.loads(response.body)

            assert data["status"] == "connected"
            assert data["url"] == "http://localhost:11434"
            assert data["model"] == "llama3.2"
            assert len(data["available_models"]) == 3
            assert "llama3.2:latest" in data["available_models"]
            assert len(data["loaded_models"]) == 1
            assert "llama3.2:latest" in data["loaded_models"]

    @pytest.mark.anyio
    async def test_status_not_configured(self):
        """Status returns not_configured when no URL set."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value={"endpoint": None, "url": "", "model": ""}):
            from fun_api.routers.llm import llm_status

            response = await llm_status()
            data = json.loads(response.body)

            assert data["status"] == "not_configured"
            assert data["loaded_models"] == []

    @pytest.mark.anyio
    async def test_status_unreachable(self, mock_ollama_config):
        """Status returns unreachable when Ollama not responding."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value=mock_ollama_config), \
             patch("fun_api.routers.llm._ollama_request", return_value=(0, {"error": "unreachable: Connection refused"})):

            from fun_api.routers.llm import llm_status

            response = await llm_status()
            data = json.loads(response.body)

            assert data["status"] == "unreachable"
            assert "error" in data
            assert data["loaded_models"] == []


class TestLlmTest:
    """Tests for POST /api/llm/test endpoint."""

    @pytest.mark.anyio
    async def test_test_prompt_success(self, mock_ollama_config):
        """Test prompt returns response and timing."""
        mock_generate_response = {
            "response": "Hello! How can I help you today?",
            "total_duration": 1500000000,  # nanoseconds
        }

        with patch("fun_api.routers.llm._get_ollama_config", return_value=mock_ollama_config), \
             patch("fun_api.routers.llm._ollama_request", return_value=(200, mock_generate_response)):

            from fun_api.routers.llm import llm_test
            from fastapi import Request

            mock_request = MagicMock(spec=Request)
            mock_request.json = MagicMock(return_value={"prompt": "Say hello"})

            # Make it async
            async def async_json():
                return {"prompt": "Say hello"}
            mock_request.json = async_json

            response = await llm_test(mock_request)
            data = json.loads(response.body)

            assert data["response"] == "Hello! How can I help you today?"
            assert data["model"] == "llama3.2"
            assert data["total_duration_ms"] == 1500.0

    @pytest.mark.anyio
    async def test_test_prompt_not_configured(self):
        """Test prompt returns error when not configured."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value={"endpoint": None, "url": "", "model": ""}):

            from fun_api.routers.llm import llm_test
            from fastapi import Request

            mock_request = MagicMock(spec=Request)

            async def async_json():
                return {"prompt": "Say hello"}
            mock_request.json = async_json

            response = await llm_test(mock_request)

            assert response.status_code == 503
            data = json.loads(response.body)
            assert "error" in data


class TestLlmWarm:
    """Tests for POST /api/llm/warm endpoint."""

    @pytest.mark.anyio
    async def test_warm_success(self, mock_ollama_config):
        """Warm model returns success."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value=mock_ollama_config), \
             patch("fun_api.routers.llm._ollama_request", return_value=(200, {})):

            from fun_api.routers.llm import llm_warm

            response = await llm_warm()
            data = json.loads(response.body)

            assert data["success"] is True
            assert data["model"] == "llama3.2"

    @pytest.mark.anyio
    async def test_warm_not_configured(self):
        """Warm returns error when not configured."""
        with patch("fun_api.routers.llm._get_ollama_config", return_value={"endpoint": None, "url": "", "model": ""}):

            from fun_api.routers.llm import llm_warm

            response = await llm_warm()

            assert response.status_code == 503
            data = json.loads(response.body)
            assert "error" in data
