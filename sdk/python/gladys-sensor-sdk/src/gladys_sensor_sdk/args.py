"""Typed command arguments with lenient parsing.

Each command has a typed args class with named accessors, default values,
and a raw() escape hatch for undocumented fields. Parsing is lenient:
missing fields get defaults, wrong types get defaults, never throws.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommandArgs:
    """Base class for all typed command arguments.

    Provides lenient raw() accessor for unknown fields.
    """

    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def raw(self, key: str, default: Any = None) -> Any:
        """Get raw argument value (escape hatch for undocumented args).

        Args:
            key: Argument name.
            default: Default value if key not found.

        Returns:
            Argument value or default.
        """
        return self._raw.get(key, default)


def _safe_bool(value: Any, default: bool) -> bool:
    """Coerce value to bool leniently. Returns default on failure."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_int(value: Any, default: int) -> int:
    """Coerce value to int leniently. Returns default on failure."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        try:
            return int(value)
        except (ValueError, OverflowError):
            return default
    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    return default


def _safe_str(value: Any, default: str) -> str:
    """Coerce value to str leniently. Returns default on failure."""
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


@dataclass(frozen=True)
class StartArgs(CommandArgs):
    """Arguments for START command.

    Attributes:
        dry_run: Validate config without starting.
    """

    dry_run: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StartArgs:
        """Parse args from dict (lenient parsing).

        Missing fields get defaults. Wrong types get defaults.
        Never raises exceptions.
        """
        return cls(
            dry_run=_safe_bool(raw.get("dry_run"), False),
            _raw=raw,
        )

    @classmethod
    def test_defaults(cls) -> StartArgs:
        """Factory for tests (normal startup)."""
        return cls()

    @classmethod
    def test_dry_run(cls) -> StartArgs:
        """Factory for tests (dry run mode)."""
        return cls(dry_run=True)


@dataclass(frozen=True)
class StopArgs(CommandArgs):
    """Arguments for STOP command.

    Attributes:
        force: Skip graceful shutdown.
        timeout_ms: Shutdown timeout in milliseconds.
    """

    force: bool = False
    timeout_ms: int = 5000

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StopArgs:
        """Parse args from dict (lenient parsing).

        Missing fields get defaults. Wrong types get defaults.
        Never raises exceptions.
        """
        return cls(
            force=_safe_bool(raw.get("force"), False),
            timeout_ms=_safe_int(raw.get("timeout_ms"), 5000),
            _raw=raw,
        )

    @classmethod
    def test_defaults(cls) -> StopArgs:
        """Factory for tests (graceful shutdown)."""
        return cls()

    @classmethod
    def test_force(cls) -> StopArgs:
        """Factory for tests (force shutdown)."""
        return cls(force=True, timeout_ms=1000)


@dataclass(frozen=True)
class RecoverArgs(CommandArgs):
    """Arguments for RECOVER command.

    Attributes:
        strategy: Recovery strategy identifier.
    """

    strategy: str = "default"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RecoverArgs:
        """Parse args from dict (lenient parsing).

        Missing fields get defaults. Wrong types get defaults.
        Never raises exceptions.
        """
        return cls(
            strategy=_safe_str(raw.get("strategy"), "default"),
            _raw=raw,
        )

    @classmethod
    def test_defaults(cls) -> RecoverArgs:
        """Factory for tests (default strategy)."""
        return cls()


@dataclass(frozen=True)
class HealthCheckArgs(CommandArgs):
    """Arguments for HEALTH_CHECK command.

    Attributes:
        deep: Perform comprehensive health check.
    """

    deep: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HealthCheckArgs:
        """Parse args from dict (lenient parsing).

        Missing fields get defaults. Wrong types get defaults.
        Never raises exceptions.
        """
        return cls(
            deep=_safe_bool(raw.get("deep"), False),
            _raw=raw,
        )

    @classmethod
    def test_defaults(cls) -> HealthCheckArgs:
        """Factory for tests (standard health check)."""
        return cls()

    @classmethod
    def test_deep(cls) -> HealthCheckArgs:
        """Factory for tests (deep health check)."""
        return cls(deep=True)
