"""Pytest configuration for GLADyS integration tests.

Tests REQUIRE explicit environment specification via wrapper scripts.
This ensures developers always know which environment they're testing against.

Usage:
    python scripts/local.py test test_foo.py   # LOCAL environment
    python scripts/docker.py test test_foo.py  # DOCKER environment

DO NOT run tests directly with pytest - use the wrapper scripts above.
"""

import os

import pytest


def _get_required_env_var(name: str) -> str:
    """Get a required environment variable or skip the test."""
    value = os.environ.get(name)
    if not value:
        pytest.skip(
            f"Environment variable {name} not set.\n"
            "Integration tests require explicit environment specification.\n"
            "Use wrapper scripts:\n"
            "  python scripts/local.py test <test_file>   # LOCAL\n"
            "  python scripts/docker.py test <test_file>  # DOCKER"
        )
    return value


@pytest.fixture(scope="session")
def service_env():
    """Fixture ensuring environment is properly configured.

    Skips all tests if not run via wrapper scripts.
    Returns the detected environment name for logging.
    """
    # Check that required env vars are set (wrapper scripts set these)
    orchestrator = os.environ.get("ORCHESTRATOR_ADDRESS")
    memory = os.environ.get("PYTHON_ADDRESS")

    if not orchestrator or not memory:
        pytest.skip(
            "Environment not configured.\n"
            "Integration tests require explicit environment specification.\n"
            "Use wrapper scripts:\n"
            "  python scripts/local.py test <test_file>   # LOCAL\n"
            "  python scripts/docker.py test <test_file>  # DOCKER"
        )

    # Detect which environment based on port numbers
    if ":50050" in orchestrator or ":50051" in memory:
        return "LOCAL"
    elif ":50060" in orchestrator or ":50061" in memory:
        return "DOCKER"
    else:
        return "CUSTOM"


@pytest.fixture(scope="session")
def orchestrator_address(service_env):
    """Fixture providing Orchestrator gRPC address."""
    return _get_required_env_var("ORCHESTRATOR_ADDRESS")


@pytest.fixture(scope="session")
def memory_address(service_env):
    """Fixture providing Memory Storage gRPC address."""
    return _get_required_env_var("PYTHON_ADDRESS")


@pytest.fixture(scope="session")
def salience_address(service_env):
    """Fixture providing Salience Gateway gRPC address."""
    return _get_required_env_var("RUST_ADDRESS")


@pytest.fixture(scope="session")
def executive_address(service_env):
    """Fixture providing Executive gRPC address."""
    return _get_required_env_var("EXECUTIVE_ADDRESS")
