"""PostgreSQL storage backend for GLADyS Memory."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector


@dataclass
class EpisodicEvent:
    """An episodic event stored in memory."""

    id: UUID
    timestamp: datetime
    source: str
    raw_text: str
    embedding: Optional[np.ndarray] = None
    salience: Optional[dict] = None
    structured: Optional[dict] = None
    entity_ids: Optional[list[UUID]] = None


@dataclass
class StorageConfig:
    """Configuration for PostgreSQL connection.

    Reads from environment variables if available:
      STORAGE_HOST, STORAGE_PORT, STORAGE_DATABASE, STORAGE_USER, STORAGE_PASSWORD
    """

    host: str = field(default_factory=lambda: os.environ.get("STORAGE_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("STORAGE_PORT", "5433")))
    database: str = field(default_factory=lambda: os.environ.get("STORAGE_DATABASE", "gladys"))
    user: str = field(default_factory=lambda: os.environ.get("STORAGE_USER", "gladys"))
    password: str = field(default_factory=lambda: os.environ.get("STORAGE_PASSWORD", "gladys"))


class MemoryStorage:
    """PostgreSQL + pgvector storage backend."""

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish connection pool to PostgreSQL."""
        self._pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            min_size=2,
            max_size=10,
            setup=self._setup_connection,
        )

    async def _setup_connection(self, conn: asyncpg.Connection) -> None:
        """Set up pgvector extension and JSON codec on each connection."""
        await register_vector(conn)
        # Set up JSON codec for JSONB columns
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    # =========================================================================
    # Event Operations
    # =========================================================================

    async def store_event(self, event: EpisodicEvent) -> None:
        """Store an episodic event."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        await self._pool.execute(
            """
            INSERT INTO episodic_events (
                id, timestamp, source, raw_text, embedding,
                salience, structured, entity_ids
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            event.id,
            event.timestamp,
            event.source,
            event.raw_text,
            event.embedding,
            event.salience or {},
            event.structured or {},
            event.entity_ids or [],
        )

    async def query_by_time(
        self,
        start: datetime,
        end: datetime,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        """Query events by time range."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if source:
            rows = await self._pool.fetch(
                """
                SELECT id, timestamp, source, raw_text, embedding,
                       salience, structured, entity_ids
                FROM episodic_events
                WHERE timestamp BETWEEN $1 AND $2
                  AND source = $3
                  AND archived = false
                ORDER BY timestamp DESC
                LIMIT $4
                """,
                start,
                end,
                source,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, timestamp, source, raw_text, embedding,
                       salience, structured, entity_ids
                FROM episodic_events
                WHERE timestamp BETWEEN $1 AND $2
                  AND archived = false
                ORDER BY timestamp DESC
                LIMIT $3
                """,
                start,
                end,
                limit,
            )

        return [self._row_to_event(row) for row in rows]

    async def query_by_similarity(
        self,
        query_embedding: np.ndarray,
        threshold: float = 0.7,
        limit: int = 10,
        hours: Optional[int] = None,
    ) -> list[tuple[EpisodicEvent, float]]:
        """Query events by embedding similarity.

        Returns list of (event, similarity_score) tuples.
        """
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if hours:
            rows = await self._pool.fetch(
                f"""
                SELECT id, timestamp, source, raw_text, embedding,
                       salience, structured, entity_ids,
                       1 - (embedding <=> $1) AS similarity
                FROM episodic_events
                WHERE archived = false
                  AND embedding IS NOT NULL
                  AND timestamp > NOW() - INTERVAL '{hours} hours'
                  AND 1 - (embedding <=> $1) >= $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                query_embedding,
                threshold,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, timestamp, source, raw_text, embedding,
                       salience, structured, entity_ids,
                       1 - (embedding <=> $1) AS similarity
                FROM episodic_events
                WHERE archived = false
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> $1) >= $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                query_embedding,
                threshold,
                limit,
            )

        return [(self._row_to_event(row), row["similarity"]) for row in rows]

    def _row_to_event(self, row: asyncpg.Record) -> EpisodicEvent:
        """Convert database row to EpisodicEvent."""
        return EpisodicEvent(
            id=row["id"],
            timestamp=row["timestamp"],
            source=row["source"],
            raw_text=row["raw_text"],
            embedding=np.array(row["embedding"]) if row["embedding"] is not None else None,
            salience=row["salience"],
            structured=row["structured"],
            entity_ids=row["entity_ids"],
        )

    # =========================================================================
    # Heuristic Operations
    # =========================================================================

    async def store_heuristic(
        self,
        id: UUID,
        name: str,
        condition: dict,
        action: dict,
        confidence: float,
        source_pattern_ids: Optional[list[UUID]] = None,
    ) -> None:
        """Store a new heuristic."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        await self._pool.execute(
            """
            INSERT INTO heuristics (id, name, condition, action, confidence, source_pattern_ids)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                condition = EXCLUDED.condition,
                action = EXCLUDED.action,
                confidence = EXCLUDED.confidence,
                source_pattern_ids = EXCLUDED.source_pattern_ids,
                updated_at = NOW()
            """,
            id,
            name,
            condition,
            action,
            confidence,
            source_pattern_ids or [],
        )

    async def query_heuristics(
        self,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query heuristics above confidence threshold."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        rows = await self._pool.fetch(
            """
            SELECT id, name, condition, action, confidence,
                   source_pattern_ids, last_fired, fire_count, success_count,
                   frozen, created_at, updated_at
            FROM heuristics
            WHERE confidence >= $1
              AND frozen = false
            ORDER BY confidence DESC
            LIMIT $2
            """,
            min_confidence,
            limit,
        )

        return [dict(row) for row in rows]

    async def update_heuristic_fired(
        self,
        heuristic_id: UUID,
        success: bool,
    ) -> None:
        """Update heuristic stats when it fires."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if success:
            await self._pool.execute(
                """
                UPDATE heuristics
                SET fire_count = fire_count + 1,
                    success_count = success_count + 1,
                    last_fired = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                heuristic_id,
            )
        else:
            await self._pool.execute(
                """
                UPDATE heuristics
                SET fire_count = fire_count + 1,
                    last_fired = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                heuristic_id,
            )
