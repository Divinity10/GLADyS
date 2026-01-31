"""gRPC health check client for GLADyS services.

Library usage:
    from gladys_client.health import check_health
"""

import sys
from pathlib import Path

# Add paths for generated protos
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src" / "services" / "orchestrator"))
sys.path.insert(0, str(ROOT / "src" / "services" / "memory"))

import grpc


def check_health(address: str, detailed: bool = False) -> dict:
    """Check health of a gRPC service."""
    try:
        from gladys_orchestrator.generated import types_pb2
        from gladys_orchestrator.generated import types_pb2_grpc
    except ImportError:
        try:
            from gladys_memory.generated import types_pb2
            from gladys_memory.generated import types_pb2_grpc
        except ImportError:
            return {"status": "UNKNOWN", "error": "Proto stubs not available"}

    STATUS_MAP = {
        0: "UNKNOWN",
        1: "HEALTHY",
        2: "UNHEALTHY",
        3: "DEGRADED",
    }

    try:
        with grpc.insecure_channel(address) as channel:
            try:
                grpc.channel_ready_future(channel).result(timeout=5)
            except grpc.FutureTimeoutError:
                return {"status": "UNKNOWN", "error": "Connection timeout"}

            if detailed:
                request = types_pb2.GetHealthDetailsRequest()
            else:
                request = types_pb2.GetHealthRequest()

            result = None

            # Try Memory Storage service
            try:
                from gladys_orchestrator.generated import memory_pb2_grpc
                stub = memory_pb2_grpc.MemoryStorageStub(channel)
                if detailed:
                    response = stub.GetHealthDetails(request, timeout=5)
                    result = {
                        "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                        "uptime_seconds": response.uptime_seconds,
                        "details": dict(response.details),
                    }
                else:
                    response = stub.GetHealth(request, timeout=5)
                    result = {
                        "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                        "message": response.message,
                    }
            except grpc.RpcError:
                pass

            # Try Salience Gateway service
            if result is None:
                try:
                    from gladys_orchestrator.generated import memory_pb2_grpc
                    stub = memory_pb2_grpc.SalienceGatewayStub(channel)
                    if detailed:
                        response = stub.GetHealthDetails(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "uptime_seconds": response.uptime_seconds,
                            "details": dict(response.details),
                        }
                    else:
                        response = stub.GetHealth(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "message": response.message,
                        }
                except grpc.RpcError:
                    pass

            # Try Orchestrator service
            if result is None:
                try:
                    from gladys_orchestrator.generated import orchestrator_pb2_grpc
                    stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
                    if detailed:
                        response = stub.GetHealthDetails(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "uptime_seconds": response.uptime_seconds,
                            "details": dict(response.details),
                        }
                    else:
                        response = stub.GetHealth(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "message": response.message,
                        }
                except grpc.RpcError:
                    pass

            # Try Executive service
            if result is None:
                try:
                    from gladys_orchestrator.generated import executive_pb2_grpc
                    stub = executive_pb2_grpc.ExecutiveServiceStub(channel)
                    if detailed:
                        response = stub.GetHealthDetails(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "uptime_seconds": response.uptime_seconds,
                            "details": dict(response.details),
                        }
                    else:
                        response = stub.GetHealth(request, timeout=5)
                        result = {
                            "status": STATUS_MAP.get(response.status, "UNKNOWN"),
                            "message": response.message,
                        }
                except grpc.RpcError:
                    pass

            if result is not None:
                return result
            return {"status": "UNKNOWN", "error": "No health endpoint responded"}

    except Exception as e:
        return {"status": "UNKNOWN", "error": str(e)}
