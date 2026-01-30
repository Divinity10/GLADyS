"""gRPC client for the SalienceGateway cache service.

Library usage:
    from gladys_client.cache import get_stub
"""

import sys
from pathlib import Path

# Add memory to sys.path to find generated protos
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.append(str(ROOT / "src" / "services" / "memory"))

import grpc
from gladys_memory import memory_pb2, memory_pb2_grpc


def get_stub(address: str) -> memory_pb2_grpc.SalienceGatewayStub:
    channel = grpc.insecure_channel(address)
    return memory_pb2_grpc.SalienceGatewayStub(channel)
