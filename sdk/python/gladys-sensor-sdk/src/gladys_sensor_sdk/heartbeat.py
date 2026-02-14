"""Background heartbeat manager.

Sends periodic heartbeats to the orchestrator and dispatches pending
commands via callback. Internal component composed by SensorLifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from .client import GladysClient
from .state import ComponentState

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Manages background heartbeat loop.

    Internal component composed by SensorLifecycle. Sends periodic heartbeats
    and dispatches pending commands via callback.
    """

    def __init__(
        self,
        client: GladysClient,
        component_id: str,
        interval_seconds: float = 30.0,
        on_command: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> None:
        """Initialize heartbeat manager.

        Args:
            client: GladysClient instance.
            component_id: Component ID.
            interval_seconds: Heartbeat interval (default 30s).
            on_command: Async callback for pending commands.
        """
        self.client = client
        self.component_id = component_id
        self.interval_seconds = interval_seconds
        self.on_command = on_command

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._current_state = ComponentState.UNKNOWN
        self._error_message: Optional[str] = None

    def set_state(
        self,
        state: ComponentState,
        error_message: Optional[str] = None,
    ) -> None:
        """Update current state (called by dispatcher after command execution).

        Args:
            state: New component state.
            error_message: Optional error message for ERROR state.
        """
        self._current_state = state
        self._error_message = error_message

    async def start(self) -> None:
        """Start heartbeat loop (non-blocking)."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop heartbeat loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _heartbeat_loop(self) -> None:
        """Background heartbeat loop."""
        while self._running:
            try:
                response = await self.client.heartbeat(
                    component_id=self.component_id,
                    state=self._current_state,
                    error_message=self._error_message,
                )

                # Reset error message after sent
                if self._error_message:
                    self._error_message = None

                # Dispatch pending commands
                if self.on_command:
                    for pending_cmd in response.pending_commands:
                        await self.on_command(pending_cmd)

            except Exception:
                logger.error("Heartbeat failed", exc_info=True)

            await asyncio.sleep(self.interval_seconds)
