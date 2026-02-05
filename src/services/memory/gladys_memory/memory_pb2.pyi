import types_pb2 as _types_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class NotifyHeuristicChangeRequest(_message.Message):
    __slots__ = ("heuristic_id", "change_type")
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    CHANGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    change_type: str
    def __init__(self, heuristic_id: _Optional[str] = ..., change_type: _Optional[str] = ...) -> None: ...

class NotifyHeuristicChangeResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class FlushCacheRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FlushCacheResponse(_message.Message):
    __slots__ = ("entries_flushed",)
    ENTRIES_FLUSHED_FIELD_NUMBER: _ClassVar[int]
    entries_flushed: int
    def __init__(self, entries_flushed: _Optional[int] = ...) -> None: ...

class EvictFromCacheRequest(_message.Message):
    __slots__ = ("heuristic_id",)
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    def __init__(self, heuristic_id: _Optional[str] = ...) -> None: ...

class EvictFromCacheResponse(_message.Message):
    __slots__ = ("found",)
    FOUND_FIELD_NUMBER: _ClassVar[int]
    found: bool
    def __init__(self, found: bool = ...) -> None: ...

class GetCacheStatsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetCacheStatsResponse(_message.Message):
    __slots__ = ("current_size", "max_capacity", "hit_rate", "total_hits", "total_misses")
    CURRENT_SIZE_FIELD_NUMBER: _ClassVar[int]
    MAX_CAPACITY_FIELD_NUMBER: _ClassVar[int]
    HIT_RATE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_HITS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_MISSES_FIELD_NUMBER: _ClassVar[int]
    current_size: int
    max_capacity: int
    hit_rate: float
    total_hits: int
    total_misses: int
    def __init__(self, current_size: _Optional[int] = ..., max_capacity: _Optional[int] = ..., hit_rate: _Optional[float] = ..., total_hits: _Optional[int] = ..., total_misses: _Optional[int] = ...) -> None: ...

class ListCachedHeuristicsRequest(_message.Message):
    __slots__ = ("limit",)
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    limit: int
    def __init__(self, limit: _Optional[int] = ...) -> None: ...

class CachedHeuristicInfo(_message.Message):
    __slots__ = ("heuristic_id", "name", "hit_count", "cached_at_unix", "last_hit_unix")
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    HIT_COUNT_FIELD_NUMBER: _ClassVar[int]
    CACHED_AT_UNIX_FIELD_NUMBER: _ClassVar[int]
    LAST_HIT_UNIX_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    name: str
    hit_count: int
    cached_at_unix: int
    last_hit_unix: int
    def __init__(self, heuristic_id: _Optional[str] = ..., name: _Optional[str] = ..., hit_count: _Optional[int] = ..., cached_at_unix: _Optional[int] = ..., last_hit_unix: _Optional[int] = ...) -> None: ...

class ListCachedHeuristicsResponse(_message.Message):
    __slots__ = ("heuristics",)
    HEURISTICS_FIELD_NUMBER: _ClassVar[int]
    heuristics: _containers.RepeatedCompositeFieldContainer[CachedHeuristicInfo]
    def __init__(self, heuristics: _Optional[_Iterable[_Union[CachedHeuristicInfo, _Mapping]]] = ...) -> None: ...

class EpisodicEvent(_message.Message):
    __slots__ = ("id", "timestamp_ms", "source", "raw_text", "embedding", "salience", "structured_json", "entity_ids", "predicted_success", "prediction_confidence", "response_id", "response_text", "matched_heuristic_id", "llm_prompt_text", "decision_path", "episode_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    SALIENCE_FIELD_NUMBER: _ClassVar[int]
    STRUCTURED_JSON_FIELD_NUMBER: _ClassVar[int]
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    PREDICTED_SUCCESS_FIELD_NUMBER: _ClassVar[int]
    PREDICTION_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_ID_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    LLM_PROMPT_TEXT_FIELD_NUMBER: _ClassVar[int]
    DECISION_PATH_FIELD_NUMBER: _ClassVar[int]
    EPISODE_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    timestamp_ms: int
    source: str
    raw_text: str
    embedding: bytes
    salience: _types_pb2.SalienceVector
    structured_json: str
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    predicted_success: float
    prediction_confidence: float
    response_id: str
    response_text: str
    matched_heuristic_id: str
    llm_prompt_text: str
    decision_path: str
    episode_id: str
    def __init__(self, id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., embedding: _Optional[bytes] = ..., salience: _Optional[_Union[_types_pb2.SalienceVector, _Mapping]] = ..., structured_json: _Optional[str] = ..., entity_ids: _Optional[_Iterable[str]] = ..., predicted_success: _Optional[float] = ..., prediction_confidence: _Optional[float] = ..., response_id: _Optional[str] = ..., response_text: _Optional[str] = ..., matched_heuristic_id: _Optional[str] = ..., llm_prompt_text: _Optional[str] = ..., decision_path: _Optional[str] = ..., episode_id: _Optional[str] = ...) -> None: ...

class StoreEventRequest(_message.Message):
    __slots__ = ("event",)
    EVENT_FIELD_NUMBER: _ClassVar[int]
    event: EpisodicEvent
    def __init__(self, event: _Optional[_Union[EpisodicEvent, _Mapping]] = ...) -> None: ...

class StoreEventResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class QueryByTimeRequest(_message.Message):
    __slots__ = ("start_ms", "end_ms", "source_filter", "limit")
    START_MS_FIELD_NUMBER: _ClassVar[int]
    END_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FILTER_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    start_ms: int
    end_ms: int
    source_filter: str
    limit: int
    def __init__(self, start_ms: _Optional[int] = ..., end_ms: _Optional[int] = ..., source_filter: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class QueryBySimilarityRequest(_message.Message):
    __slots__ = ("query_embedding", "similarity_threshold", "time_filter_hours", "limit")
    QUERY_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    TIME_FILTER_HOURS_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    query_embedding: bytes
    similarity_threshold: float
    time_filter_hours: int
    limit: int
    def __init__(self, query_embedding: _Optional[bytes] = ..., similarity_threshold: _Optional[float] = ..., time_filter_hours: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class QueryEventsResponse(_message.Message):
    __slots__ = ("events", "error")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[EpisodicEvent]
    error: str
    def __init__(self, events: _Optional[_Iterable[_Union[EpisodicEvent, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class ListEventsRequest(_message.Message):
    __slots__ = ("limit", "offset", "source", "include_archived")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_ARCHIVED_FIELD_NUMBER: _ClassVar[int]
    limit: int
    offset: int
    source: str
    include_archived: bool
    def __init__(self, limit: _Optional[int] = ..., offset: _Optional[int] = ..., source: _Optional[str] = ..., include_archived: bool = ...) -> None: ...

class ListEventsResponse(_message.Message):
    __slots__ = ("events", "error")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[EpisodicEvent]
    error: str
    def __init__(self, events: _Optional[_Iterable[_Union[EpisodicEvent, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class GetEventRequest(_message.Message):
    __slots__ = ("event_id",)
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    def __init__(self, event_id: _Optional[str] = ...) -> None: ...

class GetEventResponse(_message.Message):
    __slots__ = ("event", "error")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    event: EpisodicEvent
    error: str
    def __init__(self, event: _Optional[_Union[EpisodicEvent, _Mapping]] = ..., error: _Optional[str] = ...) -> None: ...

class GenerateEmbeddingRequest(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class GenerateEmbeddingResponse(_message.Message):
    __slots__ = ("embedding", "error")
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    embedding: bytes
    error: str
    def __init__(self, embedding: _Optional[bytes] = ..., error: _Optional[str] = ...) -> None: ...

class Heuristic(_message.Message):
    __slots__ = ("id", "name", "condition_text", "condition_embedding", "similarity_threshold", "effects_json", "confidence", "learning_rate", "origin", "origin_id", "next_heuristic_ids", "is_terminal", "last_fired_ms", "fire_count", "success_count", "created_at_ms", "updated_at_ms")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONDITION_TEXT_FIELD_NUMBER: _ClassVar[int]
    CONDITION_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    EFFECTS_JSON_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LEARNING_RATE_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_ID_FIELD_NUMBER: _ClassVar[int]
    NEXT_HEURISTIC_IDS_FIELD_NUMBER: _ClassVar[int]
    IS_TERMINAL_FIELD_NUMBER: _ClassVar[int]
    LAST_FIRED_MS_FIELD_NUMBER: _ClassVar[int]
    FIRE_COUNT_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    condition_text: str
    condition_embedding: bytes
    similarity_threshold: float
    effects_json: str
    confidence: float
    learning_rate: float
    origin: str
    origin_id: str
    next_heuristic_ids: _containers.RepeatedScalarFieldContainer[str]
    is_terminal: bool
    last_fired_ms: int
    fire_count: int
    success_count: int
    created_at_ms: int
    updated_at_ms: int
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., condition_text: _Optional[str] = ..., condition_embedding: _Optional[bytes] = ..., similarity_threshold: _Optional[float] = ..., effects_json: _Optional[str] = ..., confidence: _Optional[float] = ..., learning_rate: _Optional[float] = ..., origin: _Optional[str] = ..., origin_id: _Optional[str] = ..., next_heuristic_ids: _Optional[_Iterable[str]] = ..., is_terminal: bool = ..., last_fired_ms: _Optional[int] = ..., fire_count: _Optional[int] = ..., success_count: _Optional[int] = ..., created_at_ms: _Optional[int] = ..., updated_at_ms: _Optional[int] = ...) -> None: ...

class StoreHeuristicRequest(_message.Message):
    __slots__ = ("heuristic", "generate_embedding")
    HEURISTIC_FIELD_NUMBER: _ClassVar[int]
    GENERATE_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    heuristic: Heuristic
    generate_embedding: bool
    def __init__(self, heuristic: _Optional[_Union[Heuristic, _Mapping]] = ..., generate_embedding: bool = ...) -> None: ...

class StoreHeuristicResponse(_message.Message):
    __slots__ = ("success", "error", "heuristic_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    heuristic_id: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., heuristic_id: _Optional[str] = ...) -> None: ...

class QueryHeuristicsRequest(_message.Message):
    __slots__ = ("query_text", "query_embedding", "min_similarity", "min_confidence", "limit")
    QUERY_TEXT_FIELD_NUMBER: _ClassVar[int]
    QUERY_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    MIN_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    MIN_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    query_text: str
    query_embedding: bytes
    min_similarity: float
    min_confidence: float
    limit: int
    def __init__(self, query_text: _Optional[str] = ..., query_embedding: _Optional[bytes] = ..., min_similarity: _Optional[float] = ..., min_confidence: _Optional[float] = ..., limit: _Optional[int] = ...) -> None: ...

class QueryMatchingHeuristicsRequest(_message.Message):
    __slots__ = ("event_text", "min_confidence", "limit", "source_filter")
    EVENT_TEXT_FIELD_NUMBER: _ClassVar[int]
    MIN_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FILTER_FIELD_NUMBER: _ClassVar[int]
    event_text: str
    min_confidence: float
    limit: int
    source_filter: str
    def __init__(self, event_text: _Optional[str] = ..., min_confidence: _Optional[float] = ..., limit: _Optional[int] = ..., source_filter: _Optional[str] = ...) -> None: ...

class QueryHeuristicsResponse(_message.Message):
    __slots__ = ("matches", "error")
    MATCHES_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    matches: _containers.RepeatedCompositeFieldContainer[HeuristicMatch]
    error: str
    def __init__(self, matches: _Optional[_Iterable[_Union[HeuristicMatch, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class HeuristicMatch(_message.Message):
    __slots__ = ("heuristic", "similarity", "score")
    HEURISTIC_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    heuristic: Heuristic
    similarity: float
    score: float
    def __init__(self, heuristic: _Optional[_Union[Heuristic, _Mapping]] = ..., similarity: _Optional[float] = ..., score: _Optional[float] = ...) -> None: ...

class GetHeuristicRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class GetHeuristicResponse(_message.Message):
    __slots__ = ("heuristic", "error")
    HEURISTIC_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    heuristic: Heuristic
    error: str
    def __init__(self, heuristic: _Optional[_Union[Heuristic, _Mapping]] = ..., error: _Optional[str] = ...) -> None: ...

class UpdateHeuristicConfidenceRequest(_message.Message):
    __slots__ = ("heuristic_id", "positive", "learning_rate", "predicted_success", "feedback_source")
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    POSITIVE_FIELD_NUMBER: _ClassVar[int]
    LEARNING_RATE_FIELD_NUMBER: _ClassVar[int]
    PREDICTED_SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_SOURCE_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    positive: bool
    learning_rate: float
    predicted_success: float
    feedback_source: str
    def __init__(self, heuristic_id: _Optional[str] = ..., positive: bool = ..., learning_rate: _Optional[float] = ..., predicted_success: _Optional[float] = ..., feedback_source: _Optional[str] = ...) -> None: ...

class UpdateHeuristicConfidenceResponse(_message.Message):
    __slots__ = ("success", "error", "old_confidence", "new_confidence", "delta", "td_error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    OLD_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    NEW_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    TD_ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    old_confidence: float
    new_confidence: float
    delta: float
    td_error: float
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., old_confidence: _Optional[float] = ..., new_confidence: _Optional[float] = ..., delta: _Optional[float] = ..., td_error: _Optional[float] = ...) -> None: ...

class EvaluateSalienceRequest(_message.Message):
    __slots__ = ("event_id", "source", "raw_text", "structured_json", "entity_ids", "skip_novelty_detection")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    STRUCTURED_JSON_FIELD_NUMBER: _ClassVar[int]
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    SKIP_NOVELTY_DETECTION_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    source: str
    raw_text: str
    structured_json: str
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    skip_novelty_detection: bool
    def __init__(self, event_id: _Optional[str] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., structured_json: _Optional[str] = ..., entity_ids: _Optional[_Iterable[str]] = ..., skip_novelty_detection: bool = ...) -> None: ...

class EvaluateSalienceResponse(_message.Message):
    __slots__ = ("salience", "from_cache", "matched_heuristic_id", "error", "novelty_detection_skipped")
    SALIENCE_FIELD_NUMBER: _ClassVar[int]
    FROM_CACHE_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    NOVELTY_DETECTION_SKIPPED_FIELD_NUMBER: _ClassVar[int]
    salience: _types_pb2.SalienceVector
    from_cache: bool
    matched_heuristic_id: str
    error: str
    novelty_detection_skipped: bool
    def __init__(self, salience: _Optional[_Union[_types_pb2.SalienceVector, _Mapping]] = ..., from_cache: bool = ..., matched_heuristic_id: _Optional[str] = ..., error: _Optional[str] = ..., novelty_detection_skipped: bool = ...) -> None: ...

class Entity(_message.Message):
    __slots__ = ("id", "canonical_name", "aliases", "entity_type", "attributes_json", "embedding", "source", "first_seen_ms", "last_seen_ms", "mention_count", "created_at_ms", "updated_at_ms")
    ID_FIELD_NUMBER: _ClassVar[int]
    CANONICAL_NAME_FIELD_NUMBER: _ClassVar[int]
    ALIASES_FIELD_NUMBER: _ClassVar[int]
    ENTITY_TYPE_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_JSON_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    FIRST_SEEN_MS_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_MS_FIELD_NUMBER: _ClassVar[int]
    MENTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    id: str
    canonical_name: str
    aliases: _containers.RepeatedScalarFieldContainer[str]
    entity_type: str
    attributes_json: str
    embedding: bytes
    source: str
    first_seen_ms: int
    last_seen_ms: int
    mention_count: int
    created_at_ms: int
    updated_at_ms: int
    def __init__(self, id: _Optional[str] = ..., canonical_name: _Optional[str] = ..., aliases: _Optional[_Iterable[str]] = ..., entity_type: _Optional[str] = ..., attributes_json: _Optional[str] = ..., embedding: _Optional[bytes] = ..., source: _Optional[str] = ..., first_seen_ms: _Optional[int] = ..., last_seen_ms: _Optional[int] = ..., mention_count: _Optional[int] = ..., created_at_ms: _Optional[int] = ..., updated_at_ms: _Optional[int] = ...) -> None: ...

class StoreEntityRequest(_message.Message):
    __slots__ = ("entity", "generate_embedding")
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    GENERATE_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    entity: Entity
    generate_embedding: bool
    def __init__(self, entity: _Optional[_Union[Entity, _Mapping]] = ..., generate_embedding: bool = ...) -> None: ...

class StoreEntityResponse(_message.Message):
    __slots__ = ("success", "error", "entity_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    entity_id: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., entity_id: _Optional[str] = ...) -> None: ...

class QueryEntitiesRequest(_message.Message):
    __slots__ = ("name_query", "entity_type", "query_embedding", "min_similarity", "limit")
    NAME_QUERY_FIELD_NUMBER: _ClassVar[int]
    ENTITY_TYPE_FIELD_NUMBER: _ClassVar[int]
    QUERY_EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    MIN_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    name_query: str
    entity_type: str
    query_embedding: bytes
    min_similarity: float
    limit: int
    def __init__(self, name_query: _Optional[str] = ..., entity_type: _Optional[str] = ..., query_embedding: _Optional[bytes] = ..., min_similarity: _Optional[float] = ..., limit: _Optional[int] = ...) -> None: ...

class QueryEntitiesResponse(_message.Message):
    __slots__ = ("matches", "error")
    MATCHES_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    matches: _containers.RepeatedCompositeFieldContainer[EntityMatch]
    error: str
    def __init__(self, matches: _Optional[_Iterable[_Union[EntityMatch, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class EntityMatch(_message.Message):
    __slots__ = ("entity", "similarity")
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    entity: Entity
    similarity: float
    def __init__(self, entity: _Optional[_Union[Entity, _Mapping]] = ..., similarity: _Optional[float] = ...) -> None: ...

class Relationship(_message.Message):
    __slots__ = ("id", "subject_id", "predicate", "object_id", "attributes_json", "confidence", "source", "source_event_id", "created_at_ms", "updated_at_ms")
    ID_FIELD_NUMBER: _ClassVar[int]
    SUBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PREDICATE_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_JSON_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    id: str
    subject_id: str
    predicate: str
    object_id: str
    attributes_json: str
    confidence: float
    source: str
    source_event_id: str
    created_at_ms: int
    updated_at_ms: int
    def __init__(self, id: _Optional[str] = ..., subject_id: _Optional[str] = ..., predicate: _Optional[str] = ..., object_id: _Optional[str] = ..., attributes_json: _Optional[str] = ..., confidence: _Optional[float] = ..., source: _Optional[str] = ..., source_event_id: _Optional[str] = ..., created_at_ms: _Optional[int] = ..., updated_at_ms: _Optional[int] = ...) -> None: ...

class StoreRelationshipRequest(_message.Message):
    __slots__ = ("relationship",)
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    relationship: Relationship
    def __init__(self, relationship: _Optional[_Union[Relationship, _Mapping]] = ...) -> None: ...

class StoreRelationshipResponse(_message.Message):
    __slots__ = ("success", "error", "relationship_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIP_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    relationship_id: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., relationship_id: _Optional[str] = ...) -> None: ...

class GetRelationshipsRequest(_message.Message):
    __slots__ = ("entity_id", "predicate_filter", "include_incoming", "include_outgoing", "min_confidence", "limit")
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    PREDICATE_FILTER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_INCOMING_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_OUTGOING_FIELD_NUMBER: _ClassVar[int]
    MIN_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    entity_id: str
    predicate_filter: str
    include_incoming: bool
    include_outgoing: bool
    min_confidence: float
    limit: int
    def __init__(self, entity_id: _Optional[str] = ..., predicate_filter: _Optional[str] = ..., include_incoming: bool = ..., include_outgoing: bool = ..., min_confidence: _Optional[float] = ..., limit: _Optional[int] = ...) -> None: ...

class GetRelationshipsResponse(_message.Message):
    __slots__ = ("relationships", "error")
    RELATIONSHIPS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    relationships: _containers.RepeatedCompositeFieldContainer[RelationshipWithEntity]
    error: str
    def __init__(self, relationships: _Optional[_Iterable[_Union[RelationshipWithEntity, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class RelationshipWithEntity(_message.Message):
    __slots__ = ("relationship", "related_entity")
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    RELATED_ENTITY_FIELD_NUMBER: _ClassVar[int]
    relationship: Relationship
    related_entity: Entity
    def __init__(self, relationship: _Optional[_Union[Relationship, _Mapping]] = ..., related_entity: _Optional[_Union[Entity, _Mapping]] = ...) -> None: ...

class ExpandContextRequest(_message.Message):
    __slots__ = ("entity_ids", "max_hops", "max_entities", "min_confidence")
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    MAX_HOPS_FIELD_NUMBER: _ClassVar[int]
    MAX_ENTITIES_FIELD_NUMBER: _ClassVar[int]
    MIN_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    max_hops: int
    max_entities: int
    min_confidence: float
    def __init__(self, entity_ids: _Optional[_Iterable[str]] = ..., max_hops: _Optional[int] = ..., max_entities: _Optional[int] = ..., min_confidence: _Optional[float] = ...) -> None: ...

class ExpandContextResponse(_message.Message):
    __slots__ = ("entities", "relationships", "error")
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIPS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    entities: _containers.RepeatedCompositeFieldContainer[Entity]
    relationships: _containers.RepeatedCompositeFieldContainer[Relationship]
    error: str
    def __init__(self, entities: _Optional[_Iterable[_Union[Entity, _Mapping]]] = ..., relationships: _Optional[_Iterable[_Union[Relationship, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class ListResponsesRequest(_message.Message):
    __slots__ = ("decision_path", "source", "search", "limit", "offset")
    DECISION_PATH_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    SEARCH_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    decision_path: str
    source: str
    search: str
    limit: int
    offset: int
    def __init__(self, decision_path: _Optional[str] = ..., source: _Optional[str] = ..., search: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ResponseSummary(_message.Message):
    __slots__ = ("event_id", "timestamp_ms", "source", "raw_text", "decision_path", "matched_heuristic_id", "matched_heuristic_condition", "response_text")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    DECISION_PATH_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_CONDITION_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    timestamp_ms: int
    source: str
    raw_text: str
    decision_path: str
    matched_heuristic_id: str
    matched_heuristic_condition: str
    response_text: str
    def __init__(self, event_id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., decision_path: _Optional[str] = ..., matched_heuristic_id: _Optional[str] = ..., matched_heuristic_condition: _Optional[str] = ..., response_text: _Optional[str] = ...) -> None: ...

class ListResponsesResponse(_message.Message):
    __slots__ = ("responses", "error")
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[ResponseSummary]
    error: str
    def __init__(self, responses: _Optional[_Iterable[_Union[ResponseSummary, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class GetResponseDetailRequest(_message.Message):
    __slots__ = ("event_id",)
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    def __init__(self, event_id: _Optional[str] = ...) -> None: ...

class ResponseDetail(_message.Message):
    __slots__ = ("event_id", "timestamp_ms", "source", "raw_text", "decision_path", "matched_heuristic_id", "matched_heuristic_condition", "matched_heuristic_confidence", "llm_prompt_text", "response_text", "fire_id", "feedback_source", "outcome", "response_id")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    DECISION_PATH_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_CONDITION_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LLM_PROMPT_TEXT_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_SOURCE_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    timestamp_ms: int
    source: str
    raw_text: str
    decision_path: str
    matched_heuristic_id: str
    matched_heuristic_condition: str
    matched_heuristic_confidence: float
    llm_prompt_text: str
    response_text: str
    fire_id: str
    feedback_source: str
    outcome: str
    response_id: str
    def __init__(self, event_id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., decision_path: _Optional[str] = ..., matched_heuristic_id: _Optional[str] = ..., matched_heuristic_condition: _Optional[str] = ..., matched_heuristic_confidence: _Optional[float] = ..., llm_prompt_text: _Optional[str] = ..., response_text: _Optional[str] = ..., fire_id: _Optional[str] = ..., feedback_source: _Optional[str] = ..., outcome: _Optional[str] = ..., response_id: _Optional[str] = ...) -> None: ...

class GetResponseDetailResponse(_message.Message):
    __slots__ = ("detail", "error")
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    detail: ResponseDetail
    error: str
    def __init__(self, detail: _Optional[_Union[ResponseDetail, _Mapping]] = ..., error: _Optional[str] = ...) -> None: ...

class DeleteResponsesRequest(_message.Message):
    __slots__ = ("event_ids",)
    EVENT_IDS_FIELD_NUMBER: _ClassVar[int]
    event_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, event_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class DeleteResponsesResponse(_message.Message):
    __slots__ = ("deleted_count", "error")
    DELETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    deleted_count: int
    error: str
    def __init__(self, deleted_count: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class RecordHeuristicFireRequest(_message.Message):
    __slots__ = ("heuristic_id", "event_id", "episodic_event_id")
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    EPISODIC_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    event_id: str
    episodic_event_id: str
    def __init__(self, heuristic_id: _Optional[str] = ..., event_id: _Optional[str] = ..., episodic_event_id: _Optional[str] = ...) -> None: ...

class RecordHeuristicFireResponse(_message.Message):
    __slots__ = ("fire_id",)
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    fire_id: str
    def __init__(self, fire_id: _Optional[str] = ...) -> None: ...

class UpdateFireOutcomeRequest(_message.Message):
    __slots__ = ("fire_id", "outcome", "feedback_source")
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_SOURCE_FIELD_NUMBER: _ClassVar[int]
    fire_id: str
    outcome: str
    feedback_source: str
    def __init__(self, fire_id: _Optional[str] = ..., outcome: _Optional[str] = ..., feedback_source: _Optional[str] = ...) -> None: ...

class UpdateFireOutcomeResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class GetPendingFiresRequest(_message.Message):
    __slots__ = ("heuristic_id", "max_age_seconds")
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_AGE_SECONDS_FIELD_NUMBER: _ClassVar[int]
    heuristic_id: str
    max_age_seconds: int
    def __init__(self, heuristic_id: _Optional[str] = ..., max_age_seconds: _Optional[int] = ...) -> None: ...

class GetPendingFiresResponse(_message.Message):
    __slots__ = ("fires",)
    FIRES_FIELD_NUMBER: _ClassVar[int]
    fires: _containers.RepeatedCompositeFieldContainer[HeuristicFire]
    def __init__(self, fires: _Optional[_Iterable[_Union[HeuristicFire, _Mapping]]] = ...) -> None: ...

class ListFiresRequest(_message.Message):
    __slots__ = ("outcome", "limit", "offset")
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    outcome: str
    limit: int
    offset: int
    def __init__(self, outcome: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListFiresResponse(_message.Message):
    __slots__ = ("fires", "total_count")
    FIRES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    fires: _containers.RepeatedCompositeFieldContainer[HeuristicFire]
    total_count: int
    def __init__(self, fires: _Optional[_Iterable[_Union[HeuristicFire, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class HeuristicFire(_message.Message):
    __slots__ = ("id", "heuristic_id", "event_id", "fired_at_ms", "outcome", "feedback_source", "episodic_event_id", "heuristic_name", "condition_text", "confidence")
    ID_FIELD_NUMBER: _ClassVar[int]
    HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    FIRED_AT_MS_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_SOURCE_FIELD_NUMBER: _ClassVar[int]
    EPISODIC_EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    HEURISTIC_NAME_FIELD_NUMBER: _ClassVar[int]
    CONDITION_TEXT_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    id: str
    heuristic_id: str
    event_id: str
    fired_at_ms: int
    outcome: str
    feedback_source: str
    episodic_event_id: str
    heuristic_name: str
    condition_text: str
    confidence: float
    def __init__(self, id: _Optional[str] = ..., heuristic_id: _Optional[str] = ..., event_id: _Optional[str] = ..., fired_at_ms: _Optional[int] = ..., outcome: _Optional[str] = ..., feedback_source: _Optional[str] = ..., episodic_event_id: _Optional[str] = ..., heuristic_name: _Optional[str] = ..., condition_text: _Optional[str] = ..., confidence: _Optional[float] = ...) -> None: ...
