"""Integration tests for PostgreSQL storage backend.

These tests require a running PostgreSQL instance with pgvector.
Run with: uv run pytest tests/test_storage.py -v
"""

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import numpy as np
import pytest

from gladys_memory.config import StorageSettings
from gladys_memory.storage import MemoryStorage, EpisodicEvent


@pytest.fixture
def storage_config():
    """Configuration for test database."""
    return StorageSettings(
        host="localhost",
        port=5433,
        database="gladys",
        user="gladys",
        password="gladys",
    )


@pytest.fixture
async def storage(storage_config):
    """Create and connect storage, cleanup after test."""
    storage = MemoryStorage(storage_config)
    await storage.connect()
    yield storage
    # Cleanup: delete test events
    await storage._pool.execute(
        "DELETE FROM episodic_events WHERE source LIKE 'test_%'"
    )
    await storage.close()


@pytest.fixture
def sample_embedding():
    """Generate a sample 384-dim embedding."""
    np.random.seed(42)
    return np.random.randn(384).astype(np.float32)


@pytest.fixture
def sample_event(sample_embedding):
    """Create a sample episodic event."""
    return EpisodicEvent(
        id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        source="test_sensor",
        raw_text="Player spotted a zombie in the cave",
        embedding=sample_embedding,
        salience={"threat": 0.8, "novelty": 0.5},
        structured={"entity": "zombie", "location": "cave"},
        entity_ids=[],
    )


class TestStorageConnection:
    """Tests for database connection."""

    async def test_connect_success(self, storage_config):
        """Should connect to PostgreSQL successfully."""
        storage = MemoryStorage(storage_config)
        await storage.connect()
        assert storage._pool is not None
        await storage.close()

    async def test_connect_creates_pool(self, storage_config):
        """Connection pool should be created."""
        storage = MemoryStorage(storage_config)
        await storage.connect()
        assert storage._pool.get_size() >= 2  # min_size
        await storage.close()


class TestEventStorage:
    """Tests for storing events."""

    async def test_store_event_basic(self, storage, sample_event):
        """Should store an event successfully."""
        await storage.store_event(sample_event)

        # Verify it was stored
        row = await storage._pool.fetchrow(
            "SELECT * FROM episodic_events WHERE id = $1",
            sample_event.id
        )
        assert row is not None
        assert row["source"] == "test_sensor"
        assert row["raw_text"] == "Player spotted a zombie in the cave"

    async def test_store_event_with_embedding(self, storage, sample_event):
        """Should store event with embedding."""
        await storage.store_event(sample_event)

        row = await storage._pool.fetchrow(
            "SELECT embedding FROM episodic_events WHERE id = $1",
            sample_event.id
        )
        assert row["embedding"] is not None
        assert len(row["embedding"]) == 384

    async def test_store_event_with_salience(self, storage, sample_event):
        """Should store event with salience scores."""
        await storage.store_event(sample_event)

        row = await storage._pool.fetchrow(
            "SELECT salience FROM episodic_events WHERE id = $1",
            sample_event.id
        )
        assert row["salience"]["threat"] == 0.8
        assert row["salience"]["novelty"] == 0.5

    async def test_store_event_without_embedding(self, storage):
        """Should store event without embedding."""
        event = EpisodicEvent(
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            source="test_sensor_no_embed",
            raw_text="Simple event without embedding",
        )
        await storage.store_event(event)

        row = await storage._pool.fetchrow(
            "SELECT * FROM episodic_events WHERE id = $1",
            event.id
        )
        assert row is not None
        assert row["embedding"] is None


class TestQueryByTime:
    """Tests for time-based queries."""

    async def test_query_by_time_returns_events(self, storage, sample_embedding):
        """Should return events within time range."""
        # Store some events
        now = datetime.now(timezone.utc)
        for i in range(3):
            event = EpisodicEvent(
                id=uuid4(),
                timestamp=now - timedelta(minutes=i),
                source="test_time_query",
                raw_text=f"Event {i}",
                embedding=sample_embedding,
            )
            await storage.store_event(event)

        # Query last 10 minutes
        events = await storage.query_by_time(
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=1),
            source="test_time_query",
        )

        assert len(events) == 3

    async def test_query_by_time_respects_source_filter(self, storage, sample_embedding):
        """Should filter by source when specified."""
        now = datetime.now(timezone.utc)

        # Store events from different sources
        for source in ["test_source_a", "test_source_b"]:
            event = EpisodicEvent(
                id=uuid4(),
                timestamp=now,
                source=source,
                raw_text=f"Event from {source}",
                embedding=sample_embedding,
            )
            await storage.store_event(event)

        events = await storage.query_by_time(
            start=now - timedelta(minutes=1),
            end=now + timedelta(minutes=1),
            source="test_source_a",
        )

        assert len(events) == 1
        assert events[0].source == "test_source_a"

    async def test_query_by_time_orders_by_timestamp_desc(self, storage, sample_embedding):
        """Should return events in descending timestamp order."""
        now = datetime.now(timezone.utc)

        for i in range(3):
            event = EpisodicEvent(
                id=uuid4(),
                timestamp=now - timedelta(minutes=i),
                source="test_order",
                raw_text=f"Event {i}",
                embedding=sample_embedding,
            )
            await storage.store_event(event)

        events = await storage.query_by_time(
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=1),
            source="test_order",
        )

        # Most recent first
        assert events[0].raw_text == "Event 0"
        assert events[2].raw_text == "Event 2"


class TestQueryBySimilarity:
    """Tests for similarity-based queries."""

    async def test_query_by_similarity_finds_similar(self, storage):
        """Should find semantically similar events."""
        # Create a base embedding
        base = np.zeros(384, dtype=np.float32)
        base[0] = 1.0  # Unit vector in first dimension

        # Create a similar embedding (small perturbation)
        similar = base.copy()
        similar[1] = 0.1  # Slightly different

        # Create a different embedding
        different = np.zeros(384, dtype=np.float32)
        different[100] = 1.0  # Orthogonal to base

        now = datetime.now(timezone.utc)

        # Store events
        similar_event = EpisodicEvent(
            id=uuid4(),
            timestamp=now,
            source="test_similarity_similar",
            raw_text="Similar event",
            embedding=similar,
        )
        await storage.store_event(similar_event)

        different_event = EpisodicEvent(
            id=uuid4(),
            timestamp=now,
            source="test_similarity_different",
            raw_text="Different event",
            embedding=different,
        )
        await storage.store_event(different_event)

        # Query with base embedding
        results = await storage.query_by_similarity(
            query_embedding=base,
            threshold=0.9,
            limit=10,
        )

        # Should find the similar one but not the different one
        sources = [e.source for e, _ in results]
        assert "test_similarity_similar" in sources
        assert "test_similarity_different" not in sources

    async def test_query_by_similarity_returns_scores(self, storage, sample_embedding):
        """Should return similarity scores with events."""
        event = EpisodicEvent(
            id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            source="test_similarity_scores",
            raw_text="Test event",
            embedding=sample_embedding,
        )
        await storage.store_event(event)

        results = await storage.query_by_similarity(
            query_embedding=sample_embedding,
            threshold=0.5,
            limit=10,
        )

        assert len(results) >= 1
        event, score = results[0]
        assert score > 0.99  # Should be nearly identical


class TestHeuristicStorage:
    """Tests for heuristic CRUD operations."""

    async def test_store_heuristic(self, storage):
        """Should store a heuristic."""
        heuristic_id = uuid4()
        await storage.store_heuristic(
            id=heuristic_id,
            name="test_heuristic",
            condition={"event_type": "doorbell"},
            action={"notify": True},
            confidence=0.85,
        )

        row = await storage._pool.fetchrow(
            "SELECT * FROM heuristics WHERE id = $1",
            heuristic_id
        )
        assert row is not None
        assert row["name"] == "test_heuristic"
        assert row["confidence"] == 0.85

    async def test_query_heuristics_by_confidence(self, storage):
        """Should query heuristics above confidence threshold."""
        # Store heuristics with different confidences
        for conf in [0.3, 0.6, 0.9]:
            await storage.store_heuristic(
                id=uuid4(),
                name=f"test_heuristic_{conf}",
                condition={"test": True},
                action={"test": True},
                confidence=conf,
            )

        results = await storage.query_heuristics(min_confidence=0.5)

        assert len(results) >= 2
        for h in results:
            assert h["confidence"] >= 0.5

    async def test_update_heuristic_stats(self, storage):
        """Should update heuristic fire count and success count."""
        heuristic_id = uuid4()
        await storage.store_heuristic(
            id=heuristic_id,
            name="test_stats_heuristic",
            condition={},
            action={},
            confidence=0.5,
        )

        await storage.update_heuristic_fired(heuristic_id, success=True)

        row = await storage._pool.fetchrow(
            "SELECT fire_count, success_count FROM heuristics WHERE id = $1",
            heuristic_id
        )
        assert row["fire_count"] == 1
        assert row["success_count"] == 1
