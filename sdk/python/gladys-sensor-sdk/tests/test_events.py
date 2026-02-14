"""Tests for EventBuilder, Intent, and EventDispatcher."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from gladys_sensor_sdk.config import TimeoutConfig
from gladys_sensor_sdk.client import GladysClient
from gladys_sensor_sdk.events import EventBuilder, EventDispatcher, Intent


class TestIntent:
    """Intent constant tests."""

    def test_constants(self) -> None:
        assert Intent.ACTIONABLE == "actionable"
        assert Intent.INFORMATIONAL == "informational"
        assert Intent.UNKNOWN == "unknown"


class TestEventBuilder:
    """EventBuilder fluent API tests."""

    def test_basic_event(self) -> None:
        event = EventBuilder(source="sensor-1").build()
        assert event["source"] == "sensor-1"
        assert event["intent"] == Intent.UNKNOWN
        assert "id" in event
        assert "timestamp" in event

    def test_text(self) -> None:
        event = EventBuilder(source="s").text("hello world").build()
        assert event["raw_text"] == "hello world"

    def test_structured(self) -> None:
        data = {"key": "value", "num": 42}
        event = EventBuilder(source="s").structured(data).build()
        assert event["structured"] == data

    def test_intent(self) -> None:
        event = (
            EventBuilder(source="s").intent(Intent.ACTIONABLE).build()
        )
        assert event["intent"] == Intent.ACTIONABLE

    def test_threat(self) -> None:
        event = EventBuilder(source="s").threat(True).build()
        assert event["salience"]["threat"] is True

    def test_threat_false(self) -> None:
        event = EventBuilder(source="s").threat(False).build()
        assert event["salience"]["threat"] is False

    def test_evaluation_data(self) -> None:
        data = {"answer": "42"}
        event = EventBuilder(source="s").evaluation_data(data).build()
        assert event["evaluation_data"] == data

    def test_fluent_chaining(self) -> None:
        event = (
            EventBuilder(source="sensor-1")
            .text("Player took damage")
            .structured({"damage": 50})
            .intent(Intent.ACTIONABLE)
            .threat(True)
            .evaluation_data({"solution": "heal"})
            .build()
        )
        assert event["source"] == "sensor-1"
        assert event["raw_text"] == "Player took damage"
        assert event["structured"]["damage"] == 50
        assert event["intent"] == Intent.ACTIONABLE
        assert event["salience"]["threat"] is True
        assert event["evaluation_data"]["solution"] == "heal"

    def test_is_threat_property(self) -> None:
        builder = EventBuilder(source="s").threat(True)
        assert builder.is_threat is True

    def test_is_threat_false_by_default(self) -> None:
        builder = EventBuilder(source="s")
        assert builder.is_threat is False

    def test_unique_ids(self) -> None:
        e1 = EventBuilder(source="s").build()
        e2 = EventBuilder(source="s").build()
        assert e1["id"] != e2["id"]


class TestEventDispatcherImmediate:
    """EventDispatcher immediate mode tests."""

    @pytest.fixture
    def client(self) -> GladysClient:
        c = GladysClient("", TimeoutConfig.no_timeout())
        c.publish_event = AsyncMock()  # type: ignore[method-assign]
        c.publish_events = AsyncMock()  # type: ignore[method-assign]
        return c

    @pytest.mark.asyncio
    async def test_immediate_mode_sends_immediately(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(client, source="s", flush_interval_ms=0)
        assert dispatcher.is_immediate is True

        event = EventBuilder(source="s").text("test").build()
        await dispatcher.emit(event)

        client.publish_event.assert_awaited_once_with(event)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_immediate_mode_no_buffering(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(client, source="s", flush_interval_ms=0)
        event = EventBuilder(source="s").text("test").build()
        await dispatcher.emit(event)
        assert dispatcher.buffered_count == 0


class TestEventDispatcherScheduled:
    """EventDispatcher scheduled mode tests."""

    @pytest.fixture
    def client(self) -> GladysClient:
        c = GladysClient("", TimeoutConfig.no_timeout())
        c.publish_event = AsyncMock()  # type: ignore[method-assign]
        c.publish_events = AsyncMock()  # type: ignore[method-assign]
        return c

    @pytest.mark.asyncio
    async def test_scheduled_mode_buffers_events(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client, source="s", flush_interval_ms=600
        )
        assert dispatcher.is_scheduled is True

        event = EventBuilder(source="s").text("test").build()
        await dispatcher.emit(event)

        assert dispatcher.buffered_count == 1
        client.publish_event.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_manual_flush_sends_buffered(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client, source="s", flush_interval_ms=600
        )

        e1 = EventBuilder(source="s").text("first").build()
        e2 = EventBuilder(source="s").text("second").build()
        await dispatcher.emit(e1)
        await dispatcher.emit(e2)

        assert dispatcher.buffered_count == 2
        await dispatcher.flush()
        assert dispatcher.buffered_count == 0
        client.publish_events.assert_awaited_once_with([e1, e2])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_flush_single_event_uses_publish_event(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client, source="s", flush_interval_ms=600
        )

        event = EventBuilder(source="s").text("single").build()
        await dispatcher.emit(event)
        await dispatcher.flush()

        client.publish_event.assert_awaited_once_with(event)  # type: ignore[attr-defined]
        client.publish_events.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_is_noop(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client, source="s", flush_interval_ms=600
        )
        await dispatcher.flush()
        client.publish_event.assert_not_awaited()  # type: ignore[attr-defined]
        client.publish_events.assert_not_awaited()  # type: ignore[attr-defined]


class TestEventDispatcherHybrid:
    """EventDispatcher hybrid mode (scheduled + threat bypass) tests."""

    @pytest.fixture
    def client(self) -> GladysClient:
        c = GladysClient("", TimeoutConfig.no_timeout())
        c.publish_event = AsyncMock()  # type: ignore[method-assign]
        c.publish_events = AsyncMock()  # type: ignore[method-assign]
        return c

    @pytest.mark.asyncio
    async def test_threat_bypasses_buffer(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client,
            source="s",
            flush_interval_ms=600,
            immediate_on_threat=True,
        )

        threat_event = (
            EventBuilder(source="s").text("danger").threat(True).build()
        )
        await dispatcher.emit(threat_event)

        # Threat sent immediately, not buffered
        client.publish_event.assert_awaited_once_with(threat_event)  # type: ignore[attr-defined]
        assert dispatcher.buffered_count == 0

    @pytest.mark.asyncio
    async def test_non_threat_buffers_normally(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client,
            source="s",
            flush_interval_ms=600,
            immediate_on_threat=True,
        )

        normal_event = EventBuilder(source="s").text("normal").build()
        await dispatcher.emit(normal_event)

        client.publish_event.assert_not_awaited()  # type: ignore[attr-defined]
        assert dispatcher.buffered_count == 1

    @pytest.mark.asyncio
    async def test_threat_bypass_disabled(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client,
            source="s",
            flush_interval_ms=600,
            immediate_on_threat=False,
        )

        threat_event = (
            EventBuilder(source="s").text("danger").threat(True).build()
        )
        await dispatcher.emit(threat_event)

        # With immediate_on_threat=False, threat events are buffered
        client.publish_event.assert_not_awaited()  # type: ignore[attr-defined]
        assert dispatcher.buffered_count == 1

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining(
        self, client: GladysClient
    ) -> None:
        dispatcher = EventDispatcher(
            client, source="s", flush_interval_ms=600
        )

        event = EventBuilder(source="s").text("test").build()
        await dispatcher.emit(event)
        assert dispatcher.buffered_count == 1

        await dispatcher.stop()
        assert dispatcher.buffered_count == 0
        client.publish_event.assert_awaited_once_with(event)  # type: ignore[attr-defined]
