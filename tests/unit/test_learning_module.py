"""Unit tests for the LearningModule facade.

Tests all interface methods and implicit feedback signals:
- on_feedback() → explicit confidence update
- on_fire() → flight recorder + outcome watcher registration
- on_outcome() → implicit confidence update
- check_event_for_outcomes() → pattern matching + undo detection
- on_heuristic_ignored() → ignored-3x negative feedback
- cleanup_expired() → timeout = positive feedback
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path

# Add orchestrator to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "services" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "lib" / "gladys_common"))

from gladys_orchestrator.learning import LearningModule, UNDO_WINDOW_SEC, IGNORED_THRESHOLD
from gladys_orchestrator.outcome_watcher import OutcomeWatcher, OutcomePattern, PendingOutcome


@pytest.fixture
def memory_client():
    """Mock memory client with all required methods."""
    client = AsyncMock()
    client.update_heuristic_confidence.return_value = {
        "success": True,
        "old_confidence": 0.5,
        "new_confidence": 0.6,
        "delta": 0.1,
        "td_error": 0.0,
    }
    client.record_heuristic_fire.return_value = "fire-id-123"
    client.get_heuristic.return_value = {
        "id": "h-1",
        "condition_text": "test condition",
        "confidence": 0.5,
    }
    return client


@pytest.fixture
def outcome_watcher(memory_client):
    """OutcomeWatcher with a simple test pattern."""
    patterns = [
        OutcomePattern(
            trigger_pattern="oven",
            outcome_pattern="oven off",
            timeout_sec=10,
            is_success=True,
        ),
    ]
    return OutcomeWatcher(patterns=patterns, memory_client=memory_client)


@pytest.fixture
def learning_module(memory_client, outcome_watcher):
    """LearningModule with mocked dependencies."""
    return LearningModule(
        memory_client=memory_client,
        outcome_watcher=outcome_watcher,
    )


@pytest.fixture
def learning_module_no_watcher(memory_client):
    """LearningModule without an outcome watcher."""
    return LearningModule(
        memory_client=memory_client,
        outcome_watcher=None,
    )


# ---------------------------------------------------------------------------
# on_feedback tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_feedback_explicit_positive(learning_module, memory_client):
    await learning_module.on_feedback(
        event_id="evt-1",
        heuristic_id="h-1",
        positive=True,
        source="explicit",
    )
    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=True,
        feedback_source="explicit",
    )


@pytest.mark.asyncio
async def test_on_feedback_explicit_negative(learning_module, memory_client):
    await learning_module.on_feedback(
        event_id="evt-1",
        heuristic_id="h-1",
        positive=False,
        source="explicit",
    )
    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=False,
        feedback_source="explicit",
    )


@pytest.mark.asyncio
async def test_on_feedback_no_memory_client():
    module = LearningModule(memory_client=None, outcome_watcher=None)
    # Should not raise
    await module.on_feedback("evt-1", "h-1", True, "explicit")


# ---------------------------------------------------------------------------
# on_fire tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_fire_records_and_registers(learning_module, memory_client, outcome_watcher):
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="When the oven is left on",
        predicted_success=0.7,
    )

    # Should call record_heuristic_fire on memory client
    memory_client.record_heuristic_fire.assert_awaited_once_with(
        heuristic_id="h-1",
        event_id="evt-1",
    )

    # Should register with outcome watcher (oven pattern matches)
    assert outcome_watcher.pending_count == 1


@pytest.mark.asyncio
async def test_on_fire_no_pattern_match(learning_module, memory_client, outcome_watcher):
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="Something about weather",
        predicted_success=0.5,
    )

    # Fire still recorded
    memory_client.record_heuristic_fire.assert_awaited_once()
    # But no outcome expectation (no pattern match)
    assert outcome_watcher.pending_count == 0


# ---------------------------------------------------------------------------
# on_outcome tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_outcome_success(learning_module, memory_client):
    await learning_module.on_outcome(
        heuristic_id="h-1",
        event_id="evt-1",
        outcome="success",
    )
    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=True,
        feedback_source="implicit",
    )


@pytest.mark.asyncio
async def test_on_outcome_fail(learning_module, memory_client):
    await learning_module.on_outcome(
        heuristic_id="h-1",
        event_id="evt-1",
        outcome="fail",
    )
    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=False,
        feedback_source="implicit",
    )


# ---------------------------------------------------------------------------
# check_event_for_outcomes tests (pattern match + undo)
# ---------------------------------------------------------------------------

@dataclass
class FakeEvent:
    raw_text: str = ""
    id: str = "fake-evt"


@pytest.mark.asyncio
async def test_check_event_resolves_outcome(learning_module, memory_client):
    # Register a fire first (oven pattern)
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="When the oven is left on",
        predicted_success=0.7,
    )

    # Send outcome event
    event = FakeEvent(raw_text="User turned the oven off")
    resolved = await learning_module.check_event_for_outcomes(event)
    assert "h-1" in resolved


@pytest.mark.asyncio
async def test_check_event_undo_signal(learning_module, memory_client):
    # Register a fire
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="Something",
        predicted_success=0.5,
    )

    # Send undo event within window
    event = FakeEvent(raw_text="User wants to undo the last action")
    resolved = await learning_module.check_event_for_outcomes(event)
    assert "h-1" in resolved

    # Verify negative feedback was sent
    calls = memory_client.update_heuristic_confidence.call_args_list
    # Find the implicit call (on_outcome sends it)
    implicit_calls = [c for c in calls if c.kwargs.get("feedback_source") == "implicit"]
    assert len(implicit_calls) >= 1
    assert implicit_calls[-1].kwargs["positive"] is False


@pytest.mark.asyncio
async def test_check_event_no_undo_outside_window(learning_module, memory_client):
    # Register a fire with old timestamp
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="Something",
        predicted_success=0.5,
    )

    # Manually backdate the fire record
    async with learning_module._fires_lock:
        for r in learning_module._recent_fires:
            r.fire_time = datetime.utcnow() - timedelta(seconds=UNDO_WINDOW_SEC + 10)

    event = FakeEvent(raw_text="User wants to undo the last action")
    resolved = await learning_module.check_event_for_outcomes(event)
    # h-1 should NOT be in resolved (outside undo window)
    assert "h-1" not in resolved


# ---------------------------------------------------------------------------
# on_heuristic_ignored tests (ignored 3x = negative)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ignored_3x_sends_negative(learning_module, memory_client):
    # First two ignores — no feedback
    await learning_module.on_heuristic_ignored("h-1")
    await learning_module.on_heuristic_ignored("h-1")
    # update_heuristic_confidence may have been called from other fixture setup;
    # reset to track only the ignored signal
    memory_client.update_heuristic_confidence.reset_mock()

    # Third ignore — should trigger negative feedback
    await learning_module.on_heuristic_ignored("h-1")
    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=False,
        feedback_source="implicit",
    )


@pytest.mark.asyncio
async def test_ignored_counter_resets_on_explicit_feedback(learning_module, memory_client):
    await learning_module.on_heuristic_ignored("h-1")
    await learning_module.on_heuristic_ignored("h-1")

    # Explicit feedback resets counter
    await learning_module.on_feedback("evt-1", "h-1", True, "explicit")
    memory_client.update_heuristic_confidence.reset_mock()

    # Two more ignores — should NOT trigger (counter was reset)
    await learning_module.on_heuristic_ignored("h-1")
    await learning_module.on_heuristic_ignored("h-1")
    memory_client.update_heuristic_confidence.assert_not_awaited()


# ---------------------------------------------------------------------------
# cleanup_expired tests (timeout = positive)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_sends_positive_feedback(learning_module, memory_client, outcome_watcher):
    # Register a fire with oven pattern
    await learning_module.on_fire(
        heuristic_id="h-1",
        event_id="evt-1",
        condition_text="When the oven is left on",
        predicted_success=0.7,
    )
    assert outcome_watcher.pending_count == 1

    # Manually expire the pending outcome
    async with outcome_watcher._lock:
        for p in outcome_watcher._pending:
            p.timeout_at = datetime.utcnow() - timedelta(seconds=1)

    memory_client.update_heuristic_confidence.reset_mock()

    # Cleanup should send positive feedback
    expired = await learning_module.cleanup_expired()
    assert expired == 1

    memory_client.update_heuristic_confidence.assert_awaited_once_with(
        heuristic_id="h-1",
        positive=True,
        feedback_source="implicit",
    )


@pytest.mark.asyncio
async def test_cleanup_no_watcher(learning_module_no_watcher):
    result = await learning_module_no_watcher.cleanup_expired()
    assert result == 0
