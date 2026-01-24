"""gRPC server for Memory Storage service."""

import asyncio
import json
import struct
from concurrent import futures
from datetime import datetime, timezone
from uuid import UUID

import grpc
import numpy as np

from .config import settings
from .storage import MemoryStorage, EpisodicEvent, StorageSettings
from .embeddings import EmbeddingGenerator
from . import memory_pb2
from . import memory_pb2_grpc


def _bytes_to_embedding(data: bytes) -> np.ndarray:
    """Convert bytes to 384-dim float32 embedding."""
    if not data:
        return None
    return np.frombuffer(data, dtype=np.float32)


def _embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Convert 384-dim float32 embedding to bytes."""
    if embedding is None:
        return b""
    return embedding.astype(np.float32).tobytes()


def _event_to_proto(event: EpisodicEvent) -> memory_pb2.EpisodicEvent:
    """Convert EpisodicEvent to protobuf message."""
    salience = memory_pb2.SalienceVector()
    if event.salience:
        salience.threat = event.salience.get("threat", 0.0)
        salience.opportunity = event.salience.get("opportunity", 0.0)
        salience.humor = event.salience.get("humor", 0.0)
        salience.novelty = event.salience.get("novelty", 0.0)
        salience.goal_relevance = event.salience.get("goal_relevance", 0.0)
        salience.social = event.salience.get("social", 0.0)
        salience.emotional = event.salience.get("emotional", 0.0)
        salience.actionability = event.salience.get("actionability", 0.0)
        salience.habituation = event.salience.get("habituation", 0.0)

    return memory_pb2.EpisodicEvent(
        id=str(event.id),
        timestamp_ms=int(event.timestamp.timestamp() * 1000),
        source=event.source,
        raw_text=event.raw_text,
        embedding=_embedding_to_bytes(event.embedding),
        salience=salience,
        structured_json=json.dumps(event.structured) if event.structured else "{}",
        entity_ids=[str(eid) for eid in (event.entity_ids or [])],
    )


def _proto_to_event(proto: memory_pb2.EpisodicEvent) -> EpisodicEvent:
    """Convert protobuf message to EpisodicEvent."""
    salience = None
    if proto.salience:
        salience = {
            "threat": proto.salience.threat,
            "opportunity": proto.salience.opportunity,
            "humor": proto.salience.humor,
            "novelty": proto.salience.novelty,
            "goal_relevance": proto.salience.goal_relevance,
            "social": proto.salience.social,
            "emotional": proto.salience.emotional,
            "actionability": proto.salience.actionability,
            "habituation": proto.salience.habituation,
        }

    structured = None
    if proto.structured_json:
        try:
            structured = json.loads(proto.structured_json)
        except json.JSONDecodeError:
            structured = {}

    return EpisodicEvent(
        id=UUID(proto.id) if proto.id else None,
        timestamp=datetime.fromtimestamp(proto.timestamp_ms / 1000, tz=timezone.utc),
        source=proto.source,
        raw_text=proto.raw_text,
        embedding=_bytes_to_embedding(proto.embedding),
        salience=salience,
        structured=structured,
        entity_ids=[UUID(eid) for eid in proto.entity_ids] if proto.entity_ids else [],
    )


class SalienceGatewayServicer(memory_pb2_grpc.SalienceGatewayServicer):
    """gRPC servicer for Salience Gateway - the 'amygdala'.

    Co-located with Memory per ADR-0001 §5.1.
    Provides fast salience evaluation for incoming events.
    """

    def __init__(
        self,
        storage: MemoryStorage,
        embeddings: EmbeddingGenerator,
    ):
        self.storage = storage
        self.embeddings = embeddings
        # Heuristic cache for fast path (like Rust)
        self._heuristic_cache: list[dict] | None = None
        self._cache_loaded = False

    async def _get_heuristics(self, use_cache: bool = True) -> list[dict]:
        """Get heuristics, optionally from cache.

        When use_cache=True and cache exists, returns cached heuristics (fast).
        When use_cache=False or cache empty, queries DB and updates cache.
        """
        sal_cfg = settings.salience

        if use_cache and self._heuristic_cache is not None:
            return self._heuristic_cache

        # Query from DB
        heuristics = await self.storage.query_heuristics(
            min_confidence=sal_cfg.heuristic_min_confidence
        )

        # Update cache
        self._heuristic_cache = heuristics
        self._cache_loaded = True

        return heuristics

    async def EvaluateSalience(self, request, context):
        """Evaluate salience for an event.

        Uses heuristics from Memory + novelty detection.
        Returns salience vector with all dimensions.
        """
        sal_cfg = settings.salience

        # Use cache when novelty detection is skipped (benchmark mode)
        use_cache = request.skip_novelty_detection

        try:
            # Step 1: Check for matching heuristics
            matched_heuristic = None
            salience = self._default_salience()

            # Get heuristics (from cache if benchmarking, else from DB)
            heuristics = await self._get_heuristics(use_cache=use_cache)

            for h in heuristics:
                if self._heuristic_matches(h, request):
                    matched_heuristic = h
                    # Apply heuristic's salience boost
                    salience = self._apply_heuristic_salience(salience, h)
                    break

            # Step 2: Novelty detection via embedding similarity
            # Skip if configured globally OR per-request (for benchmarking)
            skip_novelty = sal_cfg.skip_novelty_detection or request.skip_novelty_detection
            if request.raw_text and not skip_novelty:
                embedding = self.embeddings.generate(request.raw_text)
                # Check if similar events exist (low novelty) or not (high novelty)
                similar = await self.storage.query_by_similarity(
                    query_embedding=embedding,
                    threshold=sal_cfg.novelty_similarity_threshold,
                    hours=sal_cfg.novelty_time_window_hours,
                    limit=sal_cfg.novelty_similar_limit,
                )
                if len(similar) == 0:
                    # Novel event - boost novelty
                    salience["novelty"] = max(salience["novelty"], sal_cfg.novelty_high_boost)
                elif len(similar) < 3:
                    # Somewhat novel
                    salience["novelty"] = max(salience["novelty"], sal_cfg.novelty_medium_boost)
                else:
                    # Common event - habituation
                    salience["habituation"] = min(0.8, salience["habituation"] + sal_cfg.habituation_boost)

            # Build response
            salience_proto = memory_pb2.SalienceVector(
                threat=salience["threat"],
                opportunity=salience["opportunity"],
                humor=salience["humor"],
                novelty=salience["novelty"],
                goal_relevance=salience["goal_relevance"],
                social=salience["social"],
                emotional=salience["emotional"],
                actionability=salience["actionability"],
                habituation=salience["habituation"],
            )

            return memory_pb2.EvaluateSalienceResponse(
                salience=salience_proto,
                from_cache=matched_heuristic is not None,
                matched_heuristic_id=str(matched_heuristic["id"]) if matched_heuristic else "",
                novelty_detection_skipped=skip_novelty,
            )

        except Exception as e:
            return memory_pb2.EvaluateSalienceResponse(error=str(e))

    def _default_salience(self) -> dict:
        """Default salience values."""
        return {
            "threat": 0.0,
            "opportunity": 0.0,
            "humor": 0.0,
            "novelty": 0.1,
            "goal_relevance": 0.0,
            "social": 0.0,
            "emotional": 0.0,
            "actionability": 0.0,
            "habituation": 0.0,
        }

    def _heuristic_matches(self, heuristic: dict, request) -> bool:
        """Check if a heuristic matches the request context.

        Supports both old format (source/keywords) and new CBR format (text).
        True CBR matching would use embedding similarity.
        """
        sal_cfg = settings.salience
        condition = heuristic.get("condition", {})

        # New CBR format: match by text keywords
        if "text" in condition:
            condition_text = condition["text"].lower()
            request_text = request.raw_text.lower()
            # Simple word overlap matching (placeholder for embedding similarity)
            condition_words = set(condition_text.split())
            request_words = set(request_text.split())
            overlap = condition_words & request_words
            # Match if at least N words overlap or X% of condition words
            min_overlap = max(
                sal_cfg.word_overlap_min,
                int(len(condition_words) * sal_cfg.word_overlap_ratio)
            )
            return len(overlap) >= min_overlap

        # Old format: Match by source
        if "source" in condition:
            if condition["source"] != request.source:
                return False

        # Old format: Match by keywords in raw_text
        if "keywords" in condition:
            keywords = condition["keywords"]
            if isinstance(keywords, list):
                text_lower = request.raw_text.lower()
                if not any(kw.lower() in text_lower for kw in keywords):
                    return False

        return True

    def _apply_heuristic_salience(self, salience: dict, heuristic: dict) -> dict:
        """Apply salience modifiers from a matched heuristic."""
        action = heuristic.get("action", {})
        salience_boost = action.get("salience", {})

        for key, value in salience_boost.items():
            if key in salience:
                salience[key] = max(salience[key], value)

        return salience


class MemoryStorageServicer(memory_pb2_grpc.MemoryStorageServicer):
    """gRPC servicer for Memory Storage."""

    def __init__(
        self,
        storage: MemoryStorage,
        embeddings: EmbeddingGenerator,
    ):
        self.storage = storage
        self.embeddings = embeddings

    async def StoreEvent(self, request, context):
        """Store a new episodic event."""
        try:
            event = _proto_to_event(request.event)
            await self.storage.store_event(event)
            return memory_pb2.StoreEventResponse(success=True)
        except Exception as e:
            return memory_pb2.StoreEventResponse(success=False, error=str(e))

    async def QueryByTime(self, request, context):
        """Query events by time range."""
        try:
            start = datetime.fromtimestamp(request.start_ms / 1000, tz=timezone.utc)
            end = datetime.fromtimestamp(request.end_ms / 1000, tz=timezone.utc)
            source = request.source_filter if request.source_filter else None
            limit = request.limit if request.limit > 0 else 100

            events = await self.storage.query_by_time(
                start=start,
                end=end,
                source=source,
                limit=limit,
            )

            proto_events = [_event_to_proto(e) for e in events]
            return memory_pb2.QueryEventsResponse(events=proto_events)
        except Exception as e:
            return memory_pb2.QueryEventsResponse(error=str(e))

    async def QueryBySimilarity(self, request, context):
        """Query events by embedding similarity."""
        try:
            query_embedding = _bytes_to_embedding(request.query_embedding)
            if query_embedding is None:
                return memory_pb2.QueryEventsResponse(error="No query embedding provided")

            threshold = request.similarity_threshold if request.similarity_threshold > 0 else 0.7
            hours = request.time_filter_hours if request.time_filter_hours > 0 else None
            limit = request.limit if request.limit > 0 else 10

            results = await self.storage.query_by_similarity(
                query_embedding=query_embedding,
                threshold=threshold,
                hours=hours,
                limit=limit,
            )

            proto_events = [_event_to_proto(e) for e, _ in results]
            return memory_pb2.QueryEventsResponse(events=proto_events)
        except Exception as e:
            return memory_pb2.QueryEventsResponse(error=str(e))

    async def GenerateEmbedding(self, request, context):
        """Generate embedding for text."""
        try:
            if not request.text:
                return memory_pb2.GenerateEmbeddingResponse(error="No text provided")

            embedding = self.embeddings.generate(request.text)
            return memory_pb2.GenerateEmbeddingResponse(
                embedding=_embedding_to_bytes(embedding)
            )
        except Exception as e:
            return memory_pb2.GenerateEmbeddingResponse(error=str(e))

    async def StoreHeuristic(self, request, context):
        """Store or update a heuristic.

        New CBR schema uses condition_text and effects_json.
        Maps to DB columns: condition (JSONB), action (JSONB).
        """
        try:
            h = request.heuristic

            # Build condition dict from condition_text
            # Store as {"text": "...", "origin": "..."} for CBR matching
            condition = {"text": h.condition_text} if h.condition_text else {}
            if h.origin:
                condition["origin"] = h.origin

            # Parse effects_json into action dict
            action = {}
            if h.effects_json:
                try:
                    action = json.loads(h.effects_json)
                except json.JSONDecodeError:
                    action = {"raw": h.effects_json}

            # Generate embedding if requested (for future CBR similarity matching)
            # Note: DB schema doesn't have condition_embedding column yet
            if request.generate_embedding and h.condition_text:
                _embedding = self.embeddings.generate(h.condition_text)
                # Would store embedding here when column exists

            await self.storage.store_heuristic(
                id=UUID(h.id),
                name=h.name,
                condition=condition,
                action=action,
                confidence=h.confidence if h.confidence > 0 else 0.5,
            )
            return memory_pb2.StoreHeuristicResponse(
                success=True,
                heuristic_id=h.id,
            )
        except Exception as e:
            return memory_pb2.StoreHeuristicResponse(success=False, error=str(e))

    async def QueryHeuristics(self, request, context):
        """Query heuristics with CBR matching.

        New CBR schema returns HeuristicMatch with similarity scores.
        For now, similarity is 1.0 (keyword match) until embedding-based
        similarity is implemented with condition_embedding column.
        """
        try:
            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.0
            limit = request.limit if request.limit > 0 else 100

            results = await self.storage.query_heuristics(
                min_confidence=min_confidence,
                limit=limit,
            )

            matches = []
            for h in results:
                condition = h.get("condition", {})
                action = h.get("action", {})

                proto_h = memory_pb2.Heuristic(
                    id=str(h["id"]),
                    name=h["name"],
                    condition_text=condition.get("text", ""),
                    effects_json=json.dumps(action),
                    confidence=h["confidence"],
                    origin=condition.get("origin", ""),
                    last_fired_ms=int(h["last_fired"].timestamp() * 1000) if h["last_fired"] else 0,
                    fire_count=h["fire_count"],
                    success_count=h["success_count"],
                )

                # For now, similarity = 1.0 (all returned heuristics "match")
                # True CBR matching would compute embedding similarity
                similarity = 1.0
                score = similarity * h["confidence"]

                match = memory_pb2.HeuristicMatch(
                    heuristic=proto_h,
                    similarity=similarity,
                    score=score,
                )
                matches.append(match)

            return memory_pb2.QueryHeuristicsResponse(matches=matches)
        except Exception as e:
            return memory_pb2.QueryHeuristicsResponse(error=str(e))


async def serve(
    host: str | None = None,
    port: int | None = None,
    storage_config: StorageSettings | None = None,
) -> None:
    """Start the gRPC server."""
    # Use config defaults if not specified
    srv_cfg = settings.server
    host = host or srv_cfg.host
    port = port or srv_cfg.port

    # Initialize components
    storage = MemoryStorage(storage_config)
    await storage.connect()
    print(f"Connected to PostgreSQL at {storage.config.host}:{storage.config.port}")

    embeddings = EmbeddingGenerator()
    print(f"Embedding generator initialized (model: {settings.embedding.model_name})")

    # Create gRPC server
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=srv_cfg.max_workers))

    # Add servicers
    memory_pb2_grpc.add_MemoryStorageServicer_to_server(
        MemoryStorageServicer(storage, embeddings),
        server,
    )
    memory_pb2_grpc.add_SalienceGatewayServicer_to_server(
        SalienceGatewayServicer(storage, embeddings),
        server,
    )

    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"Memory Storage + Salience Gateway gRPC server started on {host}:{port}")

    try:
        await server.wait_for_termination()
    finally:
        await storage.close()
        print("Server shutdown complete")


def main():
    """Entry point for running the server."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
