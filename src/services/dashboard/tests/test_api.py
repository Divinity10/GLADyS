"""Dashboard API contract tests.

These tests validate the response shapes that the frontend depends on.
gRPC-dependent endpoints are tested in two modes:
  1. Stub unavailable (503 responses)
  2. Mocked stubs (happy path shapes)
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend package, gladys_client, fun_api, and CLI are importable
DASHBOARD_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DASHBOARD_DIR.parent.parent
sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib" / "gladys_client"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services"))
sys.path.insert(0, str(PROJECT_ROOT / "cli"))

# Mock gladys_client.db before importing the app (routers import it at module level)
mock_db = MagicMock()
sys.modules["gladys_client.db"] = mock_db

# Mock proto stubs so imports don't fail
mock_protos = MagicMock()
sys.modules["gladys_orchestrator"] = mock_protos
sys.modules["gladys_orchestrator.generated"] = mock_protos.generated

# Patch PROTOS_AVAILABLE before importing routers
import backend.env as env_module

env_module.PROTOS_AVAILABLE = False

from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ─── Config ───────────────────────────────────────────────────────────────


class TestConfig:
    def test_get_config_returns_expected_keys(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("environment", "orchestrator", "memory", "salience",
                     "executive", "db_port"):
            assert key in data, f"Missing key: {key}"

    def test_get_config_environment_is_string(self, client):
        data = client.get("/api/config").json()
        assert data["environment"] in ("local", "docker")

    def test_get_environment(self, client):
        resp = client.get("/api/config/environment")
        assert resp.status_code == 200
        assert "mode" in resp.json()

    def test_set_environment_valid(self, client):
        # Router uses untyped `request` param — FastAPI injects Request object
        resp = client.put("/api/config/environment",
                          json={"mode": "local"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["mode"] == "local"

    def test_set_environment_invalid(self, client):
        resp = client.put("/api/config/environment",
                          json={"mode": "mars"})
        assert resp.status_code == 400


# ─── Logs ─────────────────────────────────────────────────────────────────


class TestLogs:
    def test_missing_log_file(self, client):
        resp = client.get("/api/logs/nonexistent-service")
        assert resp.status_code == 200
        data = resp.json()
        assert "lines" in data
        assert isinstance(data["lines"], list)
        assert "service" in data

    def test_existing_log_file(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                         delete=False) as f:
            f.write("INFO Starting up\n")
            f.write("WARN something\n")
            f.write("ERROR bad thing\n")
            f.flush()
            log_path = Path(f.name)

        try:
            service_name = log_path.stem
            with patch("fun_api.routers.logs.LOG_DIR", log_path.parent):
                resp = client.get(f"/api/logs/{service_name}?tail=2")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["lines"]) == 2
            assert data["lines"][0] == "WARN something"
            assert data["lines"][1] == "ERROR bad thing"
        finally:
            log_path.unlink()

    def test_log_response_shape(self, client):
        """Frontend expects {service, lines, total_lines}."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                         delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            log_path = Path(f.name)

        try:
            with patch("fun_api.routers.logs.LOG_DIR", log_path.parent):
                data = client.get(f"/api/logs/{log_path.stem}").json()
            assert "lines" in data
            assert "service" in data
            assert isinstance(data["lines"], list)
        finally:
            log_path.unlink()


# ─── gRPC-dependent endpoints (stub unavailable → 503) ───────────────────


class TestGrpcUnavailable:
    """When proto stubs aren't available, endpoints should return 503."""

    def test_heuristics_list_503(self, client):
        resp = client.get("/api/heuristics")
        assert resp.status_code == 503

    def test_heuristics_create_503(self, client):
        resp = client.post("/api/heuristics",
                           json={"name": "test"})
        assert resp.status_code == 503

    def test_memory_probe_empty_query(self, client):
        """Probe with empty query should return 400 regardless of stub."""
        with patch.object(env_module, "PROTOS_AVAILABLE", True):
            with patch.object(env_module.env, "memory_stub", return_value=MagicMock()):
                resp = client.post("/api/memory/probe",
                                   json={"query": ""})
                assert resp.status_code == 400

    def test_cache_stats_503(self, client):
        resp = client.get("/api/cache/stats")
        assert resp.status_code == 503

    def test_cache_entries_503(self, client):
        resp = client.get("/api/cache/entries")
        assert resp.status_code == 503

    def test_cache_flush_503(self, client):
        resp = client.post("/api/cache/flush")
        assert resp.status_code == 503


# ─── Fires (DB-dependent) ────────────────────────────────────────────────


class TestFires:
    def test_list_fires_shape(self, client):
        """Frontend expects {fires: [...], count: N}."""
        mock_db.list_fires.return_value = [
            {
                "id": "abc-123",
                "heuristic_id": "h-456",
                "event_id": "e-789",
                "fired_at": datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc),
                "outcome": "success",
                "feedback_source": "user",
                "heuristic_name": "greeting-detector",
                "condition_text": "When someone says hello",
                "confidence": 0.85,
            }
        ]
        resp = client.get("/api/fires?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "fires" in data
        assert "count" in data
        assert data["count"] == 1

        fire = data["fires"][0]
        for key in ("id", "heuristic_id", "event_id", "fired_at",
                     "outcome", "feedback_source", "heuristic_name",
                     "condition_text", "confidence"):
            assert key in fire, f"Missing fire key: {key}"

    def test_list_fires_with_outcome_filter(self, client):
        mock_db.list_fires.return_value = []
        client.get("/api/fires?outcome=success&limit=25")
        mock_db.list_fires.assert_called_with(
            env_module.env.get_db_dsn(),
            limit=25,
            outcome="success",
        )

    def test_list_fires_db_error(self, client):
        """DB errors should return empty list, not 500."""
        mock_db.list_fires.side_effect = Exception("connection refused")
        resp = client.get("/api/fires")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fires"] == []
        assert "error" in data
        mock_db.list_fires.side_effect = None


# ─── LLM (HTTP-to-Ollama) ────────────────────────────────────────────────


class TestLLM:
    def test_status_not_configured(self, client):
        """No OLLAMA_URL → not_configured."""
        with patch("fun_api.routers.llm._get_ollama_config",
                    return_value={"endpoint": None, "url": "", "model": ""}):
            resp = client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_configured"
        assert "loaded_models" in data

    def test_status_connected_shape(self, client):
        """Frontend expects: status, url, model, available_models, loaded_models."""
        with patch("fun_api.routers.llm._get_ollama_config",
                    return_value={"endpoint": "local", "url": "http://localhost:11434",
                                  "model": "qwen2.5:3b"}):
            with patch("fun_api.routers.llm._ollama_request") as mock_req:
                # First call: /api/tags
                mock_req.side_effect = [
                    (200, {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3:8b"}]}),
                    (200, {"models": [{"name": "qwen2.5:3b"}]}),  # /api/ps
                ]
                resp = client.get("/api/llm/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert "url" in data
        assert "model" in data
        assert isinstance(data["available_models"], list)
        assert isinstance(data["loaded_models"], list)
        assert "qwen2.5:3b" in data["available_models"]
        assert "qwen2.5:3b" in data["loaded_models"]

    def test_test_prompt_shape(self, client):
        """Frontend expects: response, total_duration_ms."""
        with patch("fun_api.routers.llm._get_ollama_config",
                    return_value={"endpoint": None, "url": "http://localhost:11434",
                                  "model": "qwen2.5:3b"}):
            with patch("fun_api.routers.llm._ollama_request",
                        return_value=(200, {"response": "Hello!", "total_duration": 500_000_000})):
                resp = client.post("/api/llm/test",
                                   json={"prompt": "Say hi"})
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "total_duration_ms" in data
        assert data["response"] == "Hello!"
        assert data["total_duration_ms"] == 500.0

    def test_warm_shape(self, client):
        """Frontend expects: success, model."""
        with patch("fun_api.routers.llm._get_ollama_config",
                    return_value={"endpoint": None, "url": "http://localhost:11434",
                                  "model": "qwen2.5:3b"}):
            with patch("fun_api.routers.llm._ollama_request",
                        return_value=(200, {})):
                resp = client.post("/api/llm/warm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "model" in data


# ─── Events (submit, batch, queue) ────────────────────────────────────


class TestEvents:
    def test_submit_event_no_stub(self, client):
        """Submit without orchestrator returns 503."""
        resp = client.post("/api/events",
                           data={"source": "minecraft", "text": "test event"})
        assert resp.status_code == 503

    def test_submit_event_empty_text(self, client):
        resp = client.post("/api/events", data={"source": "minecraft", "text": ""})
        assert resp.status_code == 400
        assert "required" in resp.text.lower()

    def test_batch_not_list(self, client):
        resp = client.post("/api/events/batch",
                           json={"source": "test", "text": "hello"})
        assert resp.status_code == 400
        assert "array" in resp.json()["error"].lower()

    def test_batch_exceeds_cap(self, client):
        events = [{"source": "test", "text": f"event {i}"} for i in range(51)]
        resp = client.post("/api/events/batch", json=events)
        assert resp.status_code == 400
        assert "50" in resp.json()["error"]

    def test_batch_missing_text(self, client):
        resp = client.post("/api/events/batch",
                           json=[{"source": "test"}])
        assert resp.status_code == 400
        assert "validation" in resp.json()["error"].lower()

    def test_batch_no_stub(self, client):
        """Valid batch but no orchestrator returns 503."""
        resp = client.post("/api/events/batch",
                           json=[{"source": "test", "text": "hello"}])
        assert resp.status_code == 503

    def test_queue_no_stub(self, client):
        resp = client.get("/api/queue")
        assert resp.status_code == 503

    def test_queue_rows_no_stub(self, client):
        """Queue rows gracefully returns empty HTML when no stub."""
        resp = client.get("/api/queue/rows")
        assert resp.status_code == 200
        assert resp.text == ""

    def test_event_list_grpc_unavailable(self, client):
        """Event list with no memory stub returns 200 with empty template."""
        resp = client.get("/api/events")
        assert resp.status_code == 200
        # Should render the lab template even with empty events
        assert "lab-tab" in resp.text

    def test_event_rows_grpc_unavailable(self, client):
        """Event rows without memory stub returns empty HTML."""
        resp = client.get("/api/events/rows?limit=10&offset=0")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    def test_delete_event(self, client):
        mock_db.delete_event.return_value = True
        resp = client.delete("/api/events/abc-123")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "abc-123"

    def test_delete_event_not_found(self, client):
        mock_db.delete_event.return_value = False
        resp = client.delete("/api/events/nonexistent")
        assert resp.status_code == 404

    def test_delete_all_events(self, client):
        mock_db.delete_all_events.return_value = 15
        resp = client.delete("/api/events")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 15


# ─── Feedback ─────────────────────────────────────────────────────────────


class TestFeedback:
    """Feedback endpoint must forward response_id to executive."""

    def _mock_executive_stub(self):
        stub = MagicMock()
        mock_resp = MagicMock()
        mock_resp.created_heuristic_id = ""
        mock_resp.error_message = ""
        stub.ProvideFeedback = AsyncMock(return_value=mock_resp)
        return stub

    def _patch_executive_proto(self):
        """Inject mock executive_pb2 into events module (skipped by PROTOS_AVAILABLE=False)."""
        import backend.routers.events as events_mod
        return patch.object(events_mod, "executive_pb2", create=True, new=MagicMock())

    def test_feedback_forwards_response_id(self, client):
        """response_id from request body must appear in ProvideFeedbackRequest."""
        stub = self._mock_executive_stub()

        with patch.object(env_module.env, "executive_stub", return_value=stub):
            with self._patch_executive_proto() as mock_exec_pb2:
                resp = client.post("/api/feedback",
                                   json={"event_id": "evt-123",
                                         "response_id": "resp-456",
                                         "feedback": "good"})

        assert resp.status_code == 200
        mock_exec_pb2.ProvideFeedbackRequest.assert_called_once_with(
            event_id="evt-123",
            positive=True,
            response_id="resp-456",
        )

    def test_feedback_forwards_response_id_negative(self, client):
        """Negative feedback sets positive=False."""
        stub = self._mock_executive_stub()

        with patch.object(env_module.env, "executive_stub", return_value=stub):
            with self._patch_executive_proto() as mock_exec_pb2:
                resp = client.post("/api/feedback",
                                   json={"event_id": "evt-123",
                                         "response_id": "resp-789",
                                         "feedback": "bad"})

        assert resp.status_code == 200
        mock_exec_pb2.ProvideFeedbackRequest.assert_called_once_with(
            event_id="evt-123",
            positive=False,
            response_id="resp-789",
        )

    def test_feedback_missing_response_id_sends_empty(self, client):
        """When response_id is absent, empty string is forwarded (not omitted)."""
        stub = self._mock_executive_stub()

        with patch.object(env_module.env, "executive_stub", return_value=stub):
            with self._patch_executive_proto() as mock_exec_pb2:
                resp = client.post("/api/feedback",
                                   json={"event_id": "evt-123",
                                         "feedback": "good"})

        assert resp.status_code == 200
        mock_exec_pb2.ProvideFeedbackRequest.assert_called_once_with(
            event_id="evt-123",
            positive=True,
            response_id="",
        )

    def test_feedback_no_event_id_returns_400(self, client):
        resp = client.post("/api/feedback",
                           json={"feedback": "good"})
        assert resp.status_code == 400

    def test_feedback_no_stub_returns_503(self, client):
        with patch.object(env_module.env, "executive_stub", return_value=None):
            resp = client.post("/api/feedback",
                               json={"event_id": "evt-123", "feedback": "good"})
        assert resp.status_code == 503


# ─── Component routes (template rendering) ───────────────────────────────


class TestComponents:
    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "GLADyS Dashboard" in resp.text

    def test_heuristics_component(self, client):
        resp = client.get("/api/components/heuristics")
        assert resp.status_code == 200
        # Check for Alpine data binding which should be present
        assert "x-data" in resp.text

    def test_response_component(self, client):
        resp = client.get("/api/components/response")
        assert resp.status_code == 200
        assert "response-rows" in resp.text

    def test_learning_component(self, client):
        resp = client.get("/api/components/learning")
        assert resp.status_code == 200
        assert "learning-tab" in resp.text

    def test_llm_component(self, client):
        resp = client.get("/api/components/llm")
        assert resp.status_code == 200
        assert "llm-tab" in resp.text

    def test_logs_component(self, client):
        resp = client.get("/api/components/logs")
        assert resp.status_code == 200
        assert "logs-tab" in resp.text

    def test_settings_component(self, client):
        resp = client.get("/api/components/settings")
        assert resp.status_code == 200
        assert "settings-tab" in resp.text

    def test_invalid_component_raises(self, client):
        from jinja2.exceptions import TemplateNotFound
        with pytest.raises(TemplateNotFound):
            client.get("/api/components/nonexistent")


# ─── Static files ────────────────────────────────────────────────────────


class TestStaticFiles:
    def test_css_served(self, client):
        resp = client.get("/css/style.css")
        assert resp.status_code == 200
        assert "bg-dark" in resp.text

    def test_js_app_served(self, client):
        resp = client.get("/js/app.js")
        assert resp.status_code == 200
