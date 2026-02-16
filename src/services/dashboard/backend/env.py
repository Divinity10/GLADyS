"""Environment configuration and gRPC channel management for Dashboard V2.

Provides environment-aware addressing (Local vs Docker) and lazy gRPC
channel/stub creation. Import the `env` singleton to access stubs.

Async stubs (default) for use in FastAPI async handlers.
Sync stubs via `sync_*_stub()` for background threads (e.g. SSE).
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import grpc
import grpc.aio

# Project root: src/services/dashboard/backend/env.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

# Add proto stub paths
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "memory"))

# Import proto stubs
try:
    from gladys_orchestrator.generated import (
        common_pb2,
        executive_pb2,
        executive_pb2_grpc,
        memory_pb2,
        memory_pb2_grpc,
        orchestrator_pb2,
        orchestrator_pb2_grpc,
        types_pb2,
    )

    PROTOS_AVAILABLE = True
except ImportError:
    PROTOS_AVAILABLE = False

# Make gladys_client importable
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib" / "gladys_client"))

# CLI admin modules (backends, _gladys) needed by services router
sys.path.insert(0, str(PROJECT_ROOT / "cli"))

# FUN API routers (REST/JSON endpoints separated from dashboard)
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services"))


@dataclass
class EnvConfig:
    """Port/address configuration for an environment."""

    orchestrator: str
    memory: str
    salience: str
    executive: str
    db_port: int


ENV_CONFIGS = {
    "local": EnvConfig(
        orchestrator=os.environ.get("ORCHESTRATOR_ADDRESS", "localhost:50050"),
        memory=os.environ.get("MEMORY_ADDRESS", "localhost:50051"),
        salience=os.environ.get("SALIENCE_ADDRESS", "localhost:50052"),
        executive=os.environ.get("EXECUTIVE_ADDRESS", "localhost:50053"),
        db_port=int(os.environ.get("DB_PORT", 5432)),
    ),
    "docker": EnvConfig(
        orchestrator="localhost:50060",
        memory="localhost:50061",
        salience="localhost:50062",
        executive="localhost:50063",
        db_port=5433,
    ),
}

# Service display info keyed by name
SERVICE_INFO = {
    "orchestrator": {"label": "Orchestrator", "env_attr": "orchestrator"},
    "memory": {"label": "Memory Storage", "env_attr": "memory"},
    "salience": {"label": "Salience Gateway", "env_attr": "salience"},
    "executive": {"label": "Executive", "env_attr": "executive"},
}


class Environment:
    """Manages current environment selection and gRPC channels.

    Provides async stubs (grpc.aio) for FastAPI handlers and sync stubs
    (grpc.insecure_channel) for background threads like SSE.
    """

    def __init__(self):
        self._mode: str = "local"
        self._async_channels: dict[str, grpc.aio.Channel] = {}
        self._sync_channels: dict[str, grpc.Channel] = {}

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def config(self) -> EnvConfig:
        return ENV_CONFIGS[self._mode]

    async def switch(self, mode: str):
        """Switch environment, closing existing channels."""
        mode = mode.lower()
        if mode not in ENV_CONFIGS:
            raise ValueError(f"Unknown environment: {mode}")
        if mode != self._mode:
            await self._close_channels()
            self._mode = mode

    async def _close_channels(self):
        for ch in self._async_channels.values():
            try:
                await ch.close()
            except Exception:
                pass
        self._async_channels.clear()
        for ch in self._sync_channels.values():
            try:
                ch.close()
            except Exception:
                pass
        self._sync_channels.clear()

    def _get_async_channel(self, address: str) -> grpc.aio.Channel:
        if address not in self._async_channels:
            self._async_channels[address] = grpc.aio.insecure_channel(address)
        return self._async_channels[address]

    def _get_sync_channel(self, address: str) -> grpc.Channel:
        if address not in self._sync_channels:
            self._sync_channels[address] = grpc.insecure_channel(address)
        return self._sync_channels[address]

    # --- Async stubs (for FastAPI async handlers) ---

    def orchestrator_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return orchestrator_pb2_grpc.OrchestratorServiceStub(
            self._get_async_channel(self.config.orchestrator)
        )

    def memory_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return memory_pb2_grpc.MemoryStorageStub(
            self._get_async_channel(self.config.memory)
        )

    def salience_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return memory_pb2_grpc.SalienceGatewayStub(
            self._get_async_channel(self.config.salience)
        )

    def executive_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return executive_pb2_grpc.ExecutiveServiceStub(
            self._get_async_channel(self.config.executive)
        )

    # --- Sync stubs (for background threads like SSE) ---

    def sync_orchestrator_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return orchestrator_pb2_grpc.OrchestratorServiceStub(
            self._get_sync_channel(self.config.orchestrator)
        )

    def sync_memory_stub(self):
        if not PROTOS_AVAILABLE:
            return None
        return memory_pb2_grpc.MemoryStorageStub(
            self._get_sync_channel(self.config.memory)
        )

    def services_list(self) -> list[dict]:
        """Return service definitions with addresses for current env."""
        cfg = self.config
        result = []
        for name, info in SERVICE_INFO.items():
            addr = getattr(cfg, info["env_attr"])
            host, port = addr.rsplit(":", 1)
            result.append({
                "name": name,
                "label": info["label"],
                "host": host,
                "port": int(port),
            })
        return result

    def get_db_dsn(self) -> str:
        """PostgreSQL connection string for current environment."""
        host = os.environ.get("DB_HOST", "localhost")
        name = os.environ.get("DB_NAME", "gladys")
        user = os.environ.get("DB_USER", "gladys")
        pw = os.environ.get("DB_PASS", "gladys")
        return f"host={host} port={self.config.db_port} dbname={name} user={user} password={pw}"


# Singleton
env = Environment()
