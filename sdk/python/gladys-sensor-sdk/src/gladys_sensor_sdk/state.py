"""Component state and command enums wrapping proto int values."""

from enum import IntEnum


class ComponentState(IntEnum):
    """Component lifecycle states (matches proto ComponentState enum values)."""

    UNKNOWN = 0
    STARTING = 1
    ACTIVE = 2
    PAUSED = 3
    STOPPING = 4
    STOPPED = 5
    ERROR = 6
    DEAD = 7


class Command(IntEnum):
    """Lifecycle commands (matches proto Command enum values)."""

    UNSPECIFIED = 0
    START = 1
    STOP = 2
    PAUSE = 3
    RESUME = 4
    RELOAD = 5
    HEALTH_CHECK = 6
    RECOVER = 7
