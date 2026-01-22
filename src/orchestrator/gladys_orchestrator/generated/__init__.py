"""Generated gRPC code from proto files.

Generated with: python -m grpc_tools.protoc
"""

from .common_pb2 import (
    Event,
    SalienceVector,
    RequestMetadata,
    ComponentState,
    ComponentStatus,
    ErrorDetail,
)
from .orchestrator_pb2 import (
    EventAck,
    SubscribeRequest,
    RegisterRequest,
    RegisterResponse,
    UnregisterRequest,
    UnregisterResponse,
    CommandRequest,
    CommandResponse,
    Command,
    HeartbeatRequest,
    HeartbeatResponse,
    PendingCommand,
    SystemStatusRequest,
    SystemStatusResponse,
    ResolveRequest,
    ResolveResponse,
    ComponentCapabilities,
    TransportMode,
    InstancePolicy,
)
from .orchestrator_pb2_grpc import (
    OrchestratorServiceServicer,
    OrchestratorServiceStub,
    add_OrchestratorServiceServicer_to_server,
)
