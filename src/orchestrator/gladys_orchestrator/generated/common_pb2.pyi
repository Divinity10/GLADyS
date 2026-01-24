import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ComponentState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COMPONENT_STATE_UNKNOWN: _ClassVar[ComponentState]
    COMPONENT_STATE_STARTING: _ClassVar[ComponentState]
    COMPONENT_STATE_ACTIVE: _ClassVar[ComponentState]
    COMPONENT_STATE_PAUSED: _ClassVar[ComponentState]
    COMPONENT_STATE_STOPPING: _ClassVar[ComponentState]
    COMPONENT_STATE_STOPPED: _ClassVar[ComponentState]
    COMPONENT_STATE_ERROR: _ClassVar[ComponentState]
    COMPONENT_STATE_DEAD: _ClassVar[ComponentState]
COMPONENT_STATE_UNKNOWN: ComponentState
COMPONENT_STATE_STARTING: ComponentState
COMPONENT_STATE_ACTIVE: ComponentState
COMPONENT_STATE_PAUSED: ComponentState
COMPONENT_STATE_STOPPING: ComponentState
COMPONENT_STATE_STOPPED: ComponentState
COMPONENT_STATE_ERROR: ComponentState
COMPONENT_STATE_DEAD: ComponentState

class RequestMetadata(_message.Message):
    __slots__ = ("request_id", "trace_id", "span_id", "timestamp_ms", "source_component")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_COMPONENT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    trace_id: str
    span_id: str
    timestamp_ms: int
    source_component: str
    def __init__(self, request_id: _Optional[str] = ..., trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., source_component: _Optional[str] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("id", "timestamp", "source", "raw_text", "structured", "salience", "entity_ids", "tokens", "tokenizer_id", "metadata")
    ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAW_TEXT_FIELD_NUMBER: _ClassVar[int]
    STRUCTURED_FIELD_NUMBER: _ClassVar[int]
    SALIENCE_FIELD_NUMBER: _ClassVar[int]
    ENTITY_IDS_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    TOKENIZER_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    id: str
    timestamp: _timestamp_pb2.Timestamp
    source: str
    raw_text: str
    structured: _struct_pb2.Struct
    salience: SalienceVector
    entity_ids: _containers.RepeatedScalarFieldContainer[str]
    tokens: _containers.RepeatedScalarFieldContainer[int]
    tokenizer_id: str
    metadata: RequestMetadata
    def __init__(self, id: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., source: _Optional[str] = ..., raw_text: _Optional[str] = ..., structured: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., salience: _Optional[_Union[SalienceVector, _Mapping]] = ..., entity_ids: _Optional[_Iterable[str]] = ..., tokens: _Optional[_Iterable[int]] = ..., tokenizer_id: _Optional[str] = ..., metadata: _Optional[_Union[RequestMetadata, _Mapping]] = ...) -> None: ...

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

class Moment(_message.Message):
    __slots__ = ("events", "start_time", "end_time")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[Event]
    start_time: _timestamp_pb2.Timestamp
    end_time: _timestamp_pb2.Timestamp
    def __init__(self, events: _Optional[_Iterable[_Union[Event, _Mapping]]] = ..., start_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ComponentStatus(_message.Message):
    __slots__ = ("component_id", "state", "message", "last_heartbeat", "metrics")
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    state: ComponentState
    message: str
    last_heartbeat: _timestamp_pb2.Timestamp
    metrics: _containers.ScalarMap[str, str]
    def __init__(self, component_id: _Optional[str] = ..., state: _Optional[_Union[ComponentState, str]] = ..., message: _Optional[str] = ..., last_heartbeat: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metrics: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ErrorDetail(_message.Message):
    __slots__ = ("code", "message", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...
