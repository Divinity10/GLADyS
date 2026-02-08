"""Tests for gladys_client.orchestrator library functions (publish_event, load_fixture)."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock gRPC protos before any imports that use them
mock_protos = MagicMock()
sys.modules.setdefault("grpc", MagicMock())
sys.modules.setdefault("gladys_orchestrator", mock_protos)
sys.modules.setdefault("gladys_orchestrator.generated", mock_protos.generated)
sys.modules.setdefault("gladys_orchestrator.generated.common_pb2", mock_protos.generated.common_pb2)
sys.modules.setdefault("gladys_orchestrator.generated.orchestrator_pb2", mock_protos.generated.orchestrator_pb2)
sys.modules.setdefault("gladys_orchestrator.generated.orchestrator_pb2_grpc", mock_protos.generated.orchestrator_pb2_grpc)

# Add gladys_client to path (after mocks so proto imports resolve to mocks)
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_client"))

from gladys_client import orchestrator as _orchestrator


class TestPublishEvent:
    def test_returns_event_id_on_success(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "abc-123"
        ack.queued = True
        stub.PublishEvent.return_value = MagicMock(ack=ack)

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert result["event_id"] == "abc-123"
        assert result["status"] == "queued"

    def test_immediate_path(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "abc-123"
        ack.queued = False
        stub.PublishEvent.return_value = MagicMock(ack=ack)

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert result["status"] == "immediate"

    def test_grpc_error_returns_error_dict(self):
        stub = MagicMock()
        # grpc is mocked in this test module, so create a real exception
        # that the client code's except handler will catch
        error = type("RpcError", (Exception,), {})()
        error.code = MagicMock(return_value=MagicMock(name="UNAVAILABLE"))
        # Patch grpc.RpcError to match the exception type
        _orchestrator.grpc.RpcError = type(error)
        stub.PublishEvent.side_effect = error

        result = _orchestrator.publish_event(stub, "abc-123", "test", "hello")
        assert "error" in result
        assert result["event_id"] == "abc-123"

class TestLoadFixture:
    def test_loads_and_publishes_events(self):
        stub = MagicMock()
        ack = MagicMock()
        ack.event_id = "test-id"
        ack.queued = True
        stub.PublishEvent.return_value = MagicMock(ack=ack)

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
            assert stub.PublishEvent.call_count == 2
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
        stub.PublishEvent.return_value = MagicMock(ack=ack)

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
        stub.PublishEvent.return_value = MagicMock(ack=ack)

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
