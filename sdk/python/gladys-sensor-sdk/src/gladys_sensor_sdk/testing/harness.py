"""Test harness for sensor adapters.

Bypasses heartbeat/gRPC, dispatches commands directly.
Use in unit tests to validate command handlers.

Example::

    harness = SensorTestHarness(MySensorAdapter(
        component_id="test-sensor",
        component_type="sensor.test",
        orchestrator_address="",  # Not used
        timeout_config=TimeoutConfig.no_timeout()
    ))

    state, error = await harness.dispatch_start(StartArgs.test_defaults())
    assert state == ComponentState.ACTIVE
"""

from __future__ import annotations

from typing import Optional

from ..adapter import AdapterBase
from ..args import HealthCheckArgs, RecoverArgs, StartArgs, StopArgs
from ..state import Command, ComponentState


class SensorTestHarness:
    """Test harness for sensor adapters.

    Bypasses heartbeat/gRPC, dispatches commands directly.
    Use in unit tests to validate command handlers.
    """

    def __init__(self, adapter: AdapterBase) -> None:
        """Initialize harness with adapter instance.

        Args:
            adapter: Sensor adapter to test.
        """
        self.adapter = adapter
        self.dispatcher = adapter._dispatcher

    async def dispatch_start(
        self,
        args: Optional[StartArgs] = None,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch START command directly.

        Args:
            args: StartArgs (default: StartArgs.test_defaults()).

        Returns:
            (new_state, error_message) tuple.
        """
        if args is None:
            args = StartArgs.test_defaults()

        args_dict = {
            "dry_run": args.dry_run,
        }

        return await self.dispatcher.dispatch(Command.START, args_dict)

    async def dispatch_stop(
        self,
        args: Optional[StopArgs] = None,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch STOP command directly.

        Args:
            args: StopArgs (default: StopArgs.test_defaults()).

        Returns:
            (new_state, error_message) tuple.
        """
        if args is None:
            args = StopArgs.test_defaults()

        args_dict = {
            "force": args.force,
            "timeout_ms": args.timeout_ms,
        }

        return await self.dispatcher.dispatch(Command.STOP, args_dict)

    async def dispatch_pause(
        self,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch PAUSE command directly."""
        return await self.dispatcher.dispatch(Command.PAUSE)

    async def dispatch_resume(
        self,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch RESUME command directly."""
        return await self.dispatcher.dispatch(Command.RESUME)

    async def dispatch_reload(
        self,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch RELOAD command directly."""
        return await self.dispatcher.dispatch(Command.RELOAD)

    async def dispatch_health_check(
        self,
        args: Optional[HealthCheckArgs] = None,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch HEALTH_CHECK command directly.

        Args:
            args: HealthCheckArgs (default: HealthCheckArgs.test_defaults()).

        Returns:
            (new_state, error_message) tuple.
        """
        if args is None:
            args = HealthCheckArgs.test_defaults()

        args_dict = {
            "deep": args.deep,
        }

        return await self.dispatcher.dispatch(Command.HEALTH_CHECK, args_dict)

    async def dispatch_recover(
        self,
        args: Optional[RecoverArgs] = None,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch RECOVER command directly.

        Args:
            args: RecoverArgs (default: RecoverArgs.test_defaults()).

        Returns:
            (new_state, error_message) tuple.
        """
        if args is None:
            args = RecoverArgs.test_defaults()

        args_dict = {"strategy": args.strategy}

        return await self.dispatcher.dispatch(Command.RECOVER, args_dict)

    def get_state(self) -> ComponentState:
        """Get current component state."""
        return self.dispatcher.current_state

    def set_state(self, state: ComponentState) -> None:
        """Set component state (for test setup)."""
        self.dispatcher.current_state = state
