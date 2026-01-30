from . import common_pb2 as _common_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessEventRequest(_message.Message):
    __slots__ = ("event", "immediate", "metadata")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    IMMEDIATE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    event: _common_pb2.Event
    immediate: bool
    metadata: _common_pb2.RequestMetadata
    def __init__(self, event: _Optional[_Union[_common_pb2.Event, _Mapping]] = ..., immediate: bool = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class ProcessEventResponse(_message.Message):
    __slots__ = ("accepted", "error_message", "response_id", "response_text")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_ID_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    error_message: str
    response_id: str
    response_text: str
    def __init__(self, accepted: bool = ..., error_message: _Optional[str] = ..., response_id: _Optional[str] = ..., response_text: _Optional[str] = ...) -> None: ...

class ProcessMomentRequest(_message.Message):
    __slots__ = ("moment", "metadata")
    MOMENT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    moment: _common_pb2.Moment
    metadata: _common_pb2.RequestMetadata
    def __init__(self, moment: _Optional[_Union[_common_pb2.Moment, _Mapping]] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class ProcessMomentResponse(_message.Message):
    __slots__ = ("accepted", "error_message", "events_processed")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EVENTS_PROCESSED_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    error_message: str
    events_processed: int
    def __init__(self, accepted: bool = ..., error_message: _Optional[str] = ..., events_processed: _Optional[int] = ...) -> None: ...

class ProvideFeedbackRequest(_message.Message):
    __slots__ = ("event_id", "positive", "response_id", "metadata")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    POSITIVE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    positive: bool
    response_id: str
    metadata: _common_pb2.RequestMetadata
    def __init__(self, event_id: _Optional[str] = ..., positive: bool = ..., response_id: _Optional[str] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class ProvideFeedbackResponse(_message.Message):
    __slots__ = ("accepted", "error_message", "created_heuristic_id")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CREATED_HEURISTIC_ID_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    error_message: str
    created_heuristic_id: str
    def __init__(self, accepted: bool = ..., error_message: _Optional[str] = ..., created_heuristic_id: _Optional[str] = ...) -> None: ...
