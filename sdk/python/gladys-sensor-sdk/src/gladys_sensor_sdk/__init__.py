"""GLADyS Python Sensor SDK.

Pythonic SDK for building GLADyS sensors with automatic lifecycle management.
"""

__version__ = "0.1.0"

# Core client
from .client import GladysClient
from .config import TimeoutConfig

# Event building
from .events import EventBuilder, EventDispatcher, Intent
from .flow_control import (
    FlowStrategy,
    NoOpStrategy,
    RateLimitStrategy,
    create_strategy,
)

# State management
from .state import Command, ComponentState

# Command arguments
from .args import (
    CommandArgs,
    HealthCheckArgs,
    RecoverArgs,
    StartArgs,
    StopArgs,
)

# Sensor base class (primary API)
from .adapter import AdapterBase

# Lifecycle orchestrator (exposed for advanced use)
from .lifecycle import SensorLifecycle

# Registration helper
from .registration import SensorRegistration

# Testing subpackage
from . import testing

__all__ = [
    # Client
    "GladysClient",
    "TimeoutConfig",
    # Events
    "EventBuilder",
    "EventDispatcher",
    "Intent",
    "FlowStrategy",
    "NoOpStrategy",
    "RateLimitStrategy",
    "create_strategy",
    # State
    "ComponentState",
    "Command",
    # Args
    "CommandArgs",
    "StartArgs",
    "StopArgs",
    "RecoverArgs",
    "HealthCheckArgs",
    # Adapter (primary API)
    "AdapterBase",
    # Lifecycle
    "SensorLifecycle",
    # Registration
    "SensorRegistration",
    # Testing
    "testing",
]
