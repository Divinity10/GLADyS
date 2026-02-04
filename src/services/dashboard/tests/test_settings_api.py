"""Tests for Settings tab API endpoints (config and cache).

The Settings tab uses a valid pattern:
- htmx loads component template once
- Alpine fetches JSON via JavaScript fetch()
- x-for renders from Alpine reactive state

These tests verify the JSON API endpoints work correctly.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

from backend import env as env_module


class TestConfigEndpoints:
    """Tests for /api/config endpoints."""

    @pytest.mark.anyio
    async def test_get_config_returns_environment_info(self):
        """GET /api/config returns current environment configuration."""
        from fun_api.routers.config import get_config

        response = await get_config()
        data = json.loads(response.body)

        # Should have environment mode
        assert "environment" in data
        assert data["environment"] in ("local", "docker")

        # Should have service addresses
        assert "orchestrator" in data
        assert "memory" in data
        assert "salience" in data
        assert "executive" in data
        assert "db_port" in data

    @pytest.mark.anyio
    async def test_get_environment_returns_mode(self):
        """GET /api/config/environment returns current mode."""
        from fun_api.routers.config import get_environment

        response = await get_environment()
        data = json.loads(response.body)

        assert "mode" in data
        assert data["mode"] in ("local", "docker")

    @pytest.mark.anyio
    async def test_set_environment_valid_mode(self):
        """PUT /api/config/environment switches mode."""
        from fun_api.routers.config import set_environment
        from fastapi import Request

        # Save current mode
        original_mode = env_module.env.mode

        mock_request = MagicMock(spec=Request)

        async def async_json():
            return {"mode": "docker" if original_mode == "local" else "local"}
        mock_request.json = async_json

        response = await set_environment(mock_request)
        data = json.loads(response.body)

        assert data["success"] is True
        assert "mode" in data

        # Restore original mode
        await env_module.env.switch(original_mode)

    @pytest.mark.anyio
    async def test_set_environment_invalid_mode(self):
        """PUT /api/config/environment rejects invalid mode."""
        from fun_api.routers.config import set_environment
        from fastapi import Request

        mock_request = MagicMock(spec=Request)

        async def async_json():
            return {"mode": "invalid_mode"}
        mock_request.json = async_json

        response = await set_environment(mock_request)

        assert response.status_code == 400
        data = json.loads(response.body)
        assert "error" in data


class TestCacheEndpoints:
    """Tests for /api/cache endpoints."""

    @pytest.fixture
    def mock_cache_stats_response(self):
        """Mock response from GetCacheStats gRPC call."""
        mock_resp = MagicMock()
        mock_resp.current_size = 42
        mock_resp.max_capacity = 1000
        mock_resp.total_hits = 150
        mock_resp.total_misses = 30
        return mock_resp

    @pytest.fixture
    def mock_cache_entries_response(self):
        """Mock response from ListCachedHeuristics gRPC call."""
        mock_h1 = MagicMock()
        mock_h1.id = "h-001"
        mock_h1.name = "Test Heuristic 1"
        mock_h1.condition_text = "when user says hello"
        mock_h1.confidence = 0.85
        mock_h1.hit_count = 10

        mock_h2 = MagicMock()
        mock_h2.id = "h-002"
        mock_h2.name = "Test Heuristic 2"
        mock_h2.condition_text = "when timer expires"
        mock_h2.confidence = 0.72
        mock_h2.hit_count = 5

        mock_resp = MagicMock()
        mock_resp.heuristics = [mock_h1, mock_h2]
        return mock_resp

    @pytest.mark.anyio
    async def test_cache_stats_returns_metrics(self, mock_cache_stats_response):
        """GET /api/cache/stats returns cache metrics."""
        mock_stub = MagicMock()
        mock_stub.GetCacheStats = AsyncMock(return_value=mock_cache_stats_response)

        with patch.object(env_module.env, "salience_stub", return_value=mock_stub):
            from fun_api.routers.cache import cache_stats

            response = await cache_stats()
            data = json.loads(response.body)

            assert data["current_size"] == 42
            assert data["max_capacity"] == 1000
            assert data["total_hits"] == 150
            assert data["total_misses"] == 30
            # hit_rate = 150 / (150 + 30) * 100 = 83.3%
            assert data["hit_rate"] == 83.3

    @pytest.mark.anyio
    async def test_cache_stats_no_stub(self):
        """GET /api/cache/stats returns error when stub unavailable."""
        with patch.object(env_module.env, "salience_stub", return_value=None):
            from fun_api.routers.cache import cache_stats

            response = await cache_stats()

            assert response.status_code == 503
            data = json.loads(response.body)
            assert "error" in data

    @pytest.mark.anyio
    async def test_cache_stats_grpc_error(self):
        """GET /api/cache/stats returns error on gRPC failure."""
        import grpc

        mock_stub = MagicMock()
        mock_error = grpc.RpcError()
        mock_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        mock_stub.GetCacheStats = AsyncMock(side_effect=mock_error)

        with patch.object(env_module.env, "salience_stub", return_value=mock_stub):
            from fun_api.routers.cache import cache_stats

            response = await cache_stats()

            assert response.status_code == 502
            data = json.loads(response.body)
            assert "error" in data

    @pytest.mark.anyio
    async def test_cache_entries_returns_heuristics(self, mock_cache_entries_response):
        """GET /api/cache/entries returns cached heuristics."""
        mock_stub = MagicMock()
        mock_stub.ListCachedHeuristics = AsyncMock(return_value=mock_cache_entries_response)

        with patch.object(env_module.env, "salience_stub", return_value=mock_stub):
            from fun_api.routers.cache import cache_entries

            response = await cache_entries()
            data = json.loads(response.body)

            assert data["count"] == 2
            assert len(data["entries"]) == 2

            entry1 = data["entries"][0]
            assert entry1["heuristic_id"] == "h-001"
            assert entry1["name"] == "Test Heuristic 1"
            assert entry1["condition_text"] == "when user says hello"
            assert entry1["confidence"] == 0.85
            assert entry1["hit_count"] == 10

    @pytest.mark.anyio
    async def test_cache_entries_no_stub(self):
        """GET /api/cache/entries returns error when stub unavailable."""
        with patch.object(env_module.env, "salience_stub", return_value=None):
            from fun_api.routers.cache import cache_entries

            response = await cache_entries()

            assert response.status_code == 503
            data = json.loads(response.body)
            assert "error" in data

    @pytest.mark.anyio
    async def test_cache_flush_returns_count(self):
        """POST /api/cache/flush returns entries flushed count."""
        mock_resp = MagicMock()
        mock_resp.entries_flushed = 42

        mock_stub = MagicMock()
        mock_stub.FlushCache = AsyncMock(return_value=mock_resp)

        with patch.object(env_module.env, "salience_stub", return_value=mock_stub):
            from fun_api.routers.cache import cache_flush

            response = await cache_flush()
            data = json.loads(response.body)

            assert data["flushed"] == 42

    @pytest.mark.anyio
    async def test_cache_flush_no_stub(self):
        """POST /api/cache/flush returns error when stub unavailable."""
        with patch.object(env_module.env, "salience_stub", return_value=None):
            from fun_api.routers.cache import cache_flush

            response = await cache_flush()

            assert response.status_code == 503
            data = json.loads(response.body)
            assert "error" in data
