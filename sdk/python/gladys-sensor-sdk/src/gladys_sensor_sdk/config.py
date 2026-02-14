"""gRPC timeout configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeoutConfig:
    """gRPC timeout configuration for all operations.

    Defaults follow ADR-0005 recommendations.

    Attributes:
        publish_event_ms: Timeout for event publish RPCs (fire-and-forget, fast path).
        heartbeat_ms: Timeout for heartbeat RPCs (includes command delivery).
        register_ms: Timeout for registration RPCs (one-time, may involve setup).
    """

    publish_event_ms: int = 100
    heartbeat_ms: int = 5000
    register_ms: int = 10000

    @staticmethod
    def no_timeout() -> TimeoutConfig:
        """Return config with no timeouts (for testing)."""
        return TimeoutConfig(
            publish_event_ms=0,
            heartbeat_ms=0,
            register_ms=0,
        )
