"""Configuration settings for GLADyS Memory subsystem.

Uses pydantic-settings for environment variable and config file support.
All magic numbers and tunable parameters should live here.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5433, description="PostgreSQL port")
    database: str = Field(default="gladys", description="Database name")
    user: str = Field(default="gladys", description="Database user")
    password: str = Field(default="gladys", description="Database password")

    # Connection pool
    pool_min_size: int = Field(default=2, description="Minimum pool connections")
    pool_max_size: int = Field(default=10, description="Maximum pool connections")


class EmbeddingSettings(BaseSettings):
    """Embedding model settings."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        extra="ignore",
    )

    model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model name",
    )
    embedding_dim: int = Field(
        default=384,
        description="Embedding vector dimension (must match model)",
    )


class SalienceSettings(BaseSettings):
    """Salience evaluation settings - tune these for sensitivity."""

    model_config = SettingsConfigDict(
        env_prefix="SALIENCE_",
        env_file=".env",
        extra="ignore",
    )

    # Novelty detection
    novelty_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Similarity threshold for novelty detection (higher = stricter)",
    )
    novelty_time_window_hours: int = Field(
        default=24,
        ge=1,
        description="Time window for novelty detection",
    )
    novelty_similar_limit: int = Field(
        default=5,
        ge=1,
        description="Max similar events to check for novelty",
    )

    # Heuristic matching
    heuristic_min_confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Minimum confidence to consider a heuristic",
    )

    # Word overlap matching (CBR placeholder)
    word_overlap_min: int = Field(
        default=2,
        ge=1,
        description="Minimum word overlap for heuristic match",
    )
    word_overlap_ratio: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum ratio of condition words to match",
    )

    # Skip novelty detection (for benchmarking word-overlap only)
    skip_novelty_detection: bool = Field(
        default=False,
        description="Skip embedding-based novelty detection (for apples-to-apples benchmarking)",
    )

    # Novelty score thresholds
    novelty_high_boost: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Novelty score when no similar events found",
    )
    novelty_medium_boost: float = Field(
        default=0.4,
        ge=0.0, le=1.0,
        description="Novelty score when few similar events found",
    )
    habituation_boost: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Habituation increase when many similar events found",
    )


class ServerSettings(BaseSettings):
    """gRPC server settings."""

    model_config = SettingsConfigDict(
        env_prefix="GRPC_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", description="gRPC server bind address")
    port: int = Field(default=50051, description="gRPC server port")
    max_workers: int = Field(default=10, description="Thread pool size")


class MemorySettings(BaseSettings):
    """Top-level memory settings - composes all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    storage: StorageSettings = Field(default_factory=StorageSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    salience: SalienceSettings = Field(default_factory=SalienceSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    # Feature flags
    dev_mode: bool = Field(
        default=False,
        description="Enable development mode (verbose logging, etc.)",
    )


# Global settings instance - import this
settings = MemorySettings()
