"""Internal command dispatcher.

Routes incoming commands to registered handlers and manages state transitions.
Composed by SensorLifecycle. Not exposed to sensor developers directly.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from .args import (
    CommandArgs,
    HealthCheckArgs,
    RecoverArgs,
    StartArgs,
    StopArgs,
)
from .state import Command, ComponentState

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Internal command router.

    Routes incoming commands to registered handlers and manages state
    transitions. Composed by SensorLifecycle.
    """

    def __init__(self, component_id: str) -> None:
        self.component_id = component_id
        self.current_state = ComponentState.UNKNOWN

        # Handler registry
        self._handlers: dict[Command, Callable[..., Awaitable[Optional[ComponentState]]]] = {}
        self._error_handler: Optional[
            Callable[
                [Command, Exception, ComponentState],
                Awaitable[Optional[ComponentState]],
            ]
        ] = None

        # Default state transitions
        self._default_transitions: dict[Command, Optional[ComponentState]] = {
            Command.START: ComponentState.ACTIVE,
            Command.STOP: ComponentState.STOPPED,
            Command.PAUSE: ComponentState.PAUSED,
            Command.RESUME: ComponentState.ACTIVE,
            Command.RELOAD: ComponentState.ACTIVE,
            Command.HEALTH_CHECK: None,  # No state change
            Command.RECOVER: ComponentState.ACTIVE,
        }

    def register_handler(
        self,
        command: Command,
        handler: Callable[..., Awaitable[Optional[ComponentState]]],
    ) -> None:
        """Register command handler.

        Args:
            command: Command enum value.
            handler: Async handler function (returns ComponentState or None).
        """
        self._handlers[command] = handler

    def register_error_handler(
        self,
        handler: Callable[
            [Command, Exception, ComponentState],
            Awaitable[Optional[ComponentState]],
        ],
    ) -> None:
        """Register global error handler.

        Args:
            handler: Async error handler (cmd, exception, current_state) -> ComponentState?
        """
        self._error_handler = handler

    async def dispatch(
        self,
        command: Command,
        args_dict: Optional[dict[str, Any]] = None,
    ) -> tuple[ComponentState, Optional[str]]:
        """Dispatch command to registered handler.

        Args:
            command: Command to execute.
            args_dict: Command arguments as a dict.

        Returns:
            (new_state, error_message) tuple.
        """
        handler = self._handlers.get(command)
        if not handler:
            logger.warning("No handler for command %s", command.name)
            return (self.current_state, f"No handler for {command.name}")

        # Parse args based on command type
        parsed_args = self._parse_args(command, args_dict)

        try:
            # Call handler
            if parsed_args is not None:
                result_state = await handler(parsed_args)
            else:
                # PAUSE/RESUME/RELOAD have no args parameter
                result_state = await handler()

            # Determine new state
            if result_state is not None:
                # Handler overrode default state
                new_state = result_state
            else:
                # Use default transition
                default = self._default_transitions.get(command)
                new_state = default if default is not None else self.current_state

            self.current_state = new_state
            return (new_state, None)

        except Exception as e:
            logger.error("Command %s failed: %s", command.name, e, exc_info=True)

            # Call error handler if registered
            if self._error_handler:
                try:
                    error_result = await self._error_handler(
                        command, e, self.current_state
                    )
                    if error_result is not None:
                        # Error handler overrode state
                        self.current_state = error_result
                        return (error_result, str(e))
                except Exception as handler_error:
                    logger.error(
                        "Error handler failed: %s",
                        handler_error,
                        exc_info=True,
                    )

            # Default error handling
            if command == Command.HEALTH_CHECK:
                # Health check failure does NOT set ERROR state
                return (self.current_state, str(e))
            else:
                # All other failures set ERROR state
                self.current_state = ComponentState.ERROR
                return (ComponentState.ERROR, str(e))

    def _parse_args(
        self,
        command: Command,
        args_dict: Optional[dict[str, Any]],
    ) -> Optional[CommandArgs]:
        """Parse args based on command type.

        Returns None for commands with no args parameter (PAUSE/RESUME/RELOAD).
        """
        if args_dict is None:
            args_dict = {}

        if command == Command.START:
            return StartArgs.from_dict(args_dict)
        elif command == Command.STOP:
            return StopArgs.from_dict(args_dict)
        elif command == Command.RECOVER:
            return RecoverArgs.from_dict(args_dict)
        elif command == Command.HEALTH_CHECK:
            return HealthCheckArgs.from_dict(args_dict)
        else:
            # PAUSE/RESUME/RELOAD have no documented args
            return None
