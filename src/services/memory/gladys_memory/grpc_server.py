"""gRPC server for Memory Storage service."""

import asyncio
import json
import struct
from concurrent import futures
from datetime import datetime, timezone
from uuid import UUID

import grpc
import numpy as np

from gladys_common import setup_logging, get_logger, bind_trace_id, get_or_create_trace_id

# Initialize logging (will be called again in serve() but safe to call multiple times)
setup_logging("memory-python")
logger = get_logger(__name__)

from .config import settings
from .storage import MemoryStorage, EpisodicEvent, StorageSettings
from .embeddings import EmbeddingGenerator
from . import memory_pb2
from . import memory_pb2_grpc
from . import types_pb2


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
    salience = types_pb2.SalienceVector()
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
        # Prediction instrumentation (§27)
        predicted_success=event.predicted_success or 0.0,
        prediction_confidence=event.prediction_confidence or 0.0,
        response_id=event.response_id or "",
        response_text=event.response_text or "",
        # Decision chain fields
        matched_heuristic_id=str(event.matched_heuristic_id) if event.matched_heuristic_id else "",
        llm_prompt_text=event.llm_prompt_text or "",
        decision_path=event.decision_path or "",
        episode_id=str(event.episode_id) if event.episode_id else "",
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
        # Prediction instrumentation (§27)
        predicted_success=proto.predicted_success if proto.predicted_success else None,
        prediction_confidence=proto.prediction_confidence if proto.prediction_confidence else None,
        response_id=proto.response_id if proto.response_id else None,
        response_text=proto.response_text if proto.response_text else None,
        # Decision chain fields
        llm_prompt_text=proto.llm_prompt_text if proto.llm_prompt_text else None,
        decision_path=proto.decision_path if proto.decision_path else None,
        matched_heuristic_id=UUID(proto.matched_heuristic_id) if proto.matched_heuristic_id else None,
        episode_id=UUID(proto.episode_id) if proto.episode_id else None,
    )


class MemoryStorageServicer(memory_pb2_grpc.MemoryStorageServicer):
    """gRPC servicer for Memory Storage."""

    def __init__(
        self,
        storage: MemoryStorage,
        embeddings: EmbeddingGenerator,
        salience_address: str | None = None,
    ):
        self.storage = storage
        self.embeddings = embeddings
        self._started_at = datetime.now(timezone.utc)
        self._salience_address = salience_address
        self._salience_channel = None
        self._salience_stub = None

    async def _notify_heuristic_change(self, heuristic_id: str, change_type: str):
        """Notify Rust SalienceGateway of a heuristic change for cache invalidation."""
        if not self._salience_address:
            return
        try:
            if self._salience_channel is None:
                self._salience_channel = grpc.aio.insecure_channel(self._salience_address)
                self._salience_stub = memory_pb2_grpc.SalienceGatewayStub(self._salience_channel)

            await self._salience_stub.NotifyHeuristicChange(
                memory_pb2.NotifyHeuristicChangeRequest(
                    heuristic_id=heuristic_id,
                    change_type=change_type,
                )
            )
            logger.debug(
                "Notified salience cache",
                heuristic_id=heuristic_id,
                change_type=change_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to notify salience cache (non-fatal)",
                heuristic_id=heuristic_id,
                change_type=change_type,
                error=str(e),
            )

    def _setup_trace(self, context) -> str:
        """Extract or generate trace ID and bind to logging context."""
        metadata = dict(context.invocation_metadata())
        trace_id = get_or_create_trace_id(metadata)
        bind_trace_id(trace_id)
        return trace_id

    async def StoreEvent(self, request, context):
        """Store a new episodic event."""
        self._setup_trace(context)
        logger.info("StoreEvent request", event_id=request.event.id if request.event else None)
        try:
            event = _proto_to_event(request.event)
            await self.storage.store_event(event)
            logger.info("StoreEvent success", event_id=request.event.id)
            return memory_pb2.StoreEventResponse(success=True)
        except Exception as e:
            logger.error("StoreEvent failed", error=str(e))
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

    async def ListEvents(self, request, context):
        """List recent events for dashboard."""
        self._setup_trace(context)
        logger.info(
            "ListEvents request",
            limit=request.limit,
            offset=request.offset,
            source=request.source or None,
        )
        try:
            limit = request.limit if request.limit > 0 else 50
            offset = request.offset if request.offset > 0 else 0
            source = request.source if request.source else None

            rows = await self.storage.list_events(
                limit=limit,
                offset=offset,
                source=source,
                include_archived=request.include_archived,
            )

            proto_events = []
            for row in rows:
                salience = types_pb2.SalienceVector()
                sal_data = row.get("salience")
                if isinstance(sal_data, dict):
                    salience.threat = sal_data.get("threat", 0.0)
                    salience.opportunity = sal_data.get("opportunity", 0.0)
                    salience.humor = sal_data.get("humor", 0.0)
                    salience.novelty = sal_data.get("novelty", 0.0)
                    salience.goal_relevance = sal_data.get("goal_relevance", 0.0)
                    salience.social = sal_data.get("social", 0.0)
                    salience.emotional = sal_data.get("emotional", 0.0)
                    salience.actionability = sal_data.get("actionability", 0.0)
                    salience.habituation = sal_data.get("habituation", 0.0)

                proto_events.append(memory_pb2.EpisodicEvent(
                    id=str(row["id"]),
                    timestamp_ms=int(row["timestamp"].timestamp() * 1000),
                    source=row["source"] or "",
                    raw_text=row["raw_text"] or "",
                    salience=salience,
                    predicted_success=float(row["predicted_success"]) if row.get("predicted_success") is not None else 0.0,
                    prediction_confidence=float(row["prediction_confidence"]) if row.get("prediction_confidence") is not None else 0.0,
                    response_id=row.get("response_id") or "",
                    response_text=row.get("response_text") or "",
                    matched_heuristic_id=str(row["matched_heuristic_id"]) if row.get("matched_heuristic_id") else "",
                    llm_prompt_text=row.get("llm_prompt_text") or "",
                    decision_path=row.get("decision_path") or "",
                    episode_id=str(row["episode_id"]) if row.get("episode_id") else "",
                ))

            logger.info("ListEvents success", count=len(proto_events))
            return memory_pb2.ListEventsResponse(events=proto_events)
        except Exception as e:
            logger.error("ListEvents failed", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetEvent(self, request, context):
        """Get a single event by ID."""
        self._setup_trace(context)
        logger.info("GetEvent request", event_id=request.event_id)
        try:
            if not request.event_id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No event_id provided")

            row = await self.storage.get_event(request.event_id)

            if not row:
                return memory_pb2.GetEventResponse(error="Event not found")

            salience = types_pb2.SalienceVector()
            sal_data = row.get("salience")
            if isinstance(sal_data, dict):
                salience.threat = sal_data.get("threat", 0.0)
                salience.opportunity = sal_data.get("opportunity", 0.0)
                salience.humor = sal_data.get("humor", 0.0)
                salience.novelty = sal_data.get("novelty", 0.0)
                salience.goal_relevance = sal_data.get("goal_relevance", 0.0)
                salience.social = sal_data.get("social", 0.0)
                salience.emotional = sal_data.get("emotional", 0.0)
                salience.actionability = sal_data.get("actionability", 0.0)
                salience.habituation = sal_data.get("habituation", 0.0)

            event = memory_pb2.EpisodicEvent(
                id=str(row["id"]),
                timestamp_ms=int(row["timestamp"].timestamp() * 1000),
                source=row["source"] or "",
                raw_text=row["raw_text"] or "",
                salience=salience,
                predicted_success=float(row["predicted_success"]) if row.get("predicted_success") is not None else 0.0,
                prediction_confidence=float(row["prediction_confidence"]) if row.get("prediction_confidence") is not None else 0.0,
                response_id=row.get("response_id") or "",
                response_text=row.get("response_text") or "",
                matched_heuristic_id=str(row["matched_heuristic_id"]) if row.get("matched_heuristic_id") else "",
                llm_prompt_text=row.get("llm_prompt_text") or "",
                decision_path=row.get("decision_path") or "",
                episode_id=str(row["episode_id"]) if row.get("episode_id") else "",
            )

            logger.info("GetEvent success", event_id=request.event_id)
            return memory_pb2.GetEventResponse(event=event)
        except Exception as e:
            logger.error("GetEvent failed", event_id=request.event_id, error=str(e))
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

        Always generates embedding for semantic matching when condition_text is provided.
        """
        self._setup_trace(context)
        h = request.heuristic
        logger.info("StoreHeuristic request", heuristic_id=h.id, name=h.name)
        try:
            h = request.heuristic

            # Build condition dict from condition_text
            # Origin is stored in dedicated column, not in condition JSONB
            condition = {"text": h.condition_text} if h.condition_text else {}

            # Parse effects_json into action dict
            action = {}
            if h.effects_json:
                try:
                    action = json.loads(h.effects_json)
                except json.JSONDecodeError:
                    action = {"raw": h.effects_json}

            # Warn if effects_json doesn't have canonical 'message' field
            if action and "message" not in action:
                logger.warning(
                    "StoreHeuristic: effects_json missing 'message' field",
                    heuristic_id=h.id,
                    available_keys=list(action.keys()),
                )

            # Always generate embedding for semantic matching
            # This is critical for correct heuristic matching
            condition_embedding = None
            if h.condition_text:
                condition_embedding = self.embeddings.generate(h.condition_text)
                logger.debug(f"Generated embedding for heuristic {h.id}: {len(condition_embedding)} dims")

            await self.storage.store_heuristic(
                id=UUID(h.id),
                name=h.name,
                condition=condition,
                action=action,
                confidence=h.confidence if h.confidence > 0 else 0.5,
                condition_embedding=condition_embedding,
                origin=h.origin or "learned",
                origin_id=h.origin_id or None,
            )
            logger.info("StoreHeuristic success", heuristic_id=h.id)

            # Notify Rust cache of new/updated heuristic
            await self._notify_heuristic_change(h.id, "created")

            return memory_pb2.StoreHeuristicResponse(
                success=True,
                heuristic_id=h.id,
            )
        except Exception as e:
            logger.error("StoreHeuristic failed", heuristic_id=h.id, error=str(e))
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
                    origin=h.get("origin", "learned"),
                    origin_id=h.get("origin_id", ""),
                    last_fired_ms=int(h["last_fired"].timestamp() * 1000) if h["last_fired"] else 0,
                    fire_count=h["fire_count"],
                    success_count=h["success_count"],
                    created_at_ms=int(h["created_at"].timestamp() * 1000) if h.get("created_at") else 0,
                    updated_at_ms=int(h["updated_at"].timestamp() * 1000) if h.get("updated_at") else 0,
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
        """Query heuristics using semantic similarity.

        Uses embedding-based similarity for accurate semantic matching.
        Falls back to text search only for heuristics without embeddings.
        """
        self._setup_trace(context)
        source_filter = request.source_filter if request.source_filter else None
        logger.info(
            "QueryMatchingHeuristics request",
            event_text_len=len(request.event_text) if request.event_text else 0,
            source_filter=source_filter,
        )
        try:
            event_text = request.event_text
            if not event_text:
                logger.warning("QueryMatchingHeuristics: no event_text provided")
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No event_text provided")

            min_confidence = request.min_confidence if request.min_confidence > 0 else 0.0
            limit = request.limit if request.limit > 0 else 10

            # Generate embedding for semantic matching
            query_embedding = self.embeddings.generate(event_text)

            results = await self.storage.query_matching_heuristics(
                event_text=event_text,
                min_confidence=min_confidence,
                limit=limit,
                source_filter=source_filter,
                query_embedding=query_embedding,
                min_similarity=settings.salience.heuristic_min_similarity,
            )
            logger.info("QueryMatchingHeuristics result", match_count=len(results))

            matches = []
            for h in results:
                condition = h.get("condition", {})
                action = h.get("action", {})

                # Include condition_embedding so Rust cache can do local similarity
                raw_embedding = h.get("condition_embedding")
                embedding_bytes = _embedding_to_bytes(raw_embedding) if raw_embedding is not None else b""

                proto_h = memory_pb2.Heuristic(
                    id=str(h["id"]),
                    name=h["name"],
                    condition_text=condition.get("text", ""),
                    condition_embedding=embedding_bytes,
                    effects_json=json.dumps(action),
                    confidence=h["confidence"],
                    origin=h.get("origin", "learned"),
                    origin_id=h.get("origin_id", ""),
                    last_fired_ms=int(h["last_fired"].timestamp() * 1000) if h["last_fired"] else 0,
                    fire_count=h["fire_count"],
                    success_count=h["success_count"],
                    created_at_ms=int(h["created_at"].timestamp() * 1000) if h.get("created_at") else 0,
                    updated_at_ms=int(h["updated_at"].timestamp() * 1000) if h.get("updated_at") else 0,
                )

                # Use semantic similarity (or text rank as fallback)
                similarity = h.get("similarity", 0.0)
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

    async def GetHeuristic(self, request, context):
        """Get a single heuristic by ID."""
        try:
            if not request.id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No id provided")

            heuristic = await self.storage.get_heuristic(UUID(request.id))

            if not heuristic:
                return memory_pb2.GetHeuristicResponse(error="Heuristic not found")

            proto_h = memory_pb2.Heuristic(
                id=str(heuristic["id"]),
                name=heuristic["name"],
                condition_text=heuristic["condition_text"],
                effects_json=heuristic.get("effects_json") or "{}",
                confidence=float(heuristic["confidence"]),
                origin=heuristic.get("origin") or "",
                success_count=heuristic.get("success_count") or 0,
            )
            return memory_pb2.GetHeuristicResponse(heuristic=proto_h)
        except Exception as e:
            logger.error(f"GetHeuristic error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def UpdateHeuristicConfidence(self, request, context):
        """Update heuristic confidence based on feedback (TD learning).

        Two modes:
        1. TD Learning (when predicted_success is provided):
           td_error = actual_outcome - predicted_success
           Enables "learn more from surprises"

        2. Simple mode (fallback):
           delta = +1.0 for positive, -1.0 for negative
        """
        try:
            heuristic_id = request.heuristic_id
            if not heuristic_id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No heuristic_id provided")

            # Use provided learning_rate or None to use default
            learning_rate = request.learning_rate if request.learning_rate > 0 else None

            # Check for TD learning mode (predicted_success provided)
            # In proto3, scalar fields always have a value (default 0.0).
            # We treat any non-zero value as intentionally set.
            # Note: This means we can't distinguish "not set" from "set to 0.0",
            # but a prediction of exactly 0.0 is rare (use 0.001 if needed).
            predicted_success = None
            if request.predicted_success != 0.0:
                predicted_success = request.predicted_success

            # Get feedback_source, default to 'explicit' if not provided
            feedback_source = request.feedback_source if request.feedback_source else "explicit"

            old_conf, new_conf, delta, td_error = await self.storage.update_heuristic_confidence(
                heuristic_id=UUID(heuristic_id),
                positive=request.positive,
                learning_rate=learning_rate,
                predicted_success=predicted_success,
                feedback_source=feedback_source,
            )

            # Log appropriately based on mode
            if td_error is not None:
                logger.info(
                    f"TD_LEARNING: heuristic={heuristic_id}, "
                    f"positive={request.positive}, predicted={predicted_success:.3f}, "
                    f"td_error={td_error:.3f}, old={old_conf:.3f}, new={new_conf:.3f}"
                )
            else:
                logger.info(
                    f"TD_LEARNING (simple): heuristic={heuristic_id}, "
                    f"positive={request.positive}, "
                    f"old={old_conf:.3f}, new={new_conf:.3f}, delta={delta:.3f}"
                )

            # Notify Rust cache of confidence change
            await self._notify_heuristic_change(heuristic_id, "updated")

            return memory_pb2.UpdateHeuristicConfidenceResponse(
                success=True,
                old_confidence=old_conf,
                new_confidence=new_conf,
                delta=delta,
                td_error=td_error if td_error is not None else 0.0,
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
                min_similarity = request.min_similarity if request.min_similarity > 0 else settings.salience.heuristic_min_similarity
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

    # =========================================================================
    # Response Tab Queries
    # =========================================================================

    async def ListResponses(self, request, context):
        """List events with decision chain data for Response tab."""
        self._setup_trace(context)
        try:
            limit = request.limit if request.limit > 0 else 50
            offset = request.offset if request.offset > 0 else 0
            decision_path = request.decision_path if request.decision_path else None
            source = request.source if request.source else None
            search = request.search if request.search else None

            rows = await self.storage.list_responses(
                decision_path=decision_path,
                source=source,
                search=search,
                limit=limit,
                offset=offset,
            )

            summaries = []
            for row in rows:
                summaries.append(memory_pb2.ResponseSummary(
                    event_id=str(row["id"]),
                    timestamp_ms=int(row["timestamp"].timestamp() * 1000),
                    source=row["source"] or "",
                    raw_text=row["raw_text"] or "",
                    decision_path=row.get("decision_path") or "",
                    matched_heuristic_id=str(row["matched_heuristic_id"]) if row.get("matched_heuristic_id") else "",
                    matched_heuristic_condition=row.get("matched_heuristic_condition") or "",
                    response_text=row.get("response_text") or "",
                ))

            return memory_pb2.ListResponsesResponse(responses=summaries)
        except Exception as e:
            logger.error("ListResponses failed", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetResponseDetail(self, request, context):
        """Get full detail for one event (drill-down)."""
        self._setup_trace(context)
        try:
            if not request.event_id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No event_id provided")

            row = await self.storage.get_response_detail(request.event_id)
            if not row:
                return memory_pb2.GetResponseDetailResponse(error="Event not found")

            detail = memory_pb2.ResponseDetail(
                event_id=str(row["id"]),
                timestamp_ms=int(row["timestamp"].timestamp() * 1000),
                source=row["source"] or "",
                raw_text=row["raw_text"] or "",
                decision_path=row.get("decision_path") or "",
                matched_heuristic_id=str(row["matched_heuristic_id"]) if row.get("matched_heuristic_id") else "",
                matched_heuristic_condition=row.get("matched_heuristic_condition") or "",
                matched_heuristic_confidence=float(row["matched_heuristic_confidence"]) if row.get("matched_heuristic_confidence") is not None else 0.0,
                llm_prompt_text=row.get("llm_prompt_text") or "",
                response_text=row.get("response_text") or "",
                fire_id=str(row["fire_id"]) if row.get("fire_id") else "",
                feedback_source=row.get("feedback_source") or "",
                outcome=row.get("outcome") or "",
            )

            return memory_pb2.GetResponseDetailResponse(detail=detail)
        except Exception as e:
            logger.error("GetResponseDetail failed", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def DeleteResponses(self, request, context):
        """Delete multiple events by ID (dashboard bulk delete)."""
        self._setup_trace(context)
        try:
            if not request.event_ids:
                return memory_pb2.DeleteResponsesResponse(deleted_count=0)

            # Convert string IDs to UUIDs
            event_uuids = [UUID(eid) for eid in request.event_ids]

            deleted_count = await self.storage.delete_events(event_uuids)
            logger.info("DeleteResponses success", count=deleted_count, requested=len(event_uuids))

            return memory_pb2.DeleteResponsesResponse(deleted_count=deleted_count)
        except ValueError as e:
            logger.error("DeleteResponses invalid UUID", error=str(e))
            return memory_pb2.DeleteResponsesResponse(deleted_count=0, error=f"Invalid event ID: {e}")
        except Exception as e:
            logger.error("DeleteResponses failed", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    # =========================================================================
    # Heuristic Fire Tracking ("Flight Recorder")
    # =========================================================================

    async def RecordHeuristicFire(self, request, context):
        """Record that a heuristic fired."""
        try:
            heuristic_id = request.heuristic_id
            if not heuristic_id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No heuristic_id provided")

            fire_id = await self.storage.record_heuristic_fire(
                heuristic_id=UUID(heuristic_id),
                event_id=request.event_id,
                episodic_event_id=UUID(request.episodic_event_id) if request.episodic_event_id else None
            )
            return memory_pb2.RecordHeuristicFireResponse(fire_id=str(fire_id))
        except Exception as e:
            logger.error(f"RecordHeuristicFire error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def UpdateFireOutcome(self, request, context):
        """Update a fire record with outcome."""
        try:
            success = await self.storage.update_fire_outcome(
                fire_id=UUID(request.fire_id),
                outcome=request.outcome,
                feedback_source=request.feedback_source
            )
            return memory_pb2.UpdateFireOutcomeResponse(success=success)
        except Exception as e:
            logger.error(f"UpdateFireOutcome error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetPendingFires(self, request, context):
        """Get fires awaiting feedback."""
        try:
            h_id = UUID(request.heuristic_id) if request.heuristic_id else None
            max_age = request.max_age_seconds if request.max_age_seconds > 0 else 300
            
            fires = await self.storage.get_pending_fires(h_id, max_age)
            
            proto_fires = [
                memory_pb2.HeuristicFire(
                    id=str(f["id"]),
                    heuristic_id=str(f["heuristic_id"]),
                    event_id=f["event_id"],
                    fired_at_ms=int(f["fired_at"].timestamp() * 1000),
                    outcome=f["outcome"],
                    feedback_source=f["feedback_source"] or "",
                    episodic_event_id=str(f["episodic_event_id"]) if f["episodic_event_id"] else ""
                )
                for f in fires
            ]
            return memory_pb2.GetPendingFiresResponse(fires=proto_fires)
        except Exception as e:
            logger.error(f"GetPendingFires error: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def ListFires(
        self,
        request: memory_pb2.ListFiresRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.ListFiresResponse:
        """List heuristic fires with optional filtering."""
        try:
            outcome = request.outcome if request.outcome else None
            limit = request.limit if request.limit > 0 else 100
            offset = request.offset if request.offset >= 0 else 0

            fires, total = await self.storage.list_fires(
                outcome=outcome,
                limit=limit,
                offset=offset,
            )

            # Convert to proto
            fire_protos = []
            for f in fires:
                fire_proto = memory_pb2.HeuristicFire(
                    id=str(f["id"]),
                    heuristic_id=str(f["heuristic_id"]) if f["heuristic_id"] else "",
                    event_id=str(f["event_id"]) if f["event_id"] else "",
                    outcome=f["outcome"] or "",
                    feedback_source=f["feedback_source"] or "",
                    heuristic_name=f["heuristic_name"] or "",
                    condition_text=f["condition_text"] or "",
                    confidence=float(f["confidence"]) if f["confidence"] is not None else 0.0,
                )
                # Set fired_at if present
                if f["fired_at"]:
                    fire_proto.fired_at_ms = int(f["fired_at"].timestamp() * 1000)
                fire_protos.append(fire_proto)

            return memory_pb2.ListFiresResponse(
                fires=fire_protos,
                total_count=total,
            )

        except Exception as e:
            logger.error(f"ListFires failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return memory_pb2.ListFiresResponse()

    async def GetHealth(self, request, context):
        """Basic health check."""
        return types_pb2.GetHealthResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            message=""
        )

    async def GetHealthDetails(self, request, context):
        """Detailed health check with uptime and metrics."""
        uptime = int((datetime.now(timezone.utc) - self._started_at).total_seconds())

        # Gather details from storage
        details = {
            "db_connected": "true" if self.storage._pool else "false",
            "embedding_model": settings.embedding.model_name,
        }

        return types_pb2.GetHealthDetailsResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            uptime_seconds=uptime,
            details=details
        )


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

    # Pre-warm the embedding model to avoid cold-start delays on first request
    print("Pre-warming embedding model...")
    embeddings.generate("warmup")
    print("Embedding model ready")

    # Create gRPC server
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=srv_cfg.max_workers))

    # Add servicer (SalienceGateway moved to Rust fast path)
    salience_address = srv_cfg.salience_address
    print(f"Cache invalidation notifications \u2192 {salience_address}")
    memory_pb2_grpc.add_MemoryStorageServicer_to_server(
        MemoryStorageServicer(storage, embeddings, salience_address=salience_address),
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
