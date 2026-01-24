"""gRPC server for Memory Storage service."""

import asyncio
import json
import logging
import struct
from concurrent import futures
from datetime import datetime, timezone
from uuid import UUID

import grpc
import numpy as np

logger = logging.getLogger(__name__)

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
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

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
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def QueryBySimilarity(self, request, context):
        """Query events by embedding similarity."""
        try:
            query_embedding = _bytes_to_embedding(request.query_embedding)
            if query_embedding is None:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No query embedding provided")

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
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GenerateEmbedding(self, request, context):
        """Generate embedding for text."""
        try:
            if not request.text:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No text provided")

            embedding = self.embeddings.generate(request.text)
            return memory_pb2.GenerateEmbeddingResponse(
                embedding=_embedding_to_bytes(embedding)
            )
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

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
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

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
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def QueryMatchingHeuristics(self, request, context):
        """Query heuristics using PostgreSQL text search.

        Used by Rust fast path on cache miss. Faster than embedding similarity
        because it uses tsvector/tsquery for word-overlap matching.
        """
        try:
            event_text = request.event_text
            if not event_text:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No event_text provided")

            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.0
            limit = request.limit if request.limit > 0 else 10

            results = await self.storage.query_matching_heuristics(
                event_text=event_text,
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

                # Use text search rank as similarity proxy
                rank = h.get("rank", 0.0)
                score = rank * h["confidence"]

                match = memory_pb2.HeuristicMatch(
                    heuristic=proto_h,
                    similarity=rank,
                    score=score,
                )
                matches.append(match)

            return memory_pb2.QueryHeuristicsResponse(matches=matches)
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def UpdateHeuristicConfidence(self, request, context):
        """Update heuristic confidence based on feedback (TD learning).

        Implements the TD learning formula:
        new_confidence = clamp(old_confidence + learning_rate * delta, 0, 1)

        where delta = +1.0 for positive feedback, -1.0 for negative.
        """
        try:
            heuristic_id = request.heuristic_id
            if not heuristic_id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No heuristic_id provided")

            # Use provided learning_rate or None to use heuristic's stored rate
            learning_rate = request.learning_rate if request.learning_rate > 0 else None

            old_conf, new_conf, delta = await self.storage.update_heuristic_confidence(
                heuristic_id=UUID(heuristic_id),
                positive=request.positive,
                learning_rate=learning_rate,
            )

            logger.info(
                f"TD_LEARNING: heuristic={heuristic_id}, "
                f"positive={request.positive}, "
                f"old={old_conf:.3f}, new={new_conf:.3f}, delta={delta:.3f}"
            )

            return memory_pb2.UpdateHeuristicConfidenceResponse(
                success=True,
                old_confidence=old_conf,
                new_confidence=new_conf,
                delta=delta,
            )
        except ValueError as e:
            # Heuristic not found
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            logger.error(f"UpdateHeuristicConfidence error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    # =========================================================================
    # Semantic Memory: Entities
    # =========================================================================

    async def StoreEntity(self, request, context):
        """Store or update an entity."""
        try:
            e = request.entity
            entity_id = UUID(e.id) if e.id else None
            if not entity_id:
                import uuid
                entity_id = uuid.uuid4()

            # Generate embedding if requested
            embedding = None
            if request.generate_embedding and e.canonical_name:
                # Combine name + type + attributes for embedding
                embed_text = f"{e.canonical_name} ({e.entity_type})"
                if e.attributes_json:
                    try:
                        attrs = json.loads(e.attributes_json)
                        if attrs:
                            embed_text += f" {' '.join(str(v) for v in attrs.values())}"
                    except json.JSONDecodeError:
                        pass
                embedding = self.embeddings.generate(embed_text)

            # Parse attributes
            attributes = {}
            if e.attributes_json:
                try:
                    attributes = json.loads(e.attributes_json)
                except json.JSONDecodeError:
                    attributes = {"raw": e.attributes_json}

            await self.storage.store_entity(
                id=entity_id,
                canonical_name=e.canonical_name,
                entity_type=e.entity_type,
                aliases=list(e.aliases) if e.aliases else [],
                attributes=attributes,
                embedding=embedding,
                source=e.source if e.source else None,
            )

            return memory_pb2.StoreEntityResponse(
                success=True,
                entity_id=str(entity_id),
            )
        except Exception as ex:
            await context.abort(grpc.StatusCode.INTERNAL, str(ex))

    async def QueryEntities(self, request, context):
        """Query entities by name, type, or embedding."""
        try:
            matches = []

            # Embedding similarity search
            if request.query_embedding:
                query_embedding = _bytes_to_embedding(request.query_embedding)
                min_similarity = request.min_similarity if request.min_similarity > 0 else 0.7
                limit = request.limit if request.limit > 0 else 10
                entity_type = request.entity_type if request.entity_type else None

                results = await self.storage.query_entities_by_similarity(
                    query_embedding=query_embedding,
                    min_similarity=min_similarity,
                    entity_type=entity_type,
                    limit=limit,
                )

                for entity_dict, similarity in results:
                    matches.append(memory_pb2.EntityMatch(
                        entity=self._entity_dict_to_proto(entity_dict),
                        similarity=similarity,
                    ))

            # Name-based search
            elif request.name_query:
                limit = request.limit if request.limit > 0 else 10
                entity_type = request.entity_type if request.entity_type else None

                results = await self.storage.query_entities_by_name(
                    name_query=request.name_query,
                    entity_type=entity_type,
                    limit=limit,
                )

                for entity_dict in results:
                    matches.append(memory_pb2.EntityMatch(
                        entity=self._entity_dict_to_proto(entity_dict),
                        similarity=1.0,  # Exact/prefix match
                    ))

            return memory_pb2.QueryEntitiesResponse(matches=matches)
        except Exception as ex:
            await context.abort(grpc.StatusCode.INTERNAL, str(ex))

    def _entity_dict_to_proto(self, entity_dict: dict) -> memory_pb2.Entity:
        """Convert entity dict to proto message."""
        return memory_pb2.Entity(
            id=str(entity_dict["id"]),
            canonical_name=entity_dict["canonical_name"],
            aliases=entity_dict.get("aliases", []),
            entity_type=entity_dict["entity_type"],
            attributes_json=json.dumps(entity_dict.get("attributes", {})),
            embedding=_embedding_to_bytes(entity_dict.get("embedding")),
            source=entity_dict.get("source") or "",
            first_seen_ms=int(entity_dict["first_seen"].timestamp() * 1000) if entity_dict.get("first_seen") else 0,
            last_seen_ms=int(entity_dict["last_seen"].timestamp() * 1000) if entity_dict.get("last_seen") else 0,
            mention_count=entity_dict.get("mention_count", 0),
            created_at_ms=int(entity_dict["created_at"].timestamp() * 1000) if entity_dict.get("created_at") else 0,
            updated_at_ms=int(entity_dict["updated_at"].timestamp() * 1000) if entity_dict.get("updated_at") else 0,
        )

    # =========================================================================
    # Semantic Memory: Relationships
    # =========================================================================

    async def StoreRelationship(self, request, context):
        """Store a relationship between entities."""
        try:
            r = request.relationship
            rel_id = UUID(r.id) if r.id else None
            if not rel_id:
                import uuid
                rel_id = uuid.uuid4()

            # Parse attributes
            attributes = {}
            if r.attributes_json:
                try:
                    attributes = json.loads(r.attributes_json)
                except json.JSONDecodeError:
                    attributes = {"raw": r.attributes_json}

            await self.storage.store_relationship(
                id=rel_id,
                subject_id=UUID(r.subject_id),
                predicate=r.predicate,
                object_id=UUID(r.object_id),
                attributes=attributes,
                confidence=r.confidence if r.confidence > 0 else 1.0,
                source=r.source if r.source else None,
                source_event_id=UUID(r.source_event_id) if r.source_event_id else None,
            )

            return memory_pb2.StoreRelationshipResponse(
                success=True,
                relationship_id=str(rel_id),
            )
        except Exception as ex:
            await context.abort(grpc.StatusCode.INTERNAL, str(ex))

    async def GetRelationships(self, request, context):
        """Get relationships for an entity."""
        try:
            entity_id = UUID(request.entity_id)
            predicate_filter = request.predicate_filter if request.predicate_filter else None
            # Proto3 doesn't have HasField for scalar types, use default values
            include_incoming = request.include_incoming if request.include_incoming else True
            include_outgoing = request.include_outgoing if request.include_outgoing else True
            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.0
            limit = request.limit if request.limit > 0 else 50

            results = await self.storage.get_relationships(
                entity_id=entity_id,
                predicate_filter=predicate_filter,
                include_incoming=include_incoming,
                include_outgoing=include_outgoing,
                min_confidence=min_confidence,
                limit=limit,
            )

            relationships = []
            for rel_data in results:
                rel = rel_data["relationship"]
                related = rel_data["related_entity"]

                relationships.append(memory_pb2.RelationshipWithEntity(
                    relationship=memory_pb2.Relationship(
                        id=str(rel["id"]),
                        subject_id=str(rel["subject_id"]),
                        predicate=rel["predicate"],
                        object_id=str(rel["object_id"]),
                        attributes_json=json.dumps(rel.get("attributes", {})),
                        confidence=rel["confidence"],
                        source=rel.get("source") or "",
                        source_event_id=str(rel["source_event_id"]) if rel.get("source_event_id") else "",
                        created_at_ms=int(rel["created_at"].timestamp() * 1000) if rel.get("created_at") else 0,
                        updated_at_ms=int(rel["updated_at"].timestamp() * 1000) if rel.get("updated_at") else 0,
                    ),
                    related_entity=memory_pb2.Entity(
                        id=str(related["id"]),
                        canonical_name=related["canonical_name"],
                        aliases=related.get("aliases", []),
                        entity_type=related["entity_type"],
                        attributes_json=json.dumps(related.get("attributes", {})),
                    ),
                ))

            return memory_pb2.GetRelationshipsResponse(relationships=relationships)
        except Exception as ex:
            await context.abort(grpc.StatusCode.INTERNAL, str(ex))

    async def ExpandContext(self, request, context):
        """Expand context for LLM prompts."""
        try:
            entity_ids = [UUID(eid) for eid in request.entity_ids]
            max_hops = request.max_hops if request.max_hops > 0 else 2
            max_hops = min(max_hops, 3)  # Cap at 3
            max_entities = request.max_entities if request.max_entities > 0 else 20
            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.5

            entities, relationships = await self.storage.expand_context(
                entity_ids=entity_ids,
                max_hops=max_hops,
                max_entities=max_entities,
                min_confidence=min_confidence,
            )

            proto_entities = [self._entity_dict_to_proto(e) for e in entities]
            proto_relationships = [
                memory_pb2.Relationship(
                    id=str(r["id"]),
                    subject_id=str(r["subject_id"]),
                    predicate=r["predicate"],
                    object_id=str(r["object_id"]),
                    attributes_json=json.dumps(r.get("attributes", {})),
                    confidence=r["confidence"],
                    source=r.get("source") or "",
                    source_event_id=str(r["source_event_id"]) if r.get("source_event_id") else "",
                    created_at_ms=int(r["created_at"].timestamp() * 1000) if r.get("created_at") else 0,
                    updated_at_ms=int(r["updated_at"].timestamp() * 1000) if r.get("updated_at") else 0,
                )
                for r in relationships
            ]

            return memory_pb2.ExpandContextResponse(
                entities=proto_entities,
                relationships=proto_relationships,
            )
        except Exception as ex:
            await context.abort(grpc.StatusCode.INTERNAL, str(ex))


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

    # Add servicer (SalienceGateway moved to Rust fast path)
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
