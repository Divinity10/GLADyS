from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EpisodicEvent(_message.Message):
    __slots__ = ("id", "timestamp_ms", "source", "raw_text", "embedding", "salience", "structured_json", "entity_ids")
    ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    SALIENCE_FIELD_NUMBER: _ClassVar[int]
    STRUCTURED_JSON_FIELD_NUMBER: _ClassVar[int]
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    id: str
    timestamp_ms: int
    source: str
    raw_text: str
    embedding: bytes
    salience: SalienceVector
    structured_json: str
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., embedding: _Optional[bytes] = ..., salience: _Optional[_Union[SalienceVector, _Mapping]] = ..., structured_json: _Optional[str] = ..., entity_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class SalienceVector(_message.Message):
    __slots__ = ("threat", "opportunity", "humor", "novelty", "goal_relevance", "social", "emotional", "actionability", "habituation")
    THREAT_FIELD_NUMBER: _ClassVar[int]
    OPPORTUNITY_FIELD_NUMBER: _ClassVar[int]
    HUMOR_FIELD_NUMBER: _ClassVar[int]
    NOVELTY_FIELD_NUMBER: _ClassVar[int]
    GOAL_RELEVANCE_FIELD_NUMBER: _ClassVar[int]
    SOCIAL_FIELD_NUMBER: _ClassVar[int]
    EMOTIONAL_FIELD_NUMBER: _ClassVar[int]
    ACTIONABILITY_FIELD_NUMBER: _ClassVar[int]
    HABITUATION_FIELD_NUMBER: _ClassVar[int]
    threat: float
    opportunity: float
    humor: float
    novelty: float
    goal_relevance: float
    social: float
    emotional: float
    actionability: float
    habituation: float
    def __init__(self, threat: _Optional[float] = ..., opportunity: _Optional[float] = ..., humor: _Optional[float] = ..., novelty: _Optional[float] = ..., goal_relevance: _Optional[float] = ..., social: _Optional[float] = ..., emotional: _Optional[float] = ..., actionability: _Optional[float] = ..., habituation: _Optional[float] = ...) -> None: ...

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

class EvaluateSalienceRequest(_message.Message):
    __slots__ = ("event_id", "source", "raw_text", "structured_json", "entity_ids")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    STRUCTURED_JSON_FIELD_NUMBER: _ClassVar[int]
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    source: str
    raw_text: str
    structured_json: str
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, event_id: _Optional[str] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., structured_json: _Optional[str] = ..., entity_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class EvaluateSalienceResponse(_message.Message):
    __slots__ = ("salience", "from_cache", "matched_heuristic_id", "error")
    SALIENCE_FIELD_NUMBER: _ClassVar[int]
    FROM_CACHE_FIELD_NUMBER: _ClassVar[int]
    MATCHED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    salience: SalienceVector
    from_cache: bool
    matched_heuristic_id: str
    error: str
    def __init__(self, salience: _Optional[_Union[SalienceVector, _Mapping]] = ..., from_cache: bool = ..., matched_heuristic_id: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
