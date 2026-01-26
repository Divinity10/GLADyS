#!/usr/bin/env python3
"""Integration tests for cache management commands.

Tests the cache management RPCs on the Rust SalienceGateway (port 50052):
- GetCacheStats
- ListCachedHeuristics
- FlushCache
- EvictFromCache

Prerequisites:
  python scripts/local.py start memory-python memory-rust
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import grpc
import pytest

# Add paths for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

from gladys_orchestrator.generated import memory_pb2
from gladys_orchestrator.generated import memory_pb2_grpc


# Service addresses
MEMORY_STORAGE_ADDRESS = os.environ.get("MEMORY_STORAGE_ADDRESS", "localhost:50051")
SALIENCE_GATEWAY_ADDRESS = os.environ.get("SALIENCE_GATEWAY_ADDRESS", "localhost:50052")


@pytest.fixture
async def salience_stub():
    """Create a SalienceGateway stub for each test."""
    channel = grpc.aio.insecure_channel(SALIENCE_GATEWAY_ADDRESS)
    stub = memory_pb2_grpc.SalienceGatewayStub(channel)
    yield stub
    await channel.close()


@pytest.fixture
async def storage_stub():
    """Create a MemoryStorage stub for each test."""
    channel = grpc.aio.insecure_channel(MEMORY_STORAGE_ADDRESS)
    stub = memory_pb2_grpc.MemoryStorageStub(channel)
    yield stub
    await channel.close()


async def create_test_heuristic(storage_stub, name_suffix="") -> str:
    """Create a test heuristic and return its ID."""
    heuristic_id = str(uuid4())
    heuristic = memory_pb2.Heuristic(
        id=heuristic_id,
        name=f"cache_test_heuristic{name_suffix}",
        condition_text=f"test condition {name_suffix} {uuid4()}",
        effects_json=json.dumps({"salience": {"threat": 0.5}}),
        confidence=0.9,
        origin="test",
    )
    request = memory_pb2.StoreHeuristicRequest(heuristic=heuristic)
    response = await storage_stub.StoreHeuristic(request)
    assert response.success, f"Failed to create heuristic: {response.error}"
    return heuristic_id


async def trigger_cache_population(salience_stub, storage_stub) -> str:
    """Create a heuristic and trigger cache population via EvaluateSalience."""
    # Create a unique heuristic
    heuristic_id = await create_test_heuristic(storage_stub, f"_{uuid4().hex[:8]}")

    # Query to populate cache - use empty source to avoid filter issues
    request = memory_pb2.EvaluateSalienceRequest(
        event_id=str(uuid4()),
        source="",
        raw_text=f"test condition _{heuristic_id[:8]}",  # Match the condition
    )
    await salience_stub.EvaluateSalience(request)
    return heuristic_id


class TestCacheStats:
    """Tests for GetCacheStats RPC."""

    async def test_cache_stats_returns_valid_response(self, salience_stub):
        """GetCacheStats should return valid statistics."""
        response = await salience_stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())

        # Check response has expected fields
        assert hasattr(response, "current_size")
        assert hasattr(response, "max_capacity")
        assert hasattr(response, "hit_rate")
        assert hasattr(response, "total_hits")
        assert hasattr(response, "total_misses")

        # Capacity should be reasonable
        assert response.max_capacity > 0
        assert response.current_size >= 0
        assert response.current_size <= response.max_capacity

        # Hit rate should be valid percentage
        assert 0.0 <= response.hit_rate <= 1.0

        print(f"Cache stats: size={response.current_size}/{response.max_capacity}, "
              f"hit_rate={response.hit_rate:.2%}")


class TestCacheList:
    """Tests for ListCachedHeuristics RPC."""

    async def test_list_empty_cache(self, salience_stub):
        """ListCachedHeuristics on empty cache should return empty list."""
        # First flush to ensure empty
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())

        response = await salience_stub.ListCachedHeuristics(
            memory_pb2.ListCachedHeuristicsRequest(limit=10)
        )
        assert len(response.heuristics) == 0

    async def test_list_after_population(self, salience_stub, storage_stub):
        """ListCachedHeuristics should show cached heuristics."""
        # Ensure empty cache
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())

        # Populate cache
        heuristic_id = await trigger_cache_population(salience_stub, storage_stub)

        # List should now show entries
        response = await salience_stub.ListCachedHeuristics(
            memory_pb2.ListCachedHeuristicsRequest(limit=10)
        )

        # Should have at least one entry
        assert len(response.heuristics) >= 1

        # Each entry should have required fields
        for h in response.heuristics:
            assert h.heuristic_id
            assert h.name
            assert hasattr(h, "hit_count")
            print(f"  Cached: {h.heuristic_id[:20]}... hits={h.hit_count} name={h.name}")


class TestCacheFlush:
    """Tests for FlushCache RPC."""

    async def test_flush_empty_cache(self, salience_stub):
        """FlushCache on empty cache should return 0."""
        # First flush to empty
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())

        # Second flush should return 0
        response = await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())
        assert response.entries_flushed == 0

    async def test_flush_populated_cache(self, salience_stub, storage_stub):
        """FlushCache should clear all entries."""
        # Ensure empty, then populate
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())
        await trigger_cache_population(salience_stub, storage_stub)

        # Get initial count
        stats_before = await salience_stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        assert stats_before.current_size > 0, "Cache should have entries"

        # Flush
        flush_response = await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())
        assert flush_response.entries_flushed > 0

        # Verify empty
        stats_after = await salience_stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        assert stats_after.current_size == 0

        print(f"Flushed {flush_response.entries_flushed} entries")


class TestCacheEvict:
    """Tests for EvictFromCache RPC."""

    async def test_evict_nonexistent(self, salience_stub):
        """EvictFromCache for unknown ID should return found=False."""
        fake_id = str(uuid4())
        response = await salience_stub.EvictFromCache(
            memory_pb2.EvictFromCacheRequest(heuristic_id=fake_id)
        )
        assert not response.found

    async def test_evict_existing(self, salience_stub, storage_stub):
        """EvictFromCache for cached heuristic should remove it."""
        # Ensure empty, then populate
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())
        heuristic_id = await trigger_cache_population(salience_stub, storage_stub)

        # Verify in cache
        list_response = await salience_stub.ListCachedHeuristics(
            memory_pb2.ListCachedHeuristicsRequest(limit=100)
        )
        cached_ids = [h.heuristic_id for h in list_response.heuristics]

        # Find one to evict (may not be exact ID due to semantic matching)
        if cached_ids:
            evict_id = cached_ids[0]

            # Evict
            evict_response = await salience_stub.EvictFromCache(
                memory_pb2.EvictFromCacheRequest(heuristic_id=evict_id)
            )
            assert evict_response.found, f"Expected to find {evict_id} in cache"

            # Verify removed
            list_after = await salience_stub.ListCachedHeuristics(
                memory_pb2.ListCachedHeuristicsRequest(limit=100)
            )
            remaining_ids = [h.heuristic_id for h in list_after.heuristics]
            assert evict_id not in remaining_ids

            print(f"Evicted {evict_id}")


class TestCacheHitTracking:
    """Tests for cache hit/miss tracking."""

    async def test_hit_rate_increases_on_repeat_queries(self, salience_stub, storage_stub):
        """Repeated queries for same heuristic should increase hit rate."""
        # Start fresh
        await salience_stub.FlushCache(memory_pb2.FlushCacheRequest())

        # Create and populate
        heuristic_id = await trigger_cache_population(salience_stub, storage_stub)

        # Get initial stats
        stats1 = await salience_stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        initial_hits = stats1.total_hits
        initial_misses = stats1.total_misses

        # Make repeated queries (should be cache hits)
        for _ in range(3):
            request = memory_pb2.EvaluateSalienceRequest(
                event_id=str(uuid4()),
                source="",
                raw_text=f"test condition _{heuristic_id[:8]}",
            )
            await salience_stub.EvaluateSalience(request)

        # Check hits increased
        stats2 = await salience_stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        assert stats2.total_hits > initial_hits, "Hits should increase"
        assert stats2.total_misses >= initial_misses, "Misses should not decrease"

        print(f"Hits: {initial_hits} -> {stats2.total_hits}")
        print(f"Hit rate: {stats2.hit_rate:.2%}")
