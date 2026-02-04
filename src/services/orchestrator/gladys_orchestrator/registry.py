"""Component registry for the Orchestrator.

Tracks registered components, their status, and pending commands.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from gladys_common import get_logger

logger = get_logger(__name__)


@dataclass
class ComponentInfo:
    """Information about a registered component."""

    component_id: str
    component_type: str
    address: str
    capabilities: Any  # ComponentCapabilities proto
    state: int = 2  # COMPONENT_STATE_ACTIVE
    last_heartbeat_ms: int = 0
    metrics: dict[str, str] = field(default_factory=dict)
    pending_commands: list[dict] = field(default_factory=list)


class ComponentRegistry:
    """
    Registry of all components in the GLADyS system.

    Components register on startup, send heartbeats, and unregister on shutdown.
    The registry tracks component health and routes service discovery queries.
    """

    def __init__(self):
        self._components: dict[str, ComponentInfo] = {}
        self._by_type: dict[str, list[str]] = {}  # type -> [component_ids]

    def register(
        self,
        component_id: str,
        component_type: str,
        address: str,
        capabilities: Any,
    ) -> dict:
        """
        Register a new component.

        Returns a RegisterResponse dict.
        """
        # Check for conflicts
        if component_id in self._components:
            existing = self._components[component_id]
            if existing.address != address:
                # Different address, might be a restart - allow re-registration
                logger.warning(
                    f"Component {component_id} re-registering with new address "
                    f"({existing.address} -> {address})"
                )

        # Register
        info = ComponentInfo(
            component_id=component_id,
            component_type=component_type,
            address=address,
            capabilities=capabilities,
            last_heartbeat_ms=int(time.time() * 1000),
        )
        self._components[component_id] = info

        # Track by type
        if component_type not in self._by_type:
            self._by_type[component_type] = []
        if component_id not in self._by_type[component_type]:
            self._by_type[component_type].append(component_id)

        logger.info("Registered component", component_id=component_id, component_type=component_type, address=address)

        return {
            "success": True,
            "error_message": "",
            "assigned_id": component_id,
        }

    def unregister(self, component_id: str) -> bool:
        """Unregister a component."""
        if component_id not in self._components:
            logger.warning("Attempted to unregister unknown component", component_id=component_id)
            return False

        info = self._components.pop(component_id)

        # Remove from type index
        if info.component_type in self._by_type:
            self._by_type[info.component_type] = [
                cid for cid in self._by_type[info.component_type] if cid != component_id
            ]

        logger.info("Unregistered component", component_id=component_id)
        return True

    def update_heartbeat(
        self,
        component_id: str,
        state: int,
        metrics: dict[str, str],
    ) -> bool:
        """Update heartbeat for a component."""
        if component_id not in self._components:
            logger.warning("Heartbeat from unknown component", component_id=component_id)
            return False

        info = self._components[component_id]
        info.last_heartbeat_ms = int(time.time() * 1000)
        info.state = state
        info.metrics.update(metrics)

        return True

    def get_pending_commands(self, component_id: str) -> list[dict]:
        """Get and clear pending commands for a component."""
        if component_id not in self._components:
            return []

        info = self._components[component_id]
        commands = info.pending_commands
        info.pending_commands = []
        return commands

    def queue_command(self, component_id: str, command: dict) -> bool:
        """Queue a command for a component (delivered on next heartbeat)."""
        if component_id not in self._components:
            return False

        self._components[component_id].pending_commands.append(command)
        return True

    def get_by_id(self, component_id: str) -> ComponentInfo | None:
        """Get component info by ID."""
        return self._components.get(component_id)

    def get_by_type(self, component_type: str) -> ComponentInfo | None:
        """Get first component of a given type."""
        if component_type not in self._by_type:
            return None

        component_ids = self._by_type[component_type]
        if not component_ids:
            return None

        # Return first active component of this type
        for cid in component_ids:
            info = self._components.get(cid)
            if info and info.state == 2:  # COMPONENT_STATE_ACTIVE
                return info

        # Return first component if none active
        return self._components.get(component_ids[0])

    def get_all_status(self) -> list[dict]:
        """Get status of all components."""
        return [
            {
                "component_id": info.component_id,
                "state": info.state,
                "message": f"Last heartbeat: {info.last_heartbeat_ms}",
                "metrics": info.metrics,
            }
            for info in self._components.values()
        ]

    @property
    def component_count(self) -> int:
        """Number of registered components."""
        return len(self._components)
