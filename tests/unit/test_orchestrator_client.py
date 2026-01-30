"""Tests for _orchestrator.py library functions (publish_event, load_fixture)."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add scripts and orchestrator to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "orchestrator"))

# Mock gRPC protos before import
mock_protos = MagicMock()
sys.modules.setdefault("grpc", MagicMock())
sys.modules.setdefault("gladys_orchestrator", mock_protos)
sys.modules.setdefault("gladys_orchestrator.generated", mock_protos.generated)
sys.modules.setdefault("gladys_orchestrator.generated.common_pb2", mock_protos.generated.common_pb2)
sys.modules.setdefault("gladys_orchestrator.generated.orchestrator_pb2", mock_protos.generated.orchestrator_pb2)
sys.modules.setdefault("gladys_orchestrator.generated.orchestrator_pb2_grpc", mock_protos.generated.orchestrator_pb2_grpc)

import _orchestrator


class TestPublishEvent:
    def test_returns_event_id_on_success(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "abc-123"
        ack.queued = True
        stub.PublishEvents.return_value = iter([ack])

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert result["event_id"] == "abc-123"
        assert result["status"] == "queued"

    def test_immediate_path(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "abc-123"
        ack.queued = False
        stub.PublishEvents.return_value = iter([ack])

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert result["status"] == "immediate"

    def test_grpc_error_returns_error_dict(self):
        stub = MagicMock()
        import grpc as grpc_mod
        error = grpc_mod.RpcError()
        error.code = MagicMock(return_value=MagicMock(name="UNAVAILABLE"))
        stub.PublishEvents.side_effect = error

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert "error" in result
        assert result["event_id"] == "abc-123"

    def test_no_ack_returns_error(self):
        stub = MagicMock()
        stub.PublishEvents.return_value = iter([])

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert result == {"event_id": "abc-123", "error": "no_ack"}


class TestLoadFixture:
    def test_loads_and_publishes_events(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "test-id"
        ack.queued = True
        stub.PublishEvents.return_value = iter([ack])

        events = [
            {"source": "minecraft", "text": "Player joined"},
            {"source": "kitchen", "text": "Oven on"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            json.dump(events, f)
            f.flush()
            path = f.name

        try:
            results = _orchestrator.load_fixture(stub, path)
            assert len(results) == 2
            assert stub.PublishEvents.call_count == 2
        finally:
            Path(path).unlink()

    def test_invalid_json_raises(self):
        stub = MagicMock()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            f.write('{"not": "a list"}')
            f.flush()
            path = f.name

        try:
            with pytest.raises(ValueError, match="JSON array"):
                _orchestrator.load_fixture(stub, path)
        finally:
            Path(path).unlink()

    def test_uses_provided_ids(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "custom-id"
        ack.queued = True
        stub.PublishEvents.return_value = iter([ack])

        events = [{"source": "test", "text": "hello", "id": "custom-id"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            json.dump(events, f)
            f.flush()
            path = f.name

        try:
            Event = _orchestrator.common_pb2.Event
            Event.reset_mock()
            _orchestrator.load_fixture(stub, path)
            # Verify Event was constructed with the custom ID
            Event.assert_called_once_with(id="custom-id", source="test", raw_text="hello")
        finally:
            Path(path).unlink()

    def test_generates_ids_when_missing(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "generated"
        ack.queued = True
        stub.PublishEvents.return_value = iter([ack])

        events = [{"source": "test", "text": "hello"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            json.dump(events, f)
            f.flush()
            path = f.name

        try:
            Event = _orchestrator.common_pb2.Event
            Event.reset_mock()
            _orchestrator.load_fixture(stub, path)
            # Verify Event was called with a UUID-length id
            call_kwargs = Event.call_args[1]
            assert len(call_kwargs["id"]) == 36  # UUID format
        finally:
            Path(path).unlink()
