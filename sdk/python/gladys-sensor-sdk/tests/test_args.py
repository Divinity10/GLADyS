"""Tests for typed command arguments with lenient parsing."""

from __future__ import annotations

import pytest

from gladys_sensor_sdk.args import (
    HealthCheckArgs,
    RecoverArgs,
    StartArgs,
    StopArgs,
)


class TestStartArgs:
    """StartArgs parsing and factory tests."""

    def test_defaults(self) -> None:
        args = StartArgs.test_defaults()
        assert args.dry_run is False

    def test_dry_run_factory(self) -> None:
        args = StartArgs.test_dry_run()
        assert args.dry_run is True

    def test_from_dict_with_values(self) -> None:
        args = StartArgs.from_dict({"dry_run": True})
        assert args.dry_run is True

    def test_from_dict_empty(self) -> None:
        args = StartArgs.from_dict({})
        assert args.dry_run is False

    def test_from_dict_wrong_type_uses_default(self) -> None:
        args = StartArgs.from_dict({"dry_run": "not_a_bool"})
        # "not_a_bool" is not in ("true", "1", "yes"), so defaults to False
        assert args.dry_run is False

    def test_from_dict_string_true_coerces(self) -> None:
        args = StartArgs.from_dict({"dry_run": "true"})
        assert args.dry_run is True

    def test_from_dict_int_1_coerces(self) -> None:
        args = StartArgs.from_dict({"dry_run": 1})
        assert args.dry_run is True

    def test_raw_accessor(self) -> None:
        args = StartArgs.from_dict({"dry_run": False, "custom_key": "value"})
        assert args.raw("custom_key") == "value"
        assert args.raw("missing_key", "default") == "default"


class TestStopArgs:
    """StopArgs parsing and factory tests."""

    def test_defaults(self) -> None:
        args = StopArgs.test_defaults()
        assert args.force is False
        assert args.timeout_ms == 5000

    def test_force_factory(self) -> None:
        args = StopArgs.test_force()
        assert args.force is True
        assert args.timeout_ms == 1000

    def test_from_dict_with_values(self) -> None:
        args = StopArgs.from_dict({"force": True, "timeout_ms": 2000})
        assert args.force is True
        assert args.timeout_ms == 2000

    def test_from_dict_empty(self) -> None:
        args = StopArgs.from_dict({})
        assert args.force is False
        assert args.timeout_ms == 5000

    def test_from_dict_timeout_wrong_type(self) -> None:
        args = StopArgs.from_dict({"timeout_ms": "not_a_number"})
        assert args.timeout_ms == 5000

    def test_from_dict_timeout_float_coerces(self) -> None:
        args = StopArgs.from_dict({"timeout_ms": 3000.5})
        assert args.timeout_ms == 3000

    def test_safe_int_nan_returns_default(self) -> None:
        args = StopArgs.from_dict({"timeout_ms": float("nan")})
        assert args.timeout_ms == 5000

    def test_safe_int_infinity_returns_default(self) -> None:
        args = StopArgs.from_dict({"timeout_ms": float("inf")})
        assert args.timeout_ms == 5000

    def test_safe_int_negative_infinity_returns_default(self) -> None:
        args = StopArgs.from_dict({"timeout_ms": float("-inf")})
        assert args.timeout_ms == 5000


class TestRecoverArgs:
    """RecoverArgs parsing and factory tests."""

    def test_defaults(self) -> None:
        args = RecoverArgs.test_defaults()
        assert args.strategy == "default"

    def test_from_dict_with_strategy(self) -> None:
        args = RecoverArgs.from_dict({"strategy": "full_reset"})
        assert args.strategy == "full_reset"

    def test_from_dict_empty(self) -> None:
        args = RecoverArgs.from_dict({})
        assert args.strategy == "default"

    def test_from_dict_none_strategy(self) -> None:
        args = RecoverArgs.from_dict({"strategy": None})
        assert args.strategy == "default"

    def test_raw_accessor(self) -> None:
        args = RecoverArgs.from_dict(
            {"strategy": "default", "custom_strategy": "special"}
        )
        assert args.raw("custom_strategy") == "special"


class TestHealthCheckArgs:
    """HealthCheckArgs parsing and factory tests."""

    def test_defaults(self) -> None:
        args = HealthCheckArgs.test_defaults()
        assert args.deep is False

    def test_deep_factory(self) -> None:
        args = HealthCheckArgs.test_deep()
        assert args.deep is True

    def test_from_dict_with_values(self) -> None:
        args = HealthCheckArgs.from_dict({"deep": True})
        assert args.deep is True

    def test_from_dict_empty(self) -> None:
        args = HealthCheckArgs.from_dict({})
        assert args.deep is False

    def test_from_dict_string_coercion(self) -> None:
        args = HealthCheckArgs.from_dict({"deep": "true"})
        assert args.deep is True


class TestLenientParsing:
    """Cross-cutting lenient parsing tests."""

    def test_missing_fields_use_defaults(self) -> None:
        """All args classes handle missing fields gracefully."""
        assert StartArgs.from_dict({}).dry_run is False
        assert StopArgs.from_dict({}).force is False
        assert StopArgs.from_dict({}).timeout_ms == 5000
        assert RecoverArgs.from_dict({}).strategy == "default"
        assert HealthCheckArgs.from_dict({}).deep is False

    def test_wrong_types_use_defaults(self) -> None:
        """Wrong types fall back to defaults, never throw."""
        assert StartArgs.from_dict({"dry_run": []}).dry_run is False
        assert StopArgs.from_dict({"timeout_ms": []}).timeout_ms == 5000
        assert RecoverArgs.from_dict({"strategy": None}).strategy == "default"
        assert HealthCheckArgs.from_dict({"deep": {}}).deep is False

    def test_extra_fields_available_via_raw(self) -> None:
        """Extra fields are preserved and accessible via raw()."""
        args = StartArgs.from_dict(
            {"dry_run": False, "extra_field": 42, "nested": {"a": 1}}
        )
        assert args.raw("extra_field") == 42
        assert args.raw("nested") == {"a": 1}
        assert args.raw("nonexistent") is None
        assert args.raw("nonexistent", "fallback") == "fallback"
