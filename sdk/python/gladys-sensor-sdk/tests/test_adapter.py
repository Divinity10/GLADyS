"""Tests for AdapterBase using SensorTestHarness."""

from __future__ import annotations

from typing import Optional

import pytest

from gladys_sensor_sdk import (
    AdapterBase,
    ComponentState,
    HealthCheckArgs,
    RecoverArgs,
    StartArgs,
    StopArgs,
    TimeoutConfig,
)
from gladys_sensor_sdk.state import Command
from gladys_sensor_sdk.testing import SensorTestHarness


class MinimalSensor(AdapterBase):
    """Sensor that uses all default handlers (no overrides)."""

    def __init__(self) -> None:
        super().__init__(
            component_id="minimal",
            component_type="sensor.minimal",
            orchestrator_address="",
            timeout_config=TimeoutConfig.no_timeout(),
        )


class OverrideSensor(AdapterBase):
    """Sensor that overrides start to return explicit state."""

    def __init__(self) -> None:
        super().__init__(
            component_id="override",
            component_type="sensor.override",
            orchestrator_address="",
            timeout_config=TimeoutConfig.no_timeout(),
        )

    async def handle_start(
        self, args: StartArgs
    ) -> Optional[ComponentState]:
        return ComponentState.STARTING  # Override default ACTIVE


class FailingSensor(AdapterBase):
    """Sensor whose start handler always fails."""

    def __init__(self) -> None:
        super().__init__(
            component_id="failing",
            component_type="sensor.failing",
            orchestrator_address="",
            timeout_config=TimeoutConfig.no_timeout(),
        )

    async def handle_start(
        self, args: StartArgs
    ) -> Optional[ComponentState]:
        raise RuntimeError("Always fails")


class CustomErrorSensor(AdapterBase):
    """Sensor with custom error handler."""

    def __init__(self) -> None:
        super().__init__(
            component_id="custom-error",
            component_type="sensor.custom_error",
            orchestrator_address="",
            timeout_config=TimeoutConfig.no_timeout(),
        )

    async def handle_start(
        self, args: StartArgs
    ) -> Optional[ComponentState]:
        raise RuntimeError("Custom error")

    async def on_command_error(
        self,
        command: Command,
        exception: Exception,
        current_state: ComponentState,
    ) -> Optional[ComponentState]:
        # Custom error handling: transition to STOPPED instead of ERROR
        return ComponentState.STOPPED


class TestMinimalSensor:
    """Test that default handlers produce correct state transitions."""

    @pytest.fixture
    def harness(self) -> SensorTestHarness:
        return SensorTestHarness(MinimalSensor())

    @pytest.mark.asyncio
    async def test_default_start(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_start()
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_default_stop(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_stop()
        assert state == ComponentState.STOPPED
        assert error is None

    @pytest.mark.asyncio
    async def test_default_pause(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_pause()
        assert state == ComponentState.PAUSED
        assert error is None

    @pytest.mark.asyncio
    async def test_default_resume(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_resume()
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_default_reload(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_reload()
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_default_health_check(
        self, harness: SensorTestHarness
    ) -> None:
        harness.set_state(ComponentState.ACTIVE)
        state, error = await harness.dispatch_health_check()
        assert state == ComponentState.ACTIVE  # Unchanged
        assert error is None

    @pytest.mark.asyncio
    async def test_default_recover(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_recover()
        assert state == ComponentState.ACTIVE
        assert error is None


class TestOverrideSensor:
    """Test handler state override."""

    @pytest.mark.asyncio
    async def test_handler_can_override_default_state(self) -> None:
        harness = SensorTestHarness(OverrideSensor())
        state, error = await harness.dispatch_start()
        assert state == ComponentState.STARTING  # Not default ACTIVE
        assert error is None


class TestFailingSensor:
    """Test error handling on handler failure."""

    @pytest.mark.asyncio
    async def test_handler_failure_sets_error(self) -> None:
        harness = SensorTestHarness(FailingSensor())
        state, error = await harness.dispatch_start()
        assert state == ComponentState.ERROR
        assert error is not None
        assert "Always fails" in error


class TestCustomErrorSensor:
    """Test custom error handler override."""

    @pytest.mark.asyncio
    async def test_custom_error_handler_overrides_state(self) -> None:
        harness = SensorTestHarness(CustomErrorSensor())
        state, error = await harness.dispatch_start()
        assert state == ComponentState.STOPPED  # Custom override
        assert error is not None
        assert "Custom error" in error


class TestAdapterRegistersAllHandlers:
    """Verify all 7 commands are registered."""

    def test_all_commands_registered(self) -> None:
        sensor = MinimalSensor()
        dispatcher = sensor._dispatcher

        for cmd in [
            Command.START,
            Command.STOP,
            Command.PAUSE,
            Command.RESUME,
            Command.RELOAD,
            Command.HEALTH_CHECK,
            Command.RECOVER,
        ]:
            assert cmd in dispatcher._handlers, f"{cmd.name} not registered"

    def test_error_handler_registered(self) -> None:
        sensor = MinimalSensor()
        assert sensor._dispatcher._error_handler is not None
