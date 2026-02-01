"""PostgreSQL storage backend for GLADyS Memory."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

from .config import settings, StorageSettings


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
    # Prediction instrumentation (§27 - Instrument Now, Analyze Later)
    predicted_success: Optional[float] = None  # LLM's prediction of action success (0.0-1.0)
    prediction_confidence: Optional[float] = None  # LLM's confidence in that prediction
    response_id: Optional[str] = None  # Links to executive response/reasoning trace
    response_text: Optional[str] = None  # Actual LLM response (for fine-tuning datasets)


# Keep StorageConfig as alias for backwards compatibility
StorageConfig = StorageSettings


class MemoryStorage:
    """PostgreSQL + pgvector storage backend."""

    def __init__(self, config: Optional[StorageSettings] = None):
        self.config = config or settings.storage
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish connection pool to PostgreSQL."""
        self._pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            min_size=self.config.pool_min_size,
            max_size=self.config.pool_max_size,
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
                salience, structured, entity_ids,
                predicted_success, prediction_confidence, response_id, response_text
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            event.id,
            event.timestamp,
            event.source,
            event.raw_text,
            event.embedding,
            event.salience or {},
            event.structured or {},
            event.entity_ids or [],
            event.predicted_success,
            event.prediction_confidence,
            event.response_id,
            event.response_text,
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
                       salience, structured, entity_ids,
                       predicted_success, prediction_confidence, response_id, response_text
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
                       salience, structured, entity_ids,
                       predicted_success, prediction_confidence, response_id, response_text
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
                       predicted_success, prediction_confidence, response_id, response_text,
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
                       predicted_success, prediction_confidence, response_id, response_text,
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
            # Prediction instrumentation (§27) - may be null for older events
            predicted_success=row.get("predicted_success"),
            prediction_confidence=row.get("prediction_confidence"),
            response_id=row.get("response_id"),
            response_text=row.get("response_text"),
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
        condition_embedding: Optional[np.ndarray] = None,
        origin: Optional[str] = None,
        origin_id: Optional[str] = None,
    ) -> None:
        """Store a new heuristic.

        Args:
            id: Unique identifier for the heuristic
            name: Human-readable name
            condition: Condition dict (should have 'text' key for matching)
            action: Action dict (effects to apply when heuristic fires)
            confidence: Confidence score (0.0 to 1.0)
            source_pattern_ids: Optional list of pattern IDs this heuristic was derived from
            condition_embedding: Optional embedding for semantic matching (384-dim)
            origin: How this heuristic was created (built_in, pack, learned, user)
            origin_id: Reference to origin source (pack ID, trace ID, etc.)
        """
        if not self._pool:
            raise RuntimeError("Not connected to database")

        await self._pool.execute(
            """
            INSERT INTO heuristics (id, name, condition, action, confidence, source_pattern_ids, condition_embedding, origin, origin_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                condition = EXCLUDED.condition,
                action = EXCLUDED.action,
                confidence = EXCLUDED.confidence,
                source_pattern_ids = EXCLUDED.source_pattern_ids,
                condition_embedding = COALESCE(EXCLUDED.condition_embedding, heuristics.condition_embedding),
                origin = COALESCE(EXCLUDED.origin, heuristics.origin),
                origin_id = COALESCE(EXCLUDED.origin_id, heuristics.origin_id),
                updated_at = NOW()
            """,
            id,
            name,
            condition,
            action,
            confidence,
            source_pattern_ids or [],
            condition_embedding,
            origin or "learned",
            origin_id,
        )

    async def get_heuristic(self, heuristic_id: UUID) -> dict | None:
        """Get a single heuristic by ID."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        row = await self._pool.fetchrow(
            """
            SELECT id, name, condition, action, confidence, origin,
                   fire_count, success_count, updated_at,
                   condition->>'text' as condition_text
            FROM heuristics
            WHERE id = $1
            """,
            heuristic_id,
        )

        if not row:
            return None

        result = dict(row)
        # Build effects_json from action for proto compatibility
        import json
        result["effects_json"] = json.dumps(result.get("action") or {})
        return result

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

    async def query_matching_heuristics(
        self,
        event_text: str,
        min_confidence: float = 0.0,
        limit: int = 10,
        source_filter: str | None = None,
        query_embedding: Optional[np.ndarray] = None,
        min_similarity: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """Query heuristics matching event text using semantic similarity.

        Uses embedding-based similarity for accurate semantic matching.
        Falls back to text search only for heuristics without embeddings.

        Args:
            event_text: The event text to match against heuristic conditions
            min_confidence: Minimum confidence threshold
            limit: Maximum number of results
            source_filter: If provided, only return heuristics whose condition
                           text starts with this source/domain prefix
            query_embedding: Pre-computed embedding for event_text (384-dim)
            min_similarity: Minimum cosine similarity threshold (uses config default)

        Returns:
            List of matching heuristics with similarity ranking
        """
        if min_similarity is None:
            min_similarity = settings.salience.heuristic_min_similarity
        if not self._pool:
            raise RuntimeError("Not connected to database")

        result = []

        # Primary: Semantic similarity search (when embedding is available)
        if query_embedding is not None:
            if source_filter:
                source_pattern = f"{source_filter}:%"
                rows = await self._pool.fetch(
                    """
                    SELECT id, name, condition, action, confidence,
                           source_pattern_ids, last_fired, fire_count, success_count,
                           frozen, created_at, updated_at, condition_embedding,
                           1 - (condition_embedding <=> $1) AS similarity
                    FROM heuristics
                    WHERE condition_embedding IS NOT NULL
                      AND 1 - (condition_embedding <=> $1) >= $2
                      AND confidence >= $3
                      AND frozen = false
                      AND (condition->>'text') ILIKE $5
                    ORDER BY condition_embedding <=> $1
                    LIMIT $4
                    """,
                    query_embedding,
                    min_similarity,
                    min_confidence,
                    limit,
                    source_pattern,
                )
            else:
                rows = await self._pool.fetch(
                    """
                    SELECT id, name, condition, action, confidence,
                           source_pattern_ids, last_fired, fire_count, success_count,
                           frozen, created_at, updated_at, condition_embedding,
                           1 - (condition_embedding <=> $1) AS similarity
                    FROM heuristics
                    WHERE condition_embedding IS NOT NULL
                      AND 1 - (condition_embedding <=> $1) >= $2
                      AND confidence >= $3
                      AND frozen = false
                    ORDER BY condition_embedding <=> $1
                    LIMIT $4
                    """,
                    query_embedding,
                    min_similarity,
                    min_confidence,
                    limit,
                )

            result = [dict(row) for row in rows]

        # Fallback: Text search for heuristics without embeddings (during migration)
        # Only used if semantic search returned no results
        if not result and event_text:
            result = await self._query_matching_heuristics_text(
                event_text=event_text,
                min_confidence=min_confidence,
                limit=limit,
                source_filter=source_filter,
            )

        # Update last_accessed for LRU tracking
        if result:
            heuristic_ids = [row["id"] for row in result]
            await self._pool.execute(
                """
                UPDATE heuristics
                SET last_accessed = NOW()
                WHERE id = ANY($1)
                """,
                heuristic_ids,
            )

        return result

    async def _query_matching_heuristics_text(
        self,
        event_text: str,
        min_confidence: float = 0.0,
        limit: int = 10,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fallback text-based heuristic matching.

        Uses PostgreSQL full-text search with OR semantics.
        Only used during migration when heuristics lack embeddings.

        DEPRECATED: Will be removed once all heuristics have embeddings.
        """
        import re
        words = re.findall(r'\b\w{3,}\b', event_text.lower())
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 'her', 'was', 'one', 'our', 'out', 'his', 'has', 'had', 'this', 'that', 'with', 'they', 'been', 'have', 'from', 'will', 'what', 'when', 'where', 'need', 'fast'}
        filtered_words = [w for w in words if w not in stop_words]

        if not filtered_words:
            return []

        or_query = ' | '.join(filtered_words)

        if source_filter:
            source_pattern = f"{source_filter}:%"
            rows = await self._pool.fetch(
                """
                SELECT id, name, condition, action, confidence,
                       source_pattern_ids, last_fired, fire_count, success_count,
                       frozen, created_at, updated_at,
                       ts_rank(condition_tsv, to_tsquery('english', $1)) AS similarity
                FROM heuristics
                WHERE condition_tsv @@ to_tsquery('english', $1)
                  AND confidence >= $2
                  AND frozen = false
                  AND (condition->>'text') ILIKE $4
                ORDER BY similarity DESC, confidence DESC
                LIMIT $3
                """,
                or_query,
                min_confidence,
                limit,
                source_pattern,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, name, condition, action, confidence,
                       source_pattern_ids, last_fired, fire_count, success_count,
                       frozen, created_at, updated_at,
                       ts_rank(condition_tsv, to_tsquery('english', $1)) AS similarity
                FROM heuristics
                WHERE condition_tsv @@ to_tsquery('english', $1)
                  AND confidence >= $2
                  AND frozen = false
                ORDER BY similarity DESC, confidence DESC
                LIMIT $3
                """,
                or_query,
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

    async def update_heuristic_confidence(
        self,
        heuristic_id: UUID,
        positive: bool,
        learning_rate: Optional[float] = None,
        predicted_success: Optional[float] = None,
        feedback_source: str = "explicit",
    ) -> tuple[float, float, float, Optional[float]]:
        """
        Update heuristic confidence using Bayesian Beta-Binomial model.

        Uses Beta(1,1) prior (uniform) with posterior mean:
            confidence = (1 + success_count) / (2 + fire_count)

        Examples:
            - New heuristic (0 fires): 1/2 = 0.5
            - After 2 positive: 3/3 = 1.0
            - After 2 positive, 1 negative: 3/4 = 0.75

        Args:
            heuristic_id: UUID of the heuristic to update
            positive: True for positive feedback, False for negative
            learning_rate: Ignored (kept for API compatibility)
            predicted_success: Ignored (kept for API compatibility)
            feedback_source: 'explicit' (user feedback) or 'implicit' (outcome watcher)

        Returns:
            Tuple of (old_confidence, new_confidence, delta, None)
            td_error is always None (Bayesian doesn't use it)

        Raises:
            RuntimeError: If not connected to database
            ValueError: If heuristic not found
        """
        if not self._pool:
            raise RuntimeError("Not connected to database")

        # Get current state
        row = await self._pool.fetchrow(
            """
            SELECT confidence, fire_count, success_count
            FROM heuristics
            WHERE id = $1
            """,
            heuristic_id,
        )

        if not row:
            raise ValueError(f"Heuristic not found: {heuristic_id}")

        old_confidence = float(row["confidence"])
        fire_count = int(row["fire_count"])
        success_count = int(row["success_count"])

        # Update success_count if positive feedback
        if positive:
            success_count += 1

        # Bayesian Beta-Binomial: confidence = (1 + success_count) / (2 + fire_count)
        # Note: fire_count was already incremented when the heuristic fired
        new_confidence = (1.0 + success_count) / (2.0 + fire_count)
        delta = new_confidence - old_confidence

        # Update database
        await self._pool.execute(
            """
            UPDATE heuristics
            SET confidence = $2,
                success_count = success_count + CASE WHEN $3 THEN 1 ELSE 0 END,
                updated_at = NOW()
            WHERE id = $1
            """,
            heuristic_id,
            new_confidence,
            positive,
        )

        # Update the most recent fire record with the outcome
        await self._update_most_recent_fire(
            heuristic_id=heuristic_id,
            outcome='success' if positive else 'fail',
            feedback_source=feedback_source
        )

        return (old_confidence, new_confidence, delta, None)

    # =========================================================================
    # Heuristic Fire tracking ("Flight Recorder")
    # =========================================================================

    async def record_heuristic_fire(
        self,
        heuristic_id: UUID,
        event_id: str,
        episodic_event_id: Optional[UUID] = None,
    ) -> UUID:
        """Record that a heuristic fired. Returns the fire record ID."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        fire_id = uuid.uuid4()
        await self._pool.execute(
            """
            INSERT INTO heuristic_fires (id, heuristic_id, event_id, episodic_event_id)
            VALUES ($1, $2, $3, $4)
            """,
            fire_id,
            heuristic_id,
            event_id,
            episodic_event_id,
        )
        return fire_id

    async def update_fire_outcome(
        self,
        fire_id: UUID,
        outcome: str,  # 'success' or 'fail'
        feedback_source: str,  # 'explicit' or 'implicit'
    ) -> bool:
        """Update a fire record with its outcome. Returns True if found."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        result = await self._pool.execute(
            """
            UPDATE heuristic_fires
            SET outcome = $2,
                feedback_source = $3,
                feedback_at = NOW()
            WHERE id = $1
            """,
            fire_id,
            outcome,
            feedback_source,
        )
        # UPDATE returns 'UPDATE 1' or 'UPDATE 0'
        return result == "UPDATE 1"

    async def get_pending_fires(
        self,
        heuristic_id: Optional[UUID] = None,
        max_age_seconds: int = 300,
    ) -> list[dict]:
        """Get fires awaiting feedback (outcome='unknown')."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if heuristic_id:
            rows = await self._pool.fetch(
                """
                SELECT id, heuristic_id, event_id, fired_at, episodic_event_id,
                       outcome, feedback_source
                FROM heuristic_fires
                WHERE outcome = 'unknown'
                  AND heuristic_id = $1
                  AND fired_at > NOW() - INTERVAL '1 second' * $2
                ORDER BY fired_at DESC
                """,
                heuristic_id,
                max_age_seconds,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, heuristic_id, event_id, fired_at, episodic_event_id,
                       outcome, feedback_source
                FROM heuristic_fires
                WHERE outcome = 'unknown'
                  AND fired_at > NOW() - INTERVAL '1 second' * $2
                ORDER BY fired_at DESC
                """,
                max_age_seconds,
            )

        return [dict(row) for row in rows]

    async def _update_most_recent_fire(
        self,
        heuristic_id: UUID,
        outcome: str,
        feedback_source: str,
    ) -> bool:
        """Find the most recent 'unknown' fire for a heuristic and update it."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        # Find most recent fire for this heuristic that is still 'unknown'
        row = await self._pool.fetchrow(
            """
            SELECT id FROM heuristic_fires
            WHERE heuristic_id = $1 AND outcome = 'unknown'
            ORDER BY fired_at DESC
            LIMIT 1
            """,
            heuristic_id
        )
        
        if row:
            return await self.update_fire_outcome(row["id"], outcome, feedback_source)
        return False

    # =========================================================================
    # Entity Operations (Semantic Memory)
    # =========================================================================

    async def store_entity(
        self,
        id: UUID,
        canonical_name: str,
        entity_type: str,
        aliases: Optional[list[str]] = None,
        attributes: Optional[dict] = None,
        embedding: Optional[np.ndarray] = None,
        source: Optional[str] = None,
    ) -> None:
        """Store or update an entity."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        await self._pool.execute(
            """
            INSERT INTO entities (
                id, canonical_name, aliases, entity_type,
                attributes, embedding, source
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name,
                aliases = EXCLUDED.aliases,
                entity_type = EXCLUDED.entity_type,
                attributes = EXCLUDED.attributes,
                embedding = COALESCE(EXCLUDED.embedding, entities.embedding),
                last_seen = NOW(),
                mention_count = entities.mention_count + 1,
                updated_at = NOW()
            """,
            id,
            canonical_name,
            aliases or [],
            entity_type,
            attributes or {},
            embedding,
            source,
        )

    async def query_entities_by_name(
        self,
        name_query: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Query entities by name (case-insensitive prefix match)."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if entity_type:
            rows = await self._pool.fetch(
                """
                SELECT id, canonical_name, aliases, entity_type, attributes,
                       embedding, source, first_seen, last_seen, mention_count,
                       created_at, updated_at
                FROM entities
                WHERE merged_into IS NULL
                  AND entity_type = $1
                  AND (
                      LOWER(canonical_name) LIKE LOWER($2) || '%'
                      OR EXISTS (
                          SELECT 1 FROM unnest(aliases) AS alias
                          WHERE LOWER(alias) LIKE LOWER($2) || '%'
                      )
                  )
                ORDER BY mention_count DESC
                LIMIT $3
                """,
                entity_type,
                name_query,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, canonical_name, aliases, entity_type, attributes,
                       embedding, source, first_seen, last_seen, mention_count,
                       created_at, updated_at
                FROM entities
                WHERE merged_into IS NULL
                  AND (
                      LOWER(canonical_name) LIKE LOWER($1) || '%'
                      OR EXISTS (
                          SELECT 1 FROM unnest(aliases) AS alias
                          WHERE LOWER(alias) LIKE LOWER($1) || '%'
                      )
                  )
                ORDER BY mention_count DESC
                LIMIT $2
                """,
                name_query,
                limit,
            )

        return [self._row_to_entity_dict(row) for row in rows]

    async def query_entities_by_similarity(
        self,
        query_embedding: np.ndarray,
        min_similarity: Optional[float] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[tuple[dict[str, Any], float]]:
        """Query entities by embedding similarity."""
        if min_similarity is None:
            min_similarity = settings.salience.heuristic_min_similarity
        if not self._pool:
            raise RuntimeError("Not connected to database")

        if entity_type:
            rows = await self._pool.fetch(
                """
                SELECT id, canonical_name, aliases, entity_type, attributes,
                       embedding, source, first_seen, last_seen, mention_count,
                       created_at, updated_at,
                       1 - (embedding <=> $1) AS similarity
                FROM entities
                WHERE merged_into IS NULL
                  AND embedding IS NOT NULL
                  AND entity_type = $2
                  AND 1 - (embedding <=> $1) >= $3
                ORDER BY embedding <=> $1
                LIMIT $4
                """,
                query_embedding,
                entity_type,
                min_similarity,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT id, canonical_name, aliases, entity_type, attributes,
                       embedding, source, first_seen, last_seen, mention_count,
                       created_at, updated_at,
                       1 - (embedding <=> $1) AS similarity
                FROM entities
                WHERE merged_into IS NULL
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> $1) >= $2
                ORDER BY embedding <=> $1
                LIMIT $3
                """,
                query_embedding,
                min_similarity,
                limit,
            )

        return [(self._row_to_entity_dict(row), row["similarity"]) for row in rows]

    async def get_entity_by_id(self, entity_id: UUID) -> Optional[dict[str, Any]]:
        """Get a single entity by ID."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        row = await self._pool.fetchrow(
            """
            SELECT id, canonical_name, aliases, entity_type, attributes,
                   embedding, source, first_seen, last_seen, mention_count,
                   created_at, updated_at
            FROM entities
            WHERE id = $1 AND merged_into IS NULL
            """,
            entity_id,
        )

        return self._row_to_entity_dict(row) if row else None

    def _row_to_entity_dict(self, row: asyncpg.Record) -> dict[str, Any]:
        """Convert entity row to dictionary."""
        return {
            "id": row["id"],
            "canonical_name": row["canonical_name"],
            "aliases": list(row["aliases"]) if row["aliases"] else [],
            "entity_type": row["entity_type"],
            "attributes": row["attributes"] or {},
            "embedding": np.array(row["embedding"]) if row["embedding"] is not None else None,
            "source": row["source"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "mention_count": row["mention_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # =========================================================================
    # Relationship Operations (Semantic Memory)
    # =========================================================================

    async def store_relationship(
        self,
        id: UUID,
        subject_id: UUID,
        predicate: str,
        object_id: UUID,
        attributes: Optional[dict] = None,
        confidence: float = 1.0,
        source: Optional[str] = None,
        source_event_id: Optional[UUID] = None,
    ) -> None:
        """Store or update a relationship."""
        if not self._pool:
            raise RuntimeError("Not connected to database")

        await self._pool.execute(
            """
            INSERT INTO relationships (
                id, subject_id, predicate, object_id,
                attributes, confidence, source, source_event_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (subject_id, predicate, object_id) DO UPDATE SET
                attributes = EXCLUDED.attributes,
                confidence = EXCLUDED.confidence,
                source = COALESCE(EXCLUDED.source, relationships.source),
                updated_at = NOW()
            """,
            id,
            subject_id,
            predicate,
            object_id,
            attributes or {},
            confidence,
            source,
            source_event_id,
        )

    async def get_relationships(
        self,
        entity_id: UUID,
        predicate_filter: Optional[str] = None,
        include_incoming: bool = True,
        include_outgoing: bool = True,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get relationships for an entity.

        Returns relationships with the related entity included.
        """
        if not self._pool:
            raise RuntimeError("Not connected to database")

        results = []

        # Outgoing relationships (entity is subject)
        if include_outgoing:
            if predicate_filter:
                rows = await self._pool.fetch(
                    """
                    SELECT r.id, r.subject_id, r.predicate, r.object_id,
                           r.attributes, r.confidence, r.source, r.source_event_id,
                           r.created_at, r.updated_at,
                           e.id AS related_id, e.canonical_name, e.aliases,
                           e.entity_type, e.attributes AS entity_attrs
                    FROM relationships r
                    JOIN entities e ON r.object_id = e.id
                    WHERE r.subject_id = $1
                      AND r.predicate = $2
                      AND r.confidence >= $3
                      AND e.merged_into IS NULL
                    ORDER BY r.confidence DESC
                    LIMIT $4
                    """,
                    entity_id,
                    predicate_filter,
                    min_confidence,
                    limit,
                )
            else:
                rows = await self._pool.fetch(
                    """
                    SELECT r.id, r.subject_id, r.predicate, r.object_id,
                           r.attributes, r.confidence, r.source, r.source_event_id,
                           r.created_at, r.updated_at,
                           e.id AS related_id, e.canonical_name, e.aliases,
                           e.entity_type, e.attributes AS entity_attrs
                    FROM relationships r
                    JOIN entities e ON r.object_id = e.id
                    WHERE r.subject_id = $1
                      AND r.confidence >= $2
                      AND e.merged_into IS NULL
                    ORDER BY r.confidence DESC
                    LIMIT $3
                    """,
                    entity_id,
                    min_confidence,
                    limit,
                )
            results.extend([self._row_to_relationship_with_entity(row) for row in rows])

        # Incoming relationships (entity is object)
        if include_incoming:
            remaining = limit - len(results)
            if remaining > 0:
                if predicate_filter:
                    rows = await self._pool.fetch(
                        """
                        SELECT r.id, r.subject_id, r.predicate, r.object_id,
                               r.attributes, r.confidence, r.source, r.source_event_id,
                               r.created_at, r.updated_at,
                               e.id AS related_id, e.canonical_name, e.aliases,
                               e.entity_type, e.attributes AS entity_attrs
                        FROM relationships r
                        JOIN entities e ON r.subject_id = e.id
                        WHERE r.object_id = $1
                          AND r.predicate = $2
                          AND r.confidence >= $3
                          AND e.merged_into IS NULL
                        ORDER BY r.confidence DESC
                        LIMIT $4
                        """,
                        entity_id,
                        predicate_filter,
                        min_confidence,
                        remaining,
                    )
                else:
                    rows = await self._pool.fetch(
                        """
                        SELECT r.id, r.subject_id, r.predicate, r.object_id,
                               r.attributes, r.confidence, r.source, r.source_event_id,
                               r.created_at, r.updated_at,
                               e.id AS related_id, e.canonical_name, e.aliases,
                               e.entity_type, e.attributes AS entity_attrs
                        FROM relationships r
                        JOIN entities e ON r.subject_id = e.id
                        WHERE r.object_id = $1
                          AND r.confidence >= $2
                          AND e.merged_into IS NULL
                        ORDER BY r.confidence DESC
                        LIMIT $3
                        """,
                        entity_id,
                        min_confidence,
                        remaining,
                    )
                results.extend([self._row_to_relationship_with_entity(row) for row in rows])

        return results

    def _row_to_relationship_with_entity(self, row: asyncpg.Record) -> dict[str, Any]:
        """Convert relationship+entity row to dictionary."""
        return {
            "relationship": {
                "id": row["id"],
                "subject_id": row["subject_id"],
                "predicate": row["predicate"],
                "object_id": row["object_id"],
                "attributes": row["attributes"] or {},
                "confidence": row["confidence"],
                "source": row["source"],
                "source_event_id": row["source_event_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
            "related_entity": {
                "id": row["related_id"],
                "canonical_name": row["canonical_name"],
                "aliases": list(row["aliases"]) if row["aliases"] else [],
                "entity_type": row["entity_type"],
                "attributes": row["entity_attrs"] or {},
            },
        }

    async def expand_context(
        self,
        entity_ids: list[UUID],
        max_hops: int = 2,
        max_entities: int = 20,
        min_confidence: float = 0.5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Expand context around entities for LLM prompts.

        Returns (entities, relationships) for the context graph.
        Uses BFS to traverse up to max_hops from starting entities.
        """
        if not self._pool:
            raise RuntimeError("Not connected to database")

        # Track visited entities and collected relationships
        visited_ids: set[UUID] = set()
        all_entities: list[dict[str, Any]] = []
        all_relationships: list[dict[str, Any]] = []

        # BFS frontier
        frontier = list(entity_ids)

        for hop in range(max_hops + 1):
            if not frontier or len(all_entities) >= max_entities:
                break

            # Get entities in current frontier
            for eid in frontier:
                if eid in visited_ids:
                    continue
                if len(all_entities) >= max_entities:
                    break

                entity = await self.get_entity_by_id(eid)
                if entity:
                    all_entities.append(entity)
                    visited_ids.add(eid)

            # Get relationships for frontier (only if more hops to go)
            if hop < max_hops:
                next_frontier = []
                for eid in frontier:
                    if eid not in visited_ids:
                        continue  # Skip if not actually visited

                    rels = await self.get_relationships(
                        entity_id=eid,
                        min_confidence=min_confidence,
                        limit=10,  # Limit per entity to avoid explosion
                    )

                    for rel_data in rels:
                        rel = rel_data["relationship"]
                        related = rel_data["related_entity"]

                        # Add relationship if not duplicate
                        rel_key = (rel["subject_id"], rel["predicate"], rel["object_id"])
                        if not any(
                            (r["subject_id"], r["predicate"], r["object_id"]) == rel_key
                            for r in all_relationships
                        ):
                            all_relationships.append(rel)

                        # Add related entity ID to next frontier
                        related_id = related["id"]
                        if related_id not in visited_ids:
                            next_frontier.append(related_id)

                frontier = next_frontier

        return all_entities, all_relationships
