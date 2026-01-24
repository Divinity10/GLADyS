import datetime

from . import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TransportMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRANSPORT_MODE_UNSPECIFIED: _ClassVar[TransportMode]
    TRANSPORT_MODE_STREAMING: _ClassVar[TransportMode]
    TRANSPORT_MODE_BATCHED: _ClassVar[TransportMode]
    TRANSPORT_MODE_EVENT: _ClassVar[TransportMode]

class InstancePolicy(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    INSTANCE_POLICY_SINGLE: _ClassVar[InstancePolicy]
    INSTANCE_POLICY_MULTIPLE: _ClassVar[InstancePolicy]

class Command(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COMMAND_UNSPECIFIED: _ClassVar[Command]
    COMMAND_START: _ClassVar[Command]
    COMMAND_STOP: _ClassVar[Command]
    COMMAND_PAUSE: _ClassVar[Command]
    COMMAND_RESUME: _ClassVar[Command]
    COMMAND_RELOAD: _ClassVar[Command]
    COMMAND_HEALTH_CHECK: _ClassVar[Command]
TRANSPORT_MODE_UNSPECIFIED: TransportMode
TRANSPORT_MODE_STREAMING: TransportMode
TRANSPORT_MODE_BATCHED: TransportMode
TRANSPORT_MODE_EVENT: TransportMode
INSTANCE_POLICY_SINGLE: InstancePolicy
INSTANCE_POLICY_MULTIPLE: InstancePolicy
COMMAND_UNSPECIFIED: Command
COMMAND_START: Command
COMMAND_STOP: Command
COMMAND_PAUSE: Command
COMMAND_RESUME: Command
COMMAND_RELOAD: Command
COMMAND_HEALTH_CHECK: Command

class EventAck(_message.Message):
    __slots__ = ("event_id", "accepted", "error_message")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    accepted: bool
    error_message: str
    def __init__(self, event_id: _Optional[str] = ..., accepted: bool = ..., error_message: _Optional[str] = ...) -> None: ...

class SubscribeRequest(_message.Message):
    __slots__ = ("subscriber_id", "source_filters", "event_types")
    SUBSCRIBER_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FILTERS_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPES_FIELD_NUMBER: _ClassVar[int]
    subscriber_id: str
    source_filters: _containers.RepeatedScalarFieldContainer[str]
    event_types: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, subscriber_id: _Optional[str] = ..., source_filters: _Optional[_Iterable[str]] = ..., event_types: _Optional[_Iterable[str]] = ...) -> None: ...

class RegisterRequest(_message.Message):
    __slots__ = ("component_id", "component_type", "address", "capabilities", "metadata")
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    COMPONENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    component_type: str
    address: str
    capabilities: ComponentCapabilities
    metadata: _common_pb2.RequestMetadata
    def __init__(self, component_id: _Optional[str] = ..., component_type: _Optional[str] = ..., address: _Optional[str] = ..., capabilities: _Optional[_Union[ComponentCapabilities, _Mapping]] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class ComponentCapabilities(_message.Message):
    __slots__ = ("transport_mode", "batch_size", "batch_interval_ms", "configurable", "supported_instructions", "instance_policy")
    TRANSPORT_MODE_FIELD_NUMBER: _ClassVar[int]
    BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    BATCH_INTERVAL_MS_FIELD_NUMBER: _ClassVar[int]
    CONFIGURABLE_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_POLICY_FIELD_NUMBER: _ClassVar[int]
    transport_mode: TransportMode
    batch_size: int
    batch_interval_ms: int
    configurable: bool
    supported_instructions: _containers.RepeatedScalarFieldContainer[str]
    instance_policy: InstancePolicy
    def __init__(self, transport_mode: _Optional[_Union[TransportMode, str]] = ..., batch_size: _Optional[int] = ..., batch_interval_ms: _Optional[int] = ..., configurable: bool = ..., supported_instructions: _Optional[_Iterable[str]] = ..., instance_policy: _Optional[_Union[InstancePolicy, str]] = ...) -> None: ...

class RegisterResponse(_message.Message):
    __slots__ = ("success", "error_message", "assigned_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    assigned_id: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ..., assigned_id: _Optional[str] = ...) -> None: ...

class UnregisterRequest(_message.Message):
    __slots__ = ("component_id", "metadata")
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    metadata: _common_pb2.RequestMetadata
    def __init__(self, component_id: _Optional[str] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class UnregisterResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class CommandRequest(_message.Message):
    __slots__ = ("target_component_id", "command", "metadata")
    TARGET_COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    target_component_id: str
    command: Command
    metadata: _common_pb2.RequestMetadata
    def __init__(self, target_component_id: _Optional[str] = ..., command: _Optional[_Union[Command, str]] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class CommandResponse(_message.Message):
    __slots__ = ("success", "error_message", "status")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    status: _common_pb2.ComponentStatus
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ..., status: _Optional[_Union[_common_pb2.ComponentStatus, _Mapping]] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("component_id", "state", "metrics", "metadata")
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    state: _common_pb2.ComponentState
    metrics: _containers.ScalarMap[str, str]
    metadata: _common_pb2.RequestMetadata
    def __init__(self, component_id: _Optional[str] = ..., state: _Optional[_Union[_common_pb2.ComponentState, str]] = ..., metrics: _Optional[_Mapping[str, str]] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("acknowledged", "pending_commands")
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    PENDING_COMMANDS_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    pending_commands: _containers.RepeatedCompositeFieldContainer[PendingCommand]
    def __init__(self, acknowledged: bool = ..., pending_commands: _Optional[_Iterable[_Union[PendingCommand, _Mapping]]] = ...) -> None: ...

class PendingCommand(_message.Message):
    __slots__ = ("command_id", "command")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    command: Command
    def __init__(self, command_id: _Optional[str] = ..., command: _Optional[_Union[Command, str]] = ...) -> None: ...

class SystemStatusRequest(_message.Message):
    __slots__ = ("metadata",)
    METADATA_FIELD_NUMBER: _ClassVar[int]
    metadata: _common_pb2.RequestMetadata
    def __init__(self, metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class SystemStatusResponse(_message.Message):
    __slots__ = ("components", "timestamp")
    COMPONENTS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    components: _containers.RepeatedCompositeFieldContainer[_common_pb2.ComponentStatus]
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, components: _Optional[_Iterable[_Union[_common_pb2.ComponentStatus, _Mapping]]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ResolveRequest(_message.Message):
    __slots__ = ("component_id", "component_type", "metadata")
    COMPONENT_ID_FIELD_NUMBER: _ClassVar[int]
    COMPONENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    component_id: str
    component_type: str
    metadata: _common_pb2.RequestMetadata
    def __init__(self, component_id: _Optional[str] = ..., component_type: _Optional[str] = ..., metadata: _Optional[_Union[_common_pb2.RequestMetadata, _Mapping]] = ...) -> None: ...

class ResolveResponse(_message.Message):
    __slots__ = ("found", "address", "capabilities")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    found: bool
    address: str
    capabilities: ComponentCapabilities
    def __init__(self, found: bool = ..., address: _Optional[str] = ..., capabilities: _Optional[_Union[ComponentCapabilities, _Mapping]] = ...) -> None: ...
