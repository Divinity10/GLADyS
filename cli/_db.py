"""Database query module — thin wrapper around gladys_client.db.

Preserves the mode-based get_dsn(mode) interface for CLI scripts.
All query functions are re-exported from gladys_client.db.
"""

import sys
from pathlib import Path

# Add gladys_client to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_client"))

from gladys_client.db import (
    _connect,
    count_events,
    count_fires,
    count_heuristics,
    delete_all_events,
    delete_event,
    get_event,
    get_metrics,
    list_events,
    list_fires,
    list_heuristics,
)
from gladys_client.db import get_dsn as _get_dsn_by_port

from _gladys import LOCAL_PORTS, DOCKER_PORTS


def get_dsn(mode: str = "local") -> str:
    """Build a psycopg2 DSN string for the given environment mode."""
    ports = DOCKER_PORTS if mode == "docker" else LOCAL_PORTS
    return _get_dsn_by_port(ports.db)
