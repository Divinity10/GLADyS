"""Pytest configuration for memory service tests.

Auto-skips integration tests when PostgreSQL isn't available.
"""

import socket

import pytest


def _pg_available(host: str = "localhost", port: int = 5433) -> bool:
    """Check if PostgreSQL is accepting connections."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Check once at collection time
_DB_AVAILABLE = _pg_available()


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring PostgreSQL"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests when PostgreSQL isn't available."""
    if _DB_AVAILABLE:
        return

    skip_db = pytest.mark.skip(reason="PostgreSQL not available on port 5433")
    for item in items:
        # Skip tests in test_storage.py and test_grpc.py (integration tests)
        # but not test_grpc_events.py (uses mocks)
        test_file = item.fspath.basename
        if test_file in ("test_storage.py", "test_grpc.py"):
            item.add_marker(skip_db)
