"""Tests for the ComponentRegistry."""

import pytest

from gladys_orchestrator.registry import ComponentRegistry


class TestComponentRegistry:
    """Test cases for ComponentRegistry."""

    def test_register_component(self):
        """Components can be registered."""
        registry = ComponentRegistry()

        result = registry.register(
            component_id="sensor-1",
            component_type="sensor",
            address="localhost:50001",
            capabilities=None,
        )

        assert result["success"] is True
        assert result["assigned_id"] == "sensor-1"
        assert registry.component_count == 1

    def test_unregister_component(self):
        """Components can be unregistered."""
        registry = ComponentRegistry()
        registry.register("sensor-1", "sensor", "localhost:50001", None)

        success = registry.unregister("sensor-1")

        assert success is True
        assert registry.component_count == 0

    def test_unregister_unknown_returns_false(self):
        """Unregistering unknown component returns False."""
        registry = ComponentRegistry()

        success = registry.unregister("nonexistent")

        assert success is False

    def test_get_by_id(self):
        """Components can be retrieved by ID."""
        registry = ComponentRegistry()
        registry.register("sensor-1", "sensor", "localhost:50001", None)

        info = registry.get_by_id("sensor-1")

        assert info is not None
        assert info.component_id == "sensor-1"
        assert info.address == "localhost:50001"

    def test_get_by_type(self):
        """Components can be retrieved by type."""
        registry = ComponentRegistry()
        registry.register("sensor-1", "sensor", "localhost:50001", None)
        registry.register("sensor-2", "sensor", "localhost:50002", None)

        info = registry.get_by_type("sensor")

        assert info is not None
        assert info.component_type == "sensor"

    def test_heartbeat_updates_timestamp(self):
        """Heartbeat updates last_heartbeat_ms."""
        registry = ComponentRegistry()
        registry.register("sensor-1", "sensor", "localhost:50001", None)

        initial = registry.get_by_id("sensor-1").last_heartbeat_ms

        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.01)

        registry.update_heartbeat("sensor-1", state=2, metrics={"events": "100"})

        updated = registry.get_by_id("sensor-1").last_heartbeat_ms
        assert updated > initial

    def test_queue_and_get_pending_commands(self):
        """Commands can be queued and retrieved."""
        registry = ComponentRegistry()
        registry.register("sensor-1", "sensor", "localhost:50001", None)

        registry.queue_command("sensor-1", {"command_id": "cmd-1", "command": 1})

        pending = registry.get_pending_commands("sensor-1")

        assert len(pending) == 1
        assert pending[0]["command_id"] == "cmd-1"

        # Commands are cleared after retrieval
        pending_again = registry.get_pending_commands("sensor-1")
        assert len(pending_again) == 0
