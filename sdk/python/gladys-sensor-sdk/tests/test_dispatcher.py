"""Tests for CommandDispatcher (internal command routing)."""

from __future__ import annotations

from typing import Optional

import pytest

from gladys_sensor_sdk.args import HealthCheckArgs, StartArgs, StopArgs
from gladys_sensor_sdk.dispatcher import CommandDispatcher
from gladys_sensor_sdk.state import Command, ComponentState


@pytest.fixture
def dispatcher() -> CommandDispatcher:
    """Create a fresh CommandDispatcher."""
    return CommandDispatcher(component_id="test")


class TestDispatchDefaultTransitions:
    """Verify default state transitions for all commands."""

    @pytest.mark.asyncio
    async def test_start_transitions_to_active(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: StartArgs) -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.START, handler)
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_stop_transitions_to_stopped(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: StopArgs) -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.STOP, handler)
        state, error = await dispatcher.dispatch(Command.STOP, {})
        assert state == ComponentState.STOPPED
        assert error is None

    @pytest.mark.asyncio
    async def test_pause_transitions_to_paused(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler() -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.PAUSE, handler)
        state, error = await dispatcher.dispatch(Command.PAUSE)
        assert state == ComponentState.PAUSED
        assert error is None

    @pytest.mark.asyncio
    async def test_resume_transitions_to_active(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler() -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.RESUME, handler)
        state, error = await dispatcher.dispatch(Command.RESUME)
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_reload_transitions_to_active(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler() -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.RELOAD, handler)
        state, error = await dispatcher.dispatch(Command.RELOAD)
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_health_check_preserves_state(
        self, dispatcher: CommandDispatcher
    ) -> None:
        dispatcher.current_state = ComponentState.ACTIVE

        async def handler(args: HealthCheckArgs) -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.HEALTH_CHECK, handler)
        state, error = await dispatcher.dispatch(Command.HEALTH_CHECK, {})
        assert state == ComponentState.ACTIVE
        assert error is None

    @pytest.mark.asyncio
    async def test_recover_transitions_to_active(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: object) -> Optional[ComponentState]:
            return None

        dispatcher.register_handler(Command.RECOVER, handler)
        state, error = await dispatcher.dispatch(Command.RECOVER, {})
        assert state == ComponentState.ACTIVE
        assert error is None


class TestDispatchHandlerOverride:
    """Verify handler can override default state transitions."""

    @pytest.mark.asyncio
    async def test_handler_returns_explicit_state(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: StartArgs) -> Optional[ComponentState]:
            return ComponentState.STARTING  # Override default ACTIVE

        dispatcher.register_handler(Command.START, handler)
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.STARTING
        assert error is None


class TestDispatchErrorHandling:
    """Verify error handling behavior."""

    @pytest.mark.asyncio
    async def test_handler_exception_sets_error_state(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: StartArgs) -> Optional[ComponentState]:
            raise RuntimeError("Connection failed")

        dispatcher.register_handler(Command.START, handler)
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.ERROR
        assert error is not None
        assert "Connection failed" in error

    @pytest.mark.asyncio
    async def test_health_check_exception_preserves_state(
        self, dispatcher: CommandDispatcher
    ) -> None:
        """HEALTH_CHECK exception does NOT set ERROR state."""
        dispatcher.current_state = ComponentState.ACTIVE

        async def handler(args: HealthCheckArgs) -> Optional[ComponentState]:
            raise RuntimeError("Driver not responding")

        dispatcher.register_handler(Command.HEALTH_CHECK, handler)
        state, error = await dispatcher.dispatch(Command.HEALTH_CHECK, {})
        assert state == ComponentState.ACTIVE  # NOT ERROR
        assert error is not None
        assert "Driver not responding" in error

    @pytest.mark.asyncio
    async def test_error_handler_can_override_state(
        self, dispatcher: CommandDispatcher
    ) -> None:
        async def handler(args: StartArgs) -> Optional[ComponentState]:
            raise RuntimeError("fail")

        async def error_handler(
            cmd: Command, exc: Exception, current: ComponentState
        ) -> Optional[ComponentState]:
            return ComponentState.STOPPED  # Override ERROR

        dispatcher.register_handler(Command.START, handler)
        dispatcher.register_error_handler(error_handler)
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.STOPPED
        assert error is not None

    @pytest.mark.asyncio
    async def test_no_handler_returns_current_state_with_error(
        self, dispatcher: CommandDispatcher
    ) -> None:
        dispatcher.current_state = ComponentState.ACTIVE
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.ACTIVE
        assert error is not None
        assert "No handler" in error

    @pytest.mark.asyncio
    async def test_error_handler_exception_falls_back_to_default(
        self, dispatcher: CommandDispatcher
    ) -> None:
        """If error handler itself throws, fall back to default ERROR state."""

        async def handler(args: StartArgs) -> Optional[ComponentState]:
            raise RuntimeError("original")

        async def error_handler(
            cmd: Command, exc: Exception, current: ComponentState
        ) -> Optional[ComponentState]:
            raise RuntimeError("error handler also failed")

        dispatcher.register_handler(Command.START, handler)
        dispatcher.register_error_handler(error_handler)
        state, error = await dispatcher.dispatch(Command.START, {})
        assert state == ComponentState.ERROR
        assert "original" in error


class TestDispatchArgParsing:
    """Verify args are parsed correctly for each command type."""

    @pytest.mark.asyncio
    async def test_start_args_parsed(
        self, dispatcher: CommandDispatcher
    ) -> None:
        received_args = None

        async def handler(args: StartArgs) -> Optional[ComponentState]:
            nonlocal received_args
            received_args = args
            return None

        dispatcher.register_handler(Command.START, handler)
        await dispatcher.dispatch(Command.START, {"dry_run": True})
        assert received_args is not None
        assert received_args.dry_run is True

    @pytest.mark.asyncio
    async def test_stop_args_parsed(
        self, dispatcher: CommandDispatcher
    ) -> None:
        received_args = None

        async def handler(args: StopArgs) -> Optional[ComponentState]:
            nonlocal received_args
            received_args = args
            return None

        dispatcher.register_handler(Command.STOP, handler)
        await dispatcher.dispatch(
            Command.STOP, {"force": True, "timeout_ms": 1000}
        )
        assert received_args is not None
        assert received_args.force is True
        assert received_args.timeout_ms == 1000

    @pytest.mark.asyncio
    async def test_pause_has_no_args(
        self, dispatcher: CommandDispatcher
    ) -> None:
        called = False

        async def handler() -> Optional[ComponentState]:
            nonlocal called
            called = True
            return None

        dispatcher.register_handler(Command.PAUSE, handler)
        await dispatcher.dispatch(Command.PAUSE)
        assert called is True

    @pytest.mark.asyncio
    async def test_none_args_dict_gives_defaults(
        self, dispatcher: CommandDispatcher
    ) -> None:
        received_args = None

        async def handler(args: StartArgs) -> Optional[ComponentState]:
            nonlocal received_args
            received_args = args
            return None

        dispatcher.register_handler(Command.START, handler)
        await dispatcher.dispatch(Command.START, None)
        assert received_args is not None
        assert received_args.dry_run is False
