import pytest
from unittest.mock import AsyncMock, MagicMock

from gladys_orchestrator.learning import LearningModule


@pytest.fixture
def mock_memory():
    return AsyncMock()


@pytest.fixture
def mock_strategy():
    return MagicMock()


@pytest.fixture
def module(mock_memory, mock_strategy):
    return LearningModule(
        memory_client=mock_memory,
        outcome_watcher=None,
        strategy=mock_strategy,
    )


@pytest.mark.asyncio
async def test_on_fire_records_correctly(module, mock_memory):
    """on_fire passes episodic_event_id='' so the DB stores NULL instead of
    an invalid UUID that would cause a FK violation."""
    await module.on_fire(
        heuristic_id="test-h-id",
        event_id="test-event-id",
        condition_text="test condition",
        predicted_success=0.8,
    )

    mock_memory.record_heuristic_fire.assert_called_once_with(
        heuristic_id="test-h-id",
        event_id="test-event-id",
        episodic_event_id="",
    )


@pytest.mark.asyncio
async def test_on_fire_handles_record_failure(module, mock_memory):
    """on_fire catches exceptions from record_heuristic_fire so a DB error
    doesn't crash the pipeline (graceful degradation)."""
    mock_memory.record_heuristic_fire.side_effect = Exception("DB unavailable")

    # Must not raise
    await module.on_fire(
        heuristic_id="test-h-id",
        event_id="test-event-id",
        condition_text="test condition",
        predicted_success=0.8,
    )
