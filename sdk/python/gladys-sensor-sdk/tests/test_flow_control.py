"""Tests for flow control strategies and EventDispatcher integration."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from gladys_sensor_sdk.client import GladysClient
from gladys_sensor_sdk.config import TimeoutConfig
from gladys_sensor_sdk.events import EventBuilder, EventDispatcher
from gladys_sensor_sdk.flow_control import (
    NoOpStrategy,
    RateLimitStrategy,
    create_strategy,
)


def _mock_client() -> GladysClient:
    client = GladysClient("", TimeoutConfig.no_timeout())
    client.publish_event = AsyncMock()  # type: ignore[method-assign]
    client.publish_events = AsyncMock()  # type: ignore[method-assign]
    return client


def test_noop_always_allows() -> None:
    strategy = NoOpStrategy()
    assert strategy.should_publish({"event": "a"}) is True
    assert strategy.should_publish({"event": "b"}) is True


def test_noop_available_tokens_returns_max() -> None:
    strategy = NoOpStrategy()
    assert strategy.available_tokens() == sys.maxsize


def test_noop_consume_is_noop() -> None:
    strategy = NoOpStrategy()
    before = strategy.available_tokens()
    strategy.consume(10)
    assert strategy.available_tokens() == before


def test_rate_limit_allows_within_budget() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        side_effect=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ):
        strategy = RateLimitStrategy(max_events=5, window_seconds=1)
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True


def test_rate_limit_blocks_over_budget() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        side_effect=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ):
        strategy = RateLimitStrategy(max_events=5, window_seconds=1)
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is False


def test_rate_limit_refills_over_time() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        side_effect=[0.0, 0.0, 0.0, 0.0, 1.1],
    ):
        strategy = RateLimitStrategy(max_events=2, window_seconds=2)
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is True
        assert strategy.should_publish({}) is False
        assert strategy.should_publish({}) is True


def test_rate_limit_available_tokens_reflects_budget() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        strategy = RateLimitStrategy(max_events=5, window_seconds=1)
        strategy.should_publish({})
        strategy.should_publish({})
        assert strategy.available_tokens() == 3


def test_rate_limit_consume_decrements_tokens() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        strategy = RateLimitStrategy(max_events=10, window_seconds=1)
        strategy.consume(5)
        assert strategy.available_tokens() == 5


def test_rate_limit_rejects_zero_max_events() -> None:
    with pytest.raises(ValueError):
        RateLimitStrategy(max_events=0, window_seconds=1)


def test_rate_limit_rejects_zero_window() -> None:
    with pytest.raises(ValueError):
        RateLimitStrategy(max_events=1, window_seconds=0)


def test_rate_limit_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        RateLimitStrategy(max_events=-1, window_seconds=1)
    with pytest.raises(ValueError):
        RateLimitStrategy(max_events=1, window_seconds=-1)


def test_create_none_strategy() -> None:
    strategy = create_strategy({"strategy": "none"})
    assert isinstance(strategy, NoOpStrategy)


def test_create_rate_limit_strategy() -> None:
    strategy = create_strategy(
        {"strategy": "rate_limit", "max_events": 5, "window_seconds": 1}
    )
    assert isinstance(strategy, RateLimitStrategy)


def test_create_unknown_falls_back_to_noop() -> None:
    strategy = create_strategy({"strategy": "mystery"})
    assert isinstance(strategy, NoOpStrategy)


def test_create_default_is_noop() -> None:
    strategy = create_strategy({})
    assert isinstance(strategy, NoOpStrategy)


@pytest.mark.asyncio
async def test_emit_with_noop_strategy_publishes() -> None:
    client = _mock_client()
    dispatcher = EventDispatcher(client, source="s", strategy=NoOpStrategy())

    event = EventBuilder(source="s").text("test").build()
    result = await dispatcher.emit(event)

    assert result is True
    client.publish_event.assert_awaited_once_with(event)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_emit_with_rate_limit_blocks_excess() -> None:
    client = _mock_client()
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        side_effect=[0.0, 0.0, 0.0],
    ):
        dispatcher = EventDispatcher(
            client,
            source="s",
            strategy=RateLimitStrategy(max_events=1, window_seconds=10),
        )
        first = await dispatcher.emit(
            EventBuilder(source="s").text("first").build()
        )
        second = await dispatcher.emit(
            EventBuilder(source="s").text("second").build()
        )

    assert first is True
    assert second is False
    assert client.publish_event.await_count == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_emit_threat_bypasses_rate_limit() -> None:
    client = _mock_client()
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        side_effect=[0.0, 0.0, 0.0],
    ):
        dispatcher = EventDispatcher(
            client,
            source="s",
            strategy=RateLimitStrategy(max_events=1, window_seconds=10),
        )
        await dispatcher.emit(EventBuilder(source="s").text("normal").build())
        threat = EventBuilder(source="s").text("danger").threat(True).build()
        result = await dispatcher.emit(threat)

    assert result is True
    assert client.publish_event.await_count == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_emit_returns_true_when_published() -> None:
    client = _mock_client()
    dispatcher = EventDispatcher(client, source="s", strategy=NoOpStrategy())
    result = await dispatcher.emit(EventBuilder(source="s").text("ok").build())
    assert result is True


@pytest.mark.asyncio
async def test_emit_returns_false_when_suppressed() -> None:
    client = _mock_client()
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        dispatcher = EventDispatcher(
            client,
            source="s",
            strategy=RateLimitStrategy(max_events=1, window_seconds=10),
        )
        await dispatcher.emit(EventBuilder(source="s").text("first").build())
        result = await dispatcher.emit(
            EventBuilder(source="s").text("blocked").build()
        )
    assert result is False


@pytest.mark.asyncio
async def test_emit_threat_returns_true_when_rate_limited() -> None:
    client = _mock_client()
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        dispatcher = EventDispatcher(
            client,
            source="s",
            strategy=RateLimitStrategy(max_events=1, window_seconds=10),
        )
        await dispatcher.emit(EventBuilder(source="s").text("first").build())
        result = await dispatcher.emit(
            EventBuilder(source="s").text("danger").threat(True).build()
        )
    assert result is True


@pytest.mark.asyncio
async def test_events_filtered_increments_on_suppression() -> None:
    client = _mock_client()
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        dispatcher = EventDispatcher(
            client,
            source="s",
            strategy=RateLimitStrategy(max_events=1, window_seconds=10),
        )
        await dispatcher.emit(EventBuilder(source="s").text("first").build())
        await dispatcher.emit(EventBuilder(source="s").text("blocked").build())
    assert dispatcher.events_filtered == 1


@pytest.mark.asyncio
async def test_events_published_increments_on_send() -> None:
    client = _mock_client()
    dispatcher = EventDispatcher(client, source="s", strategy=NoOpStrategy())
    await dispatcher.emit(EventBuilder(source="s").text("sent").build())
    assert dispatcher.events_published == 1


def test_counters_zero_initially() -> None:
    client = _mock_client()
    dispatcher = EventDispatcher(client, source="s", strategy=NoOpStrategy())
    assert dispatcher.events_filtered == 0
    assert dispatcher.events_published == 0


class _DenyStrategy:
    def should_publish(self, event: Any) -> bool:
        return False

    def available_tokens(self) -> int:
        return 0

    def consume(self, n: int) -> None:
        _ = n


@pytest.mark.asyncio
async def test_set_strategy_replaces_strategy() -> None:
    client = _mock_client()
    dispatcher = EventDispatcher(
        client,
        source="s",
        strategy=_DenyStrategy(),  # type: ignore[arg-type]
    )

    await dispatcher.emit(EventBuilder(source="s").text("blocked").build())
    dispatcher.set_strategy(NoOpStrategy())
    allowed = EventBuilder(source="s").text("allowed").build()
    await dispatcher.emit(allowed)

    client.publish_event.assert_awaited_once_with(allowed)  # type: ignore[attr-defined]
