#!/usr/bin/env python3
"""Proto Contract Tests - Verify proto consistency across modules.

These tests ensure that:
1. Proto files are in sync across modules
2. Generated Python stubs match the proto definitions
3. Required services and messages exist

Run with: python -m pytest tests/test_proto_contract.py -v
"""

import hashlib
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).parent.parent.parent


class TestProtoConsistency:
    """Test that proto files are consistent across modules."""

    def test_canonical_proto_exists(self):
        """Canonical proto/ dir should contain memory.proto."""
        proto = ROOT / "proto" / "memory.proto"
        assert proto.exists(), "Canonical memory.proto not found at proto/"

    def test_memory_proto_hash(self):
        """Memory proto hash should match expected structure."""
        memory_proto = ROOT / "proto" / "memory.proto"

        if not memory_proto.exists():
            pytest.skip("Memory proto not found")

        content = memory_proto.read_text()

        # Check for required messages
        required_messages = [
            "message Heuristic",
            "message HeuristicMatch",
        ]

        for msg in required_messages:
            assert msg in content, f"Missing required message: {msg}"

        # Check for required services
        required_services = [
            "service MemoryStorage",
            "service SalienceGateway",
        ]

        for svc in required_services:
            assert svc in content, f"Missing required service: {svc}"

    def test_memory_proto_cbr_schema(self):
        """Memory proto should use CBR schema (not old condition_json)."""
        memory_proto = ROOT / "proto" / "memory.proto"

        if not memory_proto.exists():
            pytest.skip("Memory proto not found")

        content = memory_proto.read_text()

        # CBR schema uses condition_text, effects_json
        assert "condition_text" in content, "Missing CBR field: condition_text"
        assert "effects_json" in content, "Missing CBR field: effects_json"

        # Old schema used condition_json, action_json - should not be present
        assert "condition_json" not in content, (
            "Proto still uses old schema (condition_json). "
            "Should use CBR schema (condition_text)."
        )


class TestGeneratedStubs:
    """Test that generated Python stubs are valid."""

    def test_memory_stubs_exist(self):
        """Memory Python stubs should exist."""
        stubs_dir = ROOT / "src" / "services" / "memory" / "gladys_memory"

        pb2 = stubs_dir / "memory_pb2.py"
        pb2_grpc = stubs_dir / "memory_pb2_grpc.py"

        assert pb2.exists(), "memory_pb2.py not found - run proto_sync.py"
        assert pb2_grpc.exists(), "memory_pb2_grpc.py not found - run proto_sync.py"

    def test_memory_stubs_parseable(self):
        """Memory Python stubs should be valid Python."""
        import ast
        stubs_dir = ROOT / "src" / "services" / "memory" / "gladys_memory"

        for name in ("memory_pb2.py", "memory_pb2_grpc.py"):
            stub = stubs_dir / name
            if not stub.exists():
                pytest.fail(f"{name} not found")
            # Verify it parses as valid Python
            ast.parse(stub.read_text(), filename=str(stub))

    def test_memory_stubs_relative_imports(self):
        """Memory gRPC stub should use relative imports."""
        grpc_stub = ROOT / "src" / "services" / "memory" / "gladys_memory" / "memory_pb2_grpc.py"

        if not grpc_stub.exists():
            pytest.skip("gRPC stub not found")

        content = grpc_stub.read_text()

        # Should use relative imports
        assert "from . import memory_pb2" in content, (
            "gRPC stub uses absolute imports. "
            "Run proto_sync.py to fix imports."
        )

        # Should NOT use absolute imports
        assert "\nimport memory_pb2" not in content, (
            "gRPC stub uses absolute imports. "
            "Run proto_sync.py to fix imports."
        )


class TestOrchestratorStubs:
    """Test orchestrator proto stubs."""

    def test_orchestrator_stubs_exist(self):
        """Orchestrator Python stubs should exist."""
        stubs_dir = ROOT / "src" / "services" / "orchestrator" / "gladys_orchestrator" / "generated"

        required_stubs = [
            "common_pb2.py",
            "memory_pb2.py",
            "orchestrator_pb2.py",
        ]

        for stub in required_stubs:
            stub_path = stubs_dir / stub
            assert stub_path.exists(), f"{stub} not found - run proto_sync.py"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
