"""Integration tests for gRPC server.

These tests require PostgreSQL to be running (docker-compose up -d).
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import grpc
import numpy as np
import pytest

from gladys_memory import memory_pb2, memory_pb2_grpc, types_pb2
from gladys_memory.config import StorageSettings
from gladys_memory.embeddings import EmbeddingGenerator
from gladys_memory.grpc_server import MemoryStorageServicer, _embedding_to_bytes, _bytes_to_embedding
from gladys_memory.storage import MemoryStorage, EpisodicEvent


# Test configuration
TEST_CONFIG = StorageSettings(
    host="localhost",
    port=5433,
    database="gladys",
    user="gladys",
    password="gladys",
)


class TestEmbeddingConversion:
    """Test embedding byte conversion utilities."""

    def test_embedding_to_bytes_and_back(self):
        """Round-trip conversion should preserve values."""
        original = np.random.randn(384).astype(np.float32)
        as_bytes = _embedding_to_bytes(original)
        recovered = _bytes_to_embedding(as_bytes)
        np.testing.assert_array_almost_equal(original, recovered)

    def test_embedding_to_bytes_none(self):
        """None embedding should become empty bytes."""
        result = _embedding_to_bytes(None)
        assert result == b""

    def test_bytes_to_embedding_empty(self):
        """Empty bytes should become None."""
        result = _bytes_to_embedding(b"")
        assert result is None


class TestMemoryStorageServicer:
    """Integration tests for gRPC servicer."""

    @pytest.fixture
    async def storage(self):
        """Create connected storage instance."""
        storage = MemoryStorage(TEST_CONFIG)
        await storage.connect()
        yield storage
        await storage.close()

    @pytest.fixture
    def embeddings(self):
        """Create embedding generator."""
        return EmbeddingGenerator()

    @pytest.fixture
    async def servicer(self, storage, embeddings):
        """Create servicer with dependencies."""
        return MemoryStorageServicer(storage, embeddings)

    @pytest.fixture
    async def cleanup_events(self, storage):
        """Clean up test events after tests."""
        created_ids = []
        yield created_ids
        # Clean up created events
        if storage._pool:
            for event_id in created_ids:
                await storage._pool.execute(
                    "DELETE FROM episodic_events WHERE id = $1",
                    event_id,
                )

    @pytest.fixture
    async def cleanup_heuristics(self, storage):
        """Clean up test heuristics after tests."""
        created_ids = []
        yield created_ids
        # Clean up created heuristics
        if storage._pool:
            for h_id in created_ids:
                await storage._pool.execute(
                    "DELETE FROM heuristics WHERE id = $1",
                    h_id,
                )

    @pytest.mark.asyncio
    async def test_store_event(self, servicer, cleanup_events):
        """Test storing an event via gRPC."""
        event_id = uuid4()
        cleanup_events.append(event_id)

        embedding = np.random.randn(384).astype(np.float32)
        salience = types_pb2.SalienceVector(
            threat=0.1,
            novelty=0.8,
            goal_relevance=0.5,
        )
        event = memory_pb2.EpisodicEvent(
            id=str(event_id),
            timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
            source="test",
            raw_text="Test event for gRPC",
            embedding=_embedding_to_bytes(embedding),
            salience=salience,
            structured_json=json.dumps({"test": True}),
        )

        request = memory_pb2.StoreEventRequest(event=event)
        response = await servicer.StoreEvent(request, None)

        assert response.success is True
        assert response.error == ""

    @pytest.mark.asyncio
    async def test_query_by_time(self, servicer, storage, cleanup_events):
        """Test querying events by time range."""
        # Store a test event
        event_id = uuid4()
        cleanup_events.append(event_id)
        now = datetime.now(timezone.utc)

        event = EpisodicEvent(
            id=event_id,
            timestamp=now,
            source="test",
            raw_text="Time query test event",
            embedding=np.random.randn(384).astype(np.float32),
        )
        await storage.store_event(event)

        # Query via gRPC
        start_ms = int((now.timestamp() - 3600) * 1000)  # 1 hour ago
        end_ms = int((now.timestamp() + 3600) * 1000)  # 1 hour from now

        request = memory_pb2.QueryByTimeRequest(
            start_ms=start_ms,
            end_ms=end_ms,
            source_filter="test",
            limit=10,
        )
        response = await servicer.QueryByTime(request, None)

        assert response.error == ""
        assert len(response.events) >= 1
        # Find our event
        found = any(e.id == str(event_id) for e in response.events)
        assert found, f"Event {event_id} not found in results"

    @pytest.mark.asyncio
    async def test_query_by_similarity(self, servicer, storage, embeddings, cleanup_events):
        """Test querying events by embedding similarity."""
        # Store a test event with known embedding
        event_id = uuid4()
        cleanup_events.append(event_id)
        now = datetime.now(timezone.utc)

        text = "The quick brown fox jumps over the lazy dog"
        embedding = embeddings.generate(text)

        event = EpisodicEvent(
            id=event_id,
            timestamp=now,
            source="test",
            raw_text=text,
            embedding=embedding,
        )
        await storage.store_event(event)

        # Query with similar text
        similar_text = "A fast brown fox leaps over a sleepy dog"
        query_embedding = embeddings.generate(similar_text)

        request = memory_pb2.QueryBySimilarityRequest(
            query_embedding=_embedding_to_bytes(query_embedding),
            similarity_threshold=0.5,
            limit=10,
        )
        response = await servicer.QueryBySimilarity(request, None)

        assert response.error == ""
        # Should find at least our event (similarity should be high)
        found_ids = [e.id for e in response.events]
        assert str(event_id) in found_ids, f"Event {event_id} not found in similar results"

    @pytest.mark.asyncio
    async def test_query_by_similarity_no_embedding(self, servicer):
        """Test querying with no embedding returns error."""
        request = memory_pb2.QueryBySimilarityRequest(
            query_embedding=b"",
            similarity_threshold=0.5,
            limit=10,
        )
        response = await servicer.QueryBySimilarity(request, None)

        assert response.error == "No query embedding provided"

    @pytest.mark.asyncio
    async def test_generate_embedding(self, servicer):
        """Test embedding generation via gRPC."""
        request = memory_pb2.GenerateEmbeddingRequest(
            text="Hello, world!"
        )
        response = await servicer.GenerateEmbedding(request, None)

        assert response.error == ""
        embedding = _bytes_to_embedding(response.embedding)
        assert embedding is not None
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_text(self, servicer):
        """Test embedding generation with empty text returns error."""
        request = memory_pb2.GenerateEmbeddingRequest(text="")
        response = await servicer.GenerateEmbedding(request, None)

        assert response.error == "No text provided"

    @pytest.mark.asyncio
    async def test_store_heuristic(self, servicer, cleanup_heuristics):
        """Test storing a heuristic via gRPC."""
        h_id = uuid4()
        cleanup_heuristics.append(h_id)

        heuristic = memory_pb2.Heuristic(
            id=str(h_id),
            name="test_heuristic",
            condition_text="greeting hello wave",
            effects_json=json.dumps({"response": "wave"}),
            confidence=0.8,
            origin="test",
        )

        request = memory_pb2.StoreHeuristicRequest(heuristic=heuristic)
        response = await servicer.StoreHeuristic(request, None)

        assert response.success is True
        assert response.error == ""

    @pytest.mark.asyncio
    async def test_query_heuristics(self, servicer, storage, cleanup_heuristics):
        """Test querying heuristics via gRPC."""
        # Store a test heuristic
        h_id = uuid4()
        cleanup_heuristics.append(h_id)

        await storage.store_heuristic(
            id=h_id,
            name="query_test_heuristic",
            condition={"trigger": "test"},
            action={"do": "something"},
            confidence=0.9,
        )

        # Query via gRPC
        request = memory_pb2.QueryHeuristicsRequest(min_confidence=0.5)
        response = await servicer.QueryHeuristics(request, None)

        assert response.error == ""
        # Find our heuristic in matches (CBR schema returns HeuristicMatch)
        found = any(m.heuristic.id == str(h_id) for m in response.matches)
        assert found, f"Heuristic {h_id} not found in results"

    @pytest.mark.asyncio
    async def test_query_heuristics_confidence_filter(self, servicer, storage, cleanup_heuristics):
        """Test heuristic query respects confidence threshold."""
        # Store low-confidence heuristic
        h_id = uuid4()
        cleanup_heuristics.append(h_id)

        await storage.store_heuristic(
            id=h_id,
            name="low_confidence_heuristic",
            condition={"trigger": "low"},
            action={"do": "maybe"},
            confidence=0.2,
        )

        # Query with high threshold
        request = memory_pb2.QueryHeuristicsRequest(min_confidence=0.8)
        response = await servicer.QueryHeuristics(request, None)

        assert response.error == ""
        # Our low-confidence heuristic should NOT be found
        found = any(m.heuristic.id == str(h_id) for m in response.matches)
        assert not found, f"Low-confidence heuristic {h_id} should not be in results"
