"""Tests for SensorTestHarness using the SimpleSensor from conftest."""

from __future__ import annotations

import pytest

from gladys_sensor_sdk import (
    ComponentState,
    HealthCheckArgs,
    RecoverArgs,
    StartArgs,
    StopArgs,
)
from gladys_sensor_sdk.testing import SensorTestHarness


class TestHarnessStartCommand:
    """Test harness START command dispatch."""

    @pytest.mark.asyncio
    async def test_start_sets_active(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_start(StartArgs.test_defaults())
        assert state == ComponentState.ACTIVE
        assert error is None
        assert harness.adapter.driver.connected is True  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_start_dry_run(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_start(StartArgs.test_dry_run())
        assert state == ComponentState.ACTIVE
        assert harness.adapter.dry_run_mode is True  # type: ignore[attr-defined]


class TestHarnessStopCommand:
    """Test harness STOP command dispatch."""

    @pytest.mark.asyncio
    async def test_stop_disconnects(
        self, harness: SensorTestHarness
    ) -> None:
        await harness.dispatch_start()
        state, error = await harness.dispatch_stop(StopArgs.test_defaults())
        assert state == ComponentState.STOPPED
        assert harness.adapter.driver.connected is False  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_stop_force(self, harness: SensorTestHarness) -> None:
        await harness.dispatch_start()
        state, error = await harness.dispatch_stop(StopArgs.test_force())
        assert state == ComponentState.STOPPED


class TestHarnessPauseResumeReload:
    """Test harness PAUSE/RESUME/RELOAD commands."""

    @pytest.mark.asyncio
    async def test_pause(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_pause()
        assert state == ComponentState.PAUSED

    @pytest.mark.asyncio
    async def test_resume(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_resume()
        assert state == ComponentState.ACTIVE

    @pytest.mark.asyncio
    async def test_reload(self, harness: SensorTestHarness) -> None:
        state, error = await harness.dispatch_reload()
        assert state == ComponentState.ACTIVE


class TestHarnessHealthCheck:
    """Test harness HEALTH_CHECK command."""

    @pytest.mark.asyncio
    async def test_health_check_passes(
        self, harness: SensorTestHarness
    ) -> None:
        harness.set_state(ComponentState.ACTIVE)
        state, error = await harness.dispatch_health_check()
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_health_check_failure_preserves_state(
        self, harness: SensorTestHarness
    ) -> None:
        """HEALTH_CHECK failure does NOT set ERROR state."""
        harness.set_state(ComponentState.ACTIVE)

        # Mock driver to fail health check
        async def fail_ping() -> bool:
            raise RuntimeError("Driver not responding")

        harness.adapter.driver.ping = fail_ping  # type: ignore[attr-defined]

        state, error = await harness.dispatch_health_check(
            HealthCheckArgs.test_deep()
        )

        # State unchanged (still ACTIVE, NOT ERROR)
        assert state == ComponentState.ACTIVE
        assert error is not None
        assert "Driver not responding" in error


class TestHarnessRecover:
    """Test harness RECOVER command."""

    @pytest.mark.asyncio
    async def test_recover_restarts_driver(
        self, harness: SensorTestHarness
    ) -> None:
        await harness.dispatch_start()
        harness.adapter.driver.connected = False  # type: ignore[attr-defined]

        state, error = await harness.dispatch_recover(
            RecoverArgs.test_defaults()
        )

        assert state == ComponentState.ACTIVE
        assert error is None
        assert harness.adapter.driver.connected is True  # type: ignore[attr-defined]


class TestHarnessHandlerError:
    """Test harness error handling."""

    @pytest.mark.asyncio
    async def test_handler_error_sets_error_state(
        self, harness: SensorTestHarness
    ) -> None:
        # Mock driver to fail on connect
        async def fail_connect() -> None:
            raise RuntimeError("Connection failed")

        harness.adapter.driver.connect = fail_connect  # type: ignore[attr-defined]

        state, error = await harness.dispatch_start()

        assert state == ComponentState.ERROR
        assert error is not None
        assert "Connection failed" in error


class TestHarnessStateManagement:
    """Test harness state get/set."""

    def test_get_state_initial(self, harness: SensorTestHarness) -> None:
        assert harness.get_state() == ComponentState.UNKNOWN

    def test_set_state(self, harness: SensorTestHarness) -> None:
        harness.set_state(ComponentState.ACTIVE)
        assert harness.get_state() == ComponentState.ACTIVE

    @pytest.mark.asyncio
    async def test_state_tracks_through_commands(
        self, harness: SensorTestHarness
    ) -> None:
        assert harness.get_state() == ComponentState.UNKNOWN

        await harness.dispatch_start()
        assert harness.get_state() == ComponentState.ACTIVE

        await harness.dispatch_pause()
        assert harness.get_state() == ComponentState.PAUSED

        await harness.dispatch_resume()
        assert harness.get_state() == ComponentState.ACTIVE

        await harness.dispatch_stop()
        assert harness.get_state() == ComponentState.STOPPED


class TestHarnessDefaultArgs:
    """Test that dispatch methods work without explicit args."""

    @pytest.mark.asyncio
    async def test_dispatch_start_no_args(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_start()
        assert state == ComponentState.ACTIVE

    @pytest.mark.asyncio
    async def test_dispatch_stop_no_args(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_stop()
        assert state == ComponentState.STOPPED

    @pytest.mark.asyncio
    async def test_dispatch_health_check_no_args(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_health_check()
        assert error is None

    @pytest.mark.asyncio
    async def test_dispatch_recover_no_args(
        self, harness: SensorTestHarness
    ) -> None:
        state, error = await harness.dispatch_recover()
        assert state == ComponentState.ACTIVE
