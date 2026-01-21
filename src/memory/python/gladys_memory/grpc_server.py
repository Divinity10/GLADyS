"""gRPC server for Memory Storage service."""

import asyncio
import json
import struct
from concurrent import futures
from datetime import datetime, timezone
from uuid import UUID

import grpc
import numpy as np

from .storage import MemoryStorage, EpisodicEvent, StorageConfig
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
        """Store or update a heuristic."""
        try:
            h = request.heuristic
            condition = json.loads(h.condition_json) if h.condition_json else {}
            action = json.loads(h.action_json) if h.action_json else {}

            await self.storage.store_heuristic(
                id=UUID(h.id),
                name=h.name,
                condition=condition,
                action=action,
                confidence=h.confidence,
            )
            return memory_pb2.StoreHeuristicResponse(success=True)
        except Exception as e:
            return memory_pb2.StoreHeuristicResponse(success=False, error=str(e))

    async def QueryHeuristics(self, request, context):
        """Query heuristics by condition match."""
        try:
            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.0

            results = await self.storage.query_heuristics(min_confidence=min_confidence)

            proto_heuristics = []
            for h in results:
                proto_h = memory_pb2.Heuristic(
                    id=str(h["id"]),
                    name=h["name"],
                    condition_json=json.dumps(h["condition"]),
                    action_json=json.dumps(h["action"]),
                    confidence=h["confidence"],
                    last_fired_ms=int(h["last_fired"].timestamp() * 1000) if h["last_fired"] else 0,
                    fire_count=h["fire_count"],
                    success_count=h["success_count"],
                )
                proto_heuristics.append(proto_h)

            return memory_pb2.QueryHeuristicsResponse(heuristics=proto_heuristics)
        except Exception as e:
            return memory_pb2.QueryHeuristicsResponse(error=str(e))


async def serve(
    host: str = "0.0.0.0",
    port: int = 50051,
    storage_config: StorageConfig | None = None,
) -> None:
    """Start the gRPC server."""
    # Initialize components
    storage = MemoryStorage(storage_config)
    await storage.connect()
    print(f"Connected to PostgreSQL at {storage.config.host}:{storage.config.port}")

    embeddings = EmbeddingGenerator()
    print("Embedding generator initialized")

    # Create gRPC server
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add servicer
    memory_pb2_grpc.add_MemoryStorageServicer_to_server(
        MemoryStorageServicer(storage, embeddings),
        server,
    )

    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"Memory Storage gRPC server started on {host}:{port}")

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
