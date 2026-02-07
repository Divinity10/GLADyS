"""Orchestrator configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorConfig(BaseSettings):
    """Configuration for the Orchestrator service.

    Reads from environment variables (case-insensitive).
    E.g., SALIENCE_MEMORY_ADDRESS=memory:50051
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

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

    # Heuristic confidence threshold for System 1 (fast path) responses
    # If matched heuristic has confidence >= this threshold, return action immediately
    # without calling LLM. Lower values = more aggressive use of learned responses.
    heuristic_confidence_threshold: float = 0.7

    # Emergency fast-path thresholds (default values, override via env)
    # When both conditions are met, Orchestrator bypasses Executive entirely
    emergency_confidence_threshold: float = 0.95
    emergency_threat_threshold: float = 0.9

    # Fallback novelty when Salience service is unavailable
    # Must be >= salience_threshold to ensure events still route
    fallback_novelty: float = 0.8

    # Event queue settings (for events without high-confidence heuristics)
    event_timeout_ms: int = Field(
        default=30000,
        description="How long events wait in queue before timing out (ms)",
    )
    timeout_scan_interval_ms: int = Field(
        default=2000,
        description="How often to scan for timed-out events (ms)",
    )

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
    outcome_timeout_sec: int = Field(
        default=120,
        description="Default timeout for implicit feedback (no complaint = positive)",
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

    # Learning Strategy settings
    learning_strategy: str = "bayesian"
    learning_undo_window_sec: float = 30.0
    learning_ignored_threshold: int = 3
    learning_undo_keywords: str = "undo,revert,cancel,rollback,nevermind,never mind"
    learning_implicit_magnitude: float = 1.0
    learning_explicit_magnitude: float = 0.8
