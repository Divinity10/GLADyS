"""Sensor lifecycle orchestrator.

Composes HeartbeatManager + CommandDispatcher + state management.
Top-level entry point for sensor lifecycle management.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import GladysClient
from .dispatcher import CommandDispatcher
from .heartbeat import HeartbeatManager
from .state import Command, ComponentState

logger = logging.getLogger(__name__)


class SensorLifecycle:
    """Composes HeartbeatManager + CommandDispatcher + state management.

    Handles:
    - Background heartbeat
    - Command dispatching from pending commands
    - State transitions
    - Component registration/unregistration
    """

    def __init__(
        self,
        client: GladysClient,
        component_id: str,
        component_type: str,
        dispatcher: CommandDispatcher,
        heartbeat_interval_seconds: float = 30.0,
    ) -> None:
        """Initialize sensor lifecycle orchestrator.

        Args:
            client: GladysClient instance.
            component_id: Component ID.
            component_type: Component type (e.g., "sensor.runescape").
            dispatcher: CommandDispatcher instance.
            heartbeat_interval_seconds: Heartbeat interval.
        """
        self.client = client
        self.component_id = component_id
        self.component_type = component_type
        self.dispatcher = dispatcher

        # Initialize heartbeat manager with command callback
        self.heartbeat_manager = HeartbeatManager(
            client=client,
            component_id=component_id,
            interval_seconds=heartbeat_interval_seconds,
            on_command=self._handle_pending_command,
        )

    async def start(self) -> None:
        """Start lifecycle (register component, start heartbeat).

        Non-blocking -- heartbeat runs in background.
        """
        # Connect to orchestrator
        await self.client.connect()

        # Register component
        response = await self.client.register_component(
            component_id=self.component_id,
            component_type=self.component_type,
        )

        if hasattr(response, "success") and not response.success:
            raise RuntimeError(f"Registration failed: {response.error_message}")

        logger.info("Component %s registered", self.component_id)

        # Start heartbeat
        self.heartbeat_manager.set_state(ComponentState.STARTING)
        await self.heartbeat_manager.start()

    async def stop(self) -> None:
        """Stop lifecycle (stop heartbeat, unregister component)."""
        # Stop heartbeat
        await self.heartbeat_manager.stop()

        # Unregister component
        await self.client.unregister_component(self.component_id)
        logger.info("Component %s unregistered", self.component_id)

        # Close client
        await self.client.close()

    async def _handle_pending_command(self, pending_cmd: Any) -> None:
        """Handle pending command from heartbeat response.

        Called by HeartbeatManager when commands are received.
        """
        # Extract command enum value from pending command
        cmd_value = getattr(pending_cmd, "command", None)
        cmd_id = getattr(pending_cmd, "command_id", "unknown")

        # Convert proto Command enum to our Command IntEnum
        try:
            command = Command(int(cmd_value))
        except (ValueError, TypeError):
            logger.warning("Unknown command value: %s", cmd_value)
            return

        logger.info("Executing command %s: %s", cmd_id, command.name)

        # Extract args dict from pending command
        args_struct = getattr(pending_cmd, "args", None)
        args_dict: dict[str, Any] | None = None
        if args_struct is not None:
            try:
                # Convert protobuf Struct to dict
                from google.protobuf.json_format import MessageToDict  # type: ignore[import-untyped]

                args_dict = MessageToDict(args_struct)
            except (ImportError, Exception):
                args_dict = {}

        # Dispatch to handler
        new_state, error_message = await self.dispatcher.dispatch(
            command=command,
            args_dict=args_dict,
        )

        # Update heartbeat state
        self.heartbeat_manager.set_state(new_state, error_message)

        logger.info(
            "Command %s completed: %s -> %s",
            cmd_id,
            command.name,
            new_state.name,
        )
