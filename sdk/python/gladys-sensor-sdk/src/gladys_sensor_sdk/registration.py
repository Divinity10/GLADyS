"""One-shot sensor registration helper.

Useful for standalone registration without full adapter lifecycle.
"""

from __future__ import annotations

from typing import Any, Optional

from .client import GladysClient
from .config import TimeoutConfig


class SensorRegistration:
    """One-shot helper for sensor registration.

    Useful for standalone registration without full adapter lifecycle.
    """

    @staticmethod
    async def register(
        component_id: str,
        component_type: str,
        orchestrator_address: str,
        capabilities: Optional[dict[str, Any]] = None,
        timeout_config: Optional[TimeoutConfig] = None,
    ) -> Any:
        """Register sensor component with orchestrator.

        Args:
            component_id: Unique component ID.
            component_type: Component type (e.g., "sensor.runescape").
            orchestrator_address: gRPC address.
            capabilities: Component capabilities dict.
            timeout_config: Timeout configuration.

        Returns:
            RegisterResponse.

        Raises:
            RuntimeError: If registration fails.
        """
        client = GladysClient(
            orchestrator_address=orchestrator_address,
            timeout_config=timeout_config,
        )

        try:
            await client.connect()
            response = await client.register_component(
                component_id=component_id,
                component_type=component_type,
                capabilities=capabilities,
            )

            if hasattr(response, "success") and not response.success:
                raise RuntimeError(
                    f"Registration failed: {response.error_message}"
                )

            return response
        finally:
            await client.close()
