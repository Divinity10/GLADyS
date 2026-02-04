"""Playwright test fixtures for dashboard integration tests."""

import sys
from pathlib import Path

import pytest

# Add parent directories to path for imports
# This allows tests to import fun_api and other sibling packages
_dashboard_root = Path(__file__).parent.parent
_services_root = _dashboard_root.parent
sys.path.insert(0, str(_services_root))
sys.path.insert(0, str(_dashboard_root))


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser context."""
    return {
        "viewport": {"width": 1280, "height": 720},
    }


@pytest.fixture
def dashboard_url():
    """Dashboard URL for tests."""
    return "http://localhost:8502"
