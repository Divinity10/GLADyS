"""Orchestrator configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class OrchestratorConfig(BaseSettings):
    """Configuration for the Orchestrator service.

    Reads from environment variables (case-insensitive).
    E.g., SALIENCE_MEMORY_ADDRESS=memory:50051
    """

    # Server settings
    host: str = "0.0.0.0"
    port: int = 50050  # Different from Memory (50051) to avoid conflicts

    # Moment accumulation settings
    # NOTE: 1Hz (1000ms) is too slow for responsive UX per architecture review 2026-01-21
    # Target: 50-100ms for real-time scenarios (gaming, conversation)
    moment_window_ms: int = 100  # Default 100ms moment window

    # Salience threshold for immediate routing (bypass moment accumulation)
    # Events with max salience dimension above this threshold go immediately to Executive
    high_salience_threshold: float = 0.7

    # Health check settings
    heartbeat_timeout_sec: int = 30
    health_check_interval_sec: int = 10

    # gRPC settings
    max_workers: int = 10

    # Downstream service addresses (will be resolved via service discovery in prod)
    salience_memory_address: str = "localhost:50052"  # Rust SalienceGateway
    memory_storage_address: str = "localhost:50051"   # Python MemoryStorage
    executive_address: str = "localhost:50053"

    # Outcome Watcher settings (Phase 2: Implicit Feedback)
    outcome_watcher_enabled: bool = Field(
        default=True,
        description="Enable implicit feedback via outcome observation",
    )
    outcome_cleanup_interval_sec: int = Field(
        default=30,
        description="How often to cleanup expired outcome expectations",
    )
    # Default outcome patterns - JSON array of objects with:
    # - trigger_pattern: substring match on heuristic condition_text
    # - outcome_pattern: substring match on outcome event raw_text
    # - timeout_sec: how long to wait (default 120)
    # - is_success: true = outcome means success (default true)
    outcome_patterns_json: str = Field(
        default='[]',
        description="JSON array of outcome patterns for implicit feedback",
    )
