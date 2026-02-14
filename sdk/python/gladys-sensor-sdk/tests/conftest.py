"""Shared test fixtures for sensor SDK tests."""

from __future__ import annotations

import asyncio
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
from gladys_sensor_sdk.testing import TestSensorHarness


class MockDriver:
    """Mock driver for testing sensors."""

    def __init__(self) -> None:
        self.connected = False
        self.paused = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def ping(self) -> bool:
        return self.connected

    async def restart(self) -> None:
        await self.disconnect()
        await self.connect()


class SimpleSensor(AdapterBase):
    """Simple test sensor implementing all handlers."""

    def __init__(
        self,
        component_id: str = "test-sensor",
        orchestrator_address: str = "",
        timeout_config: Optional[TimeoutConfig] = None,
    ) -> None:
        super().__init__(
            component_id=component_id,
            component_type="sensor.test",
            orchestrator_address=orchestrator_address,
            timeout_config=timeout_config or TimeoutConfig.no_timeout(),
        )
        self.driver = MockDriver()
        self.paused = False
        self.dry_run_mode = False
        self.config: dict = {}
        self.capture_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    async def handle_start(self, args: StartArgs) -> Optional[ComponentState]:
        self.dry_run_mode = args.dry_run
        await self.driver.connect()
        return None

    async def handle_stop(self, args: StopArgs) -> Optional[ComponentState]:
        if self.capture_task:
            self.capture_task.cancel()
            try:
                await self.capture_task
            except asyncio.CancelledError:
                pass
        await self.driver.disconnect()
        return None

    async def handle_pause(self) -> Optional[ComponentState]:
        self.paused = True
        return None

    async def handle_resume(self) -> Optional[ComponentState]:
        self.paused = False
        return None

    async def handle_reload(self) -> Optional[ComponentState]:
        return None

    async def handle_health_check(
        self, args: HealthCheckArgs
    ) -> Optional[ComponentState]:
        if args.deep:
            if not await self.driver.ping():
                raise RuntimeError("Driver not responding")
        return None

    async def handle_recover(
        self, args: RecoverArgs
    ) -> Optional[ComponentState]:
        await self.driver.restart()
        return None


@pytest.fixture
def sensor() -> SimpleSensor:
    """Create a SimpleSensor instance."""
    return SimpleSensor()


@pytest.fixture
def harness(sensor: SimpleSensor) -> TestSensorHarness:
    """Create a TestSensorHarness wrapping a SimpleSensor."""
    return TestSensorHarness(sensor)
