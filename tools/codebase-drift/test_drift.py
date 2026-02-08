import pytest
import os
import sys
import textwrap
from pathlib import Path
from drift_check import DriftChecker

@pytest.fixture
def temp_root(tmp_path):
    """Creates a mock root directory with a minimal GLADyS structure."""
    root = tmp_path / "gladys"
    root.mkdir()
    (root / "src" / "services").mkdir(parents=True)
    (root / "proto").mkdir()
    return root

def test_detects_stale_paths(temp_root):
    # Setup: Map points to non-existent file
    map_content = textwrap.dedent("""
        ## Port Reference
        | Service | Local Port | Docker Host Port | Proto Service | Language |
        |---------|------------|------------------|---------------|----------|
        | TestSvc | 1234 | 1234 | `TestService` | Python |

        ### `TestService` Service (test.proto)
        **Implemented by**: `src/services/test/missing.py`
        | RPC | Purpose |
        |-----|---------|
        | `DoStuff` | Test |
    """)
    (temp_root / "CODEBASE_MAP.md").write_text(map_content)
    (temp_root / "proto" / "test.proto").write_text("service TestService { rpc DoStuff(Req) returns (Res); }")
    (temp_root / "src" / "services" / "test").mkdir(parents=True)
    
    checker = DriftChecker(temp_root)
    checker.parse_codebase_map()
    checker.check_stale_paths()
    
    assert any("Referenced path `src/services/test/missing.py` does not exist" in msg for msg in checker.categories["Stale Paths"])

def test_detects_missing_services(temp_root):
    # Setup: Service dir exists but not in map
    map_content = textwrap.dedent("""
        ## Port Reference
        | Service | Local Port | Docker Host Port | Proto Service | Language |
        |---------|------------|------------------|---------------|----------|
        | KnownSvc | 1234 | 1234 | `KnownService` | Python |

        ### `KnownService` Service (known.proto)
        **Implemented by**: `src/services/known/server.py`
        | RPC | Purpose |
        |-----|---------|
        | `Do` | Test |
    """)
    (temp_root / "CODEBASE_MAP.md").write_text(map_content)
    (temp_root / "src" / "services" / "known").mkdir(parents=True)
    (temp_root / "src" / "services" / "known" / "server.py").write_text("")
    
    # Extra service dir
    (temp_root / "src" / "services" / "unknown").mkdir(parents=True)
    
    checker = DriftChecker(temp_root)
    checker.parse_codebase_map()
    checker.check_missing_services()
    
    assert any("src/services/unknown is not accounted for" in msg for msg in checker.categories["Missing Services"])

def test_detects_port_drift(temp_root):
    # Setup: Map port != .env port
    map_content = textwrap.dedent("""
        ## Port Reference
        | Service | Local Port | Docker Host Port | Proto Service | Language |
        |---------|------------|------------------|---------------|----------|
        | MemoryStorage | 50051 | 50061 | `MemoryStorage` | Python |
    """)
    (temp_root / "CODEBASE_MAP.md").write_text(map_content)
    (temp_root / ".env").write_text("MEMORY_PORT=50099")

    # Setup docker-compose drift
    docker_yml = textwrap.dedent("""
        services:
          memory:
            ports:
              - "50088:50051"
    """)
    (temp_root / "docker").mkdir()
    (temp_root / "docker" / "docker-compose.yml").write_text(docker_yml)
    
    checker = DriftChecker(temp_root)
    checker.parse_codebase_map()
    checker.check_port_drift()
    
    # Check .env drift
    assert any("Map says 50051, .env `MEMORY_PORT` says 50099" in msg for msg in checker.categories["Port Drift"])
    # Check Docker host port drift
    assert any("Map says Docker host port 50061, docker-compose.yml says 50088" in msg for msg in checker.categories["Port Drift"])

def test_detects_proto_drift(temp_root):
    # Setup: Map RPCs != .proto RPCs
    map_content = textwrap.dedent("""
        ## Port Reference
        | Service | Local Port | Docker Host Port | Proto Service | Language |
        |---------|------------|------------------|---------------|----------|
        | TestSvc | 1234 | 1234 | `TestService` | Python |

        ### `TestService` Service (test.proto)
        **Implemented by**: `src/services/test/server.py`
        | RPC | Purpose |
        |-----|---------|
        | `MappedRPC` | Exists in map |
        | `StaleRPC` | Exists in map but NOT in proto |
    """)
    (temp_root / "CODEBASE_MAP.md").write_text(map_content)
    # Proto has MappedRPC and ExtraRPC (missing in map)
    proto_content = """
    service TestService {
        rpc MappedRPC(Req) returns (Res);
        rpc ExtraRPC(Req) returns (Res);
    }
    """
    (temp_root / "proto" / "test.proto").write_text(proto_content)
    
    checker = DriftChecker(temp_root)
    checker.parse_codebase_map()
    checker.check_proto_drift()
    
    # Missing in map
    assert any("RPCs in `test.proto` missing from map: ExtraRPC" in msg for msg in checker.categories["Proto Drift"])
    # Stale in map
    assert any("Stale RPCs in map for `test.proto`: StaleRPC" in msg for msg in checker.categories["Proto Drift"])

def test_bidirectional_proto_drift(temp_root):
    # Setup: Proto service exists but not in map
    (temp_root / "CODEBASE_MAP.md").write_text("## Port Reference\n| S | P | D | PS | L |\n|---|---|---|---|---|")
    (temp_root / "proto" / "unmapped.proto").write_text("service UnmappedService { rpc Any(Req) returns (Res); }")
    
    checker = DriftChecker(temp_root)
    checker.parse_codebase_map()
    checker.check_proto_drift()
    
    assert any("Proto service `UnmappedService` in `unmapped.proto` is missing from CODEBASE_MAP.md" in msg for msg in checker.categories["Proto Drift"])

def test_exit_codes(temp_root):
    # Clean run
    (temp_root / "CODEBASE_MAP.md").write_text("## Port Reference\n| S | P | D | PS | L |\n|---|---|---|---|---|")
    checker_clean = DriftChecker(temp_root)
    assert checker_clean.run() == 0
    
    # Dirty run (missing service)
    (temp_root / "src" / "services" / "newsvc").mkdir(parents=True)
    checker_dirty = DriftChecker(temp_root)
    assert checker_dirty.run() == 1