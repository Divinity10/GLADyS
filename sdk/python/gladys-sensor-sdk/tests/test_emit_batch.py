"""Batch emission tests for EventDispatcher.emit_batch()."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest

from gladys_sensor_sdk.client import GladysClient
from gladys_sensor_sdk.config import TimeoutConfig
from gladys_sensor_sdk.events import EmitResult, EventBuilder, EventDispatcher
from gladys_sensor_sdk.flow_control import FlowStrategy, RateLimitStrategy


def _mock_client() -> GladysClient:
    client = GladysClient("", TimeoutConfig.no_timeout())
    client.publish_event = AsyncMock()  # type: ignore[method-assign]
    client.publish_events = AsyncMock()  # type: ignore[method-assign]
    return client


def _event(label: str, *, threat: bool = False, priority: float = 0.0) -> dict:
    builder = EventBuilder(source="sensor").text(label).structured(
        {"priority": priority}
    )
    if threat:
        builder = builder.threat(True)
    return builder.build()


def _label(event: dict) -> str:
    return str(event.get("raw_text", ""))


def _sent_labels(client: GladysClient) -> list[str]:
    labels: list[str] = []
    for call in client.publish_event.await_args_list:  # type: ignore[attr-defined]
        labels.append(_label(call.args[0]))
    for call in client.publish_events.await_args_list:  # type: ignore[attr-defined]
        labels.extend(_label(event) for event in call.args[0])
    return labels


class _BudgetStrategy:
    def __init__(self, budget: int) -> None:
        self._budget = budget
        self.available_calls = 0
        self.consume_calls: list[int] = []

    def should_publish(self, event: object) -> bool:
        _ = event
        return True

    def available_tokens(self) -> int:
        self.available_calls += 1
        return self._budget

    def consume(self, n: int) -> None:
        self.consume_calls.append(n)
        self._budget -= n


def _make_dispatcher(
    strategy: FlowStrategy,
    priority_fn: Callable[[dict], float] | None = None,
) -> tuple[GladysClient, EventDispatcher]:
    client = _mock_client()
    dispatcher = EventDispatcher(
        client,
        source="sensor",
        strategy=strategy,
        priority_fn=priority_fn,
    )
    return client, dispatcher


@pytest.mark.asyncio
async def test_emit_batch_empty_list() -> None:
    strategy = _BudgetStrategy(10)
    client, dispatcher = _make_dispatcher(strategy)

    result = await dispatcher.emit_batch([])

    assert result == EmitResult(sent=0, suppressed=0)
    assert strategy.available_calls == 0
    assert strategy.consume_calls == []
    client.publish_event.assert_not_awaited()  # type: ignore[attr-defined]
    client.publish_events.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_emit_batch_all_threats() -> None:
    strategy = _BudgetStrategy(0)
    client, dispatcher = _make_dispatcher(strategy)
    events = [_event("t1", threat=True), _event("t2", threat=True)]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=0)
    assert strategy.available_calls == 0
    assert strategy.consume_calls == []
    assert _sent_labels(client) == ["t1", "t2"]


@pytest.mark.asyncio
async def test_emit_batch_all_within_budget() -> None:
    strategy = _BudgetStrategy(3)
    client, dispatcher = _make_dispatcher(strategy)
    events = [_event("a"), _event("b"), _event("c")]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=3, suppressed=0)
    assert strategy.consume_calls == [3]
    assert _sent_labels(client) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_emit_batch_zero_budget() -> None:
    strategy = _BudgetStrategy(0)
    client, dispatcher = _make_dispatcher(strategy)
    events = [_event("t", threat=True), _event("a"), _event("b")]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=1, suppressed=2)
    assert dispatcher.events_filtered == 2
    assert strategy.consume_calls == []
    assert _sent_labels(client) == ["t"]


@pytest.mark.asyncio
async def test_emit_batch_single_event() -> None:
    strategy = _BudgetStrategy(1)
    client, dispatcher = _make_dispatcher(strategy)
    event = _event("single")

    result = await dispatcher.emit_batch([event])

    assert result == EmitResult(sent=1, suppressed=0)
    assert strategy.consume_calls == [1]
    client.publish_event.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_emit_batch_fifo_when_no_priority_fn() -> None:
    strategy = _BudgetStrategy(2)
    client, dispatcher = _make_dispatcher(strategy)
    events = [_event("a"), _event("b"), _event("c")]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=1)
    assert _sent_labels(client) == ["a", "b"]


@pytest.mark.asyncio
async def test_emit_batch_priority_fn_selects_top_n() -> None:
    strategy = _BudgetStrategy(2)
    priority_fn = lambda event: float(event["structured"]["priority"])
    client, dispatcher = _make_dispatcher(strategy, priority_fn)
    events = [
        _event("a", priority=1),
        _event("b", priority=10),
        _event("c", priority=5),
    ]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=1)
    assert _sent_labels(client) == ["b", "c"]


@pytest.mark.asyncio
async def test_emit_batch_priority_fn_preserves_order() -> None:
    strategy = _BudgetStrategy(2)
    priority_fn = lambda event: float(event["structured"]["priority"])
    client, dispatcher = _make_dispatcher(strategy, priority_fn)
    events = [
        _event("a", priority=5),
        _event("b", priority=1),
        _event("c", priority=10),
    ]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=1)
    assert _sent_labels(client) == ["a", "c"]


@pytest.mark.asyncio
async def test_emit_batch_equal_priority_preserves_order() -> None:
    strategy = _BudgetStrategy(2)
    client, dispatcher = _make_dispatcher(strategy, lambda event: 1.0)
    events = [_event("a"), _event("b"), _event("c")]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=1)
    assert _sent_labels(client) == ["a", "b"]


@pytest.mark.asyncio
async def test_emit_batch_threats_bypass_budget() -> None:
    strategy = _BudgetStrategy(0)
    client, dispatcher = _make_dispatcher(strategy)
    events = [
        _event("t1", threat=True),
        _event("a"),
        _event("t2", threat=True),
        _event("b"),
    ]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=2, suppressed=2)
    assert _sent_labels(client) == ["t1", "t2"]


@pytest.mark.asyncio
async def test_emit_batch_threats_dont_consume_tokens() -> None:
    with patch(
        "gladys_sensor_sdk.flow_control.time.monotonic",
        return_value=0.0,
    ):
        strategy = RateLimitStrategy(max_events=5, window_seconds=10)
        client, dispatcher = _make_dispatcher(strategy)
        events = [_event(f"t{i}", threat=True) for i in range(10)]
        before = strategy.available_tokens()

        result = await dispatcher.emit_batch(events)

        after = strategy.available_tokens()

    assert result == EmitResult(sent=10, suppressed=0)
    assert before == 5
    assert after == 5
    assert len(_sent_labels(client)) == 10


@pytest.mark.asyncio
async def test_emit_batch_mixed_threats_and_candidates() -> None:
    strategy = _BudgetStrategy(1)
    client, dispatcher = _make_dispatcher(strategy)
    events = [
        _event("t1", threat=True),
        _event("a"),
        _event("b"),
        _event("t2", threat=True),
    ]

    result = await dispatcher.emit_batch(events)

    assert result == EmitResult(sent=3, suppressed=1)
    assert _sent_labels(client) == ["t1", "a", "t2"]


@pytest.mark.asyncio
async def test_emit_batch_updates_events_filtered() -> None:
    strategy = _BudgetStrategy(1)
    _, dispatcher = _make_dispatcher(strategy)
    events = [_event("a"), _event("b"), _event("c")]

    result = await dispatcher.emit_batch(events)

    assert result.suppressed == 2
    assert dispatcher.events_filtered == 2


@pytest.mark.asyncio
async def test_emit_batch_updates_events_published() -> None:
    strategy = _BudgetStrategy(1)
    _, dispatcher = _make_dispatcher(strategy)
    events = [_event("t", threat=True), _event("a"), _event("b")]

    result = await dispatcher.emit_batch(events)

    assert result.sent == 2
    assert dispatcher.events_published == 2


@pytest.mark.asyncio
async def test_emit_result_sent_plus_suppressed_equals_total() -> None:
    scenarios = [
        (0, []),
        (0, [_event("a"), _event("b"), _event("t", threat=True)]),
        (2, [_event("a"), _event("b"), _event("c")]),
        (1, [_event("t", threat=True), _event("a"), _event("b")]),
    ]

    for budget, events in scenarios:
        strategy = _BudgetStrategy(budget)
        _, dispatcher = _make_dispatcher(strategy)
        result = await dispatcher.emit_batch(events)
        assert result.sent + result.suppressed == len(events)
