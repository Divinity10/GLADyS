"""Orchestrator configuration."""

from pydantic import BaseModel


class OrchestratorConfig(BaseModel):
    """Configuration for the Orchestrator service."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 50051

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
    salience_memory_address: str = "localhost:50052"
    executive_address: str = "localhost:50053"
