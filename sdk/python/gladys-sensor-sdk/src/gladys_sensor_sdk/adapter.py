"""Sensor base class (primary developer-facing API).

Developers subclass AdapterBase and override handle_start(), handle_stop(),
etc. SDK handles all lifecycle management, heartbeat, and state transitions.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Optional

from .args import HealthCheckArgs, RecoverArgs, StartArgs, StopArgs
from .client import GladysClient
from .config import TimeoutConfig
from .dispatcher import CommandDispatcher
from .events import EventDispatcher
from .lifecycle import SensorLifecycle
from .state import Command, ComponentState

logger = logging.getLogger(__name__)


class AdapterBase(ABC):
    """Base class for GLADyS sensors (primary developer-facing API).

    Developers subclass this and override handle_start(), handle_stop(), etc.
    SDK handles all lifecycle management, heartbeat, and state transitions.

    Example::

        class GameSensor(AdapterBase):
            async def handle_start(self, args: StartArgs) -> None:
                # Connect to game, start capturing events
                pass

            async def handle_stop(self, args: StopArgs) -> None:
                # Disconnect from game
                pass
    """

    def __init__(
        self,
        component_id: str,
        component_type: str,
        orchestrator_address: str,
        heartbeat_interval_seconds: float = 30.0,
        timeout_config: Optional[TimeoutConfig] = None,
        flush_interval_ms: int = 0,
        immediate_on_threat: bool = True,
    ) -> None:
        """Initialize adapter.

        Args:
            component_id: Unique component ID.
            component_type: Component type (e.g., "sensor.runescape").
            orchestrator_address: gRPC address (e.g., "localhost:50051").
            heartbeat_interval_seconds: Heartbeat interval.
            timeout_config: gRPC timeout configuration.
            flush_interval_ms: Event flush interval (0 = immediate).
            immediate_on_threat: Send threat events immediately in scheduled mode.
        """
        self.component_id = component_id
        self.component_type = component_type

        # Initialize client
        self.client = GladysClient(
            orchestrator_address=orchestrator_address,
            timeout_config=timeout_config,
        )

        # Initialize event dispatcher
        self.events = EventDispatcher(
            client=self.client,
            source=component_id,
            flush_interval_ms=flush_interval_ms,
            immediate_on_threat=immediate_on_threat,
        )

        # Initialize command dispatcher
        self._dispatcher = CommandDispatcher(component_id=component_id)
        self._register_handlers()

        # Initialize lifecycle
        self.lifecycle = SensorLifecycle(
            client=self.client,
            component_id=component_id,
            component_type=component_type,
            dispatcher=self._dispatcher,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )

    def _register_handlers(self) -> None:
        """Register command handlers with dispatcher (internal)."""
        self._dispatcher.register_handler(Command.START, self.handle_start)
        self._dispatcher.register_handler(Command.STOP, self.handle_stop)
        self._dispatcher.register_handler(Command.PAUSE, self.handle_pause)
        self._dispatcher.register_handler(Command.RESUME, self.handle_resume)
        self._dispatcher.register_handler(Command.RELOAD, self.handle_reload)
        self._dispatcher.register_handler(
            Command.HEALTH_CHECK, self.handle_health_check
        )
        self._dispatcher.register_handler(Command.RECOVER, self.handle_recover)
        self._dispatcher.register_error_handler(self.on_command_error)

    # ------------------------------------------------------------------
    # Command Handlers (override in subclasses)
    # ------------------------------------------------------------------

    async def handle_start(
        self, args: StartArgs
    ) -> Optional[ComponentState]:
        """Handle START command.

        Args:
            args: Parsed start arguments.

        Returns:
            None (use default ACTIVE state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_start", self.__class__.__name__
        )
        return None

    async def handle_stop(self, args: StopArgs) -> Optional[ComponentState]:
        """Handle STOP command.

        Args:
            args: Parsed stop arguments.

        Returns:
            None (use default STOPPED state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_stop", self.__class__.__name__
        )
        return None

    async def handle_pause(self) -> Optional[ComponentState]:
        """Handle PAUSE command (no args).

        Returns:
            None (use default PAUSED state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_pause", self.__class__.__name__
        )
        return None

    async def handle_resume(self) -> Optional[ComponentState]:
        """Handle RESUME command (no args).

        Returns:
            None (use default ACTIVE state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_resume", self.__class__.__name__
        )
        return None

    async def handle_reload(self) -> Optional[ComponentState]:
        """Handle RELOAD command (no args).

        Returns:
            None (use default ACTIVE state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_reload", self.__class__.__name__
        )
        return None

    async def handle_health_check(
        self, args: HealthCheckArgs
    ) -> Optional[ComponentState]:
        """Handle HEALTH_CHECK command.

        Note: Exceptions do NOT set ERROR state (health check fail != broken).

        Args:
            args: Parsed health check arguments.

        Returns:
            None (state unchanged) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_health_check",
            self.__class__.__name__,
        )
        return None

    async def handle_recover(
        self, args: RecoverArgs
    ) -> Optional[ComponentState]:
        """Handle RECOVER command.

        Args:
            args: Parsed recovery arguments.

        Returns:
            None (use default ACTIVE state) or explicit ComponentState.
        """
        logger.warning(
            "%s does not implement handle_recover", self.__class__.__name__
        )
        return None

    async def on_command_error(
        self,
        command: Command,
        exception: Exception,
        current_state: ComponentState,
    ) -> Optional[ComponentState]:
        """Global error handler for all commands.

        Called when any command handler raises an exception.

        Args:
            command: Command that failed.
            exception: Exception raised.
            current_state: State before command execution.

        Returns:
            None (accept default ERROR state) or explicit ComponentState.
        """
        logger.error(
            "Command %s failed: %s", command.name, exception, exc_info=True
        )
        return None  # Accept ERROR state
