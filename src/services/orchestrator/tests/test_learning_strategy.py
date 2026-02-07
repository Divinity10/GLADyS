import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import UTC, datetime

from gladys_orchestrator.learning import (
    SignalType,
    FeedbackSignal,
    BayesianStrategy,
    BayesianStrategyConfig,
    create_learning_strategy,
    LearningModule,
    FireRecord
)
from gladys_orchestrator.config import OrchestratorConfig


@pytest.fixture
def bayesian_config():
    return BayesianStrategyConfig(
        undo_window_sec=30.0,
        ignored_threshold=3,
        undo_keywords=("undo", "revert"),
        implicit_magnitude=1.0,
        explicit_magnitude=0.8
    )


@pytest.fixture
def strategy(bayesian_config):
    return BayesianStrategy(bayesian_config)


def test_explicit_positive(strategy):
    signal = strategy.interpret_explicit_feedback("e1", "h1", True, "user")
    assert signal.signal_type == SignalType.POSITIVE
    assert signal.heuristic_id == "h1"
    assert signal.event_id == "e1"
    assert signal.magnitude == 0.8
    assert signal.source == "user"


def test_explicit_negative(strategy):
    signal = strategy.interpret_explicit_feedback("e1", "h1", False, "user")
    assert signal.signal_type == SignalType.NEGATIVE
    assert signal.heuristic_id == "h1"
    assert signal.magnitude == 0.8


def test_timeout_returns_positive(strategy):
    signal = strategy.interpret_timeout("h1", "e1", 120.0)
    assert signal.signal_type == SignalType.POSITIVE
    assert signal.heuristic_id == "h1"
    assert signal.event_id == "e1"
    assert signal.magnitude == 1.0
    assert signal.source == "implicit_timeout"


def test_undo_detected(strategy):
    recent_fires = [
        {"heuristic_id": "h1", "event_id": "e1"},
        {"heuristic_id": "h2", "event_id": "e2"}
    ]
    signals = strategy.interpret_event_for_undo("Please undo that", recent_fires)
    assert len(signals) == 2
    assert signals[0].signal_type == SignalType.NEGATIVE
    assert signals[0].heuristic_id == "h1"
    assert signals[0].source == "implicit_undo"
    assert signals[1].heuristic_id == "h2"


def test_undo_no_match(strategy):
    signals = strategy.interpret_event_for_undo("Hello world", [{"heuristic_id": "h1", "event_id": "e1"}])
    assert len(signals) == 0


def test_undo_multiple_keywords(strategy):
    assert len(strategy.interpret_event_for_undo("revert", [{"heuristic_id": "h1", "event_id": "e1"}])) == 1


def test_ignore_below_threshold(strategy):
    signal = strategy.interpret_ignore("h1", 2)
    assert signal.signal_type == SignalType.NEUTRAL


def test_ignore_at_threshold(strategy):
    signal = strategy.interpret_ignore("h1", 3)
    assert signal.signal_type == SignalType.NEGATIVE
    assert signal.magnitude == 1.0
    assert signal.source == "implicit_ignored"


def test_config_property(strategy):
    conf = strategy.config
    assert conf["undo_window_sec"] == 30.0
    assert conf["ignored_threshold"] == 3
    assert "undo" in conf["undo_keywords"]


def test_create_bayesian_strategy():
    mock_config = MagicMock(spec=OrchestratorConfig)
    mock_config.learning_strategy = "bayesian"
    mock_config.learning_undo_window_sec = 45.0
    mock_config.learning_ignored_threshold = 5
    mock_config.learning_undo_keywords = "undo, stop"
    mock_config.learning_implicit_magnitude = 0.9
    mock_config.learning_explicit_magnitude = 0.7
    
    strategy = create_learning_strategy(mock_config)
    assert isinstance(strategy, BayesianStrategy)
    assert strategy.config["undo_window_sec"] == 45.0
    assert strategy.config["ignored_threshold"] == 5
    assert strategy.config["undo_keywords"] == ("undo", "stop")
    assert strategy.config["implicit_magnitude"] == 0.9
    assert strategy.config["explicit_magnitude"] == 0.7


def test_create_unknown_strategy():
    mock_config = MagicMock(spec=OrchestratorConfig)
    mock_config.learning_strategy = "unknown"
    with pytest.raises(ValueError, match="Unknown learning strategy"):
        create_learning_strategy(mock_config)


@pytest.mark.asyncio
async def test_on_feedback_delegates_to_strategy():
    mock_memory = AsyncMock()
    mock_memory.update_heuristic_confidence.return_return_value = {"success": True}
    mock_strategy = MagicMock()
    mock_strategy.interpret_explicit_feedback.return_value = FeedbackSignal(
        signal_type=SignalType.POSITIVE,
        heuristic_id="h1",
        event_id="e1",
        source="user",
        magnitude=0.8
    )
    
    module = LearningModule(memory_client=mock_memory, outcome_watcher=None, strategy=mock_strategy)
    # Ensure it returns a real dict, not a coroutine
    mock_memory.update_heuristic_confidence.return_value = {"success": True}
    
    await module.on_feedback("e1", "h1", True, "user")
    
    mock_strategy.interpret_explicit_feedback.assert_called_once_with(
        event_id="e1", heuristic_id="h1", positive=True, source="user"
    )
    mock_memory.update_heuristic_confidence.assert_called_once_with(
        heuristic_id="h1", positive=True, magnitude=0.8, feedback_source="user"
    )


@pytest.mark.asyncio
async def test_apply_signal_skips_neutral():
    mock_memory = AsyncMock()
    module = LearningModule(memory_client=mock_memory, outcome_watcher=None, strategy=MagicMock())
    
    neutral_signal = FeedbackSignal(signal_type=SignalType.NEUTRAL, heuristic_id="h1")
    await module._apply_signal(neutral_signal)
    
    mock_memory.update_heuristic_confidence.assert_not_called()


@pytest.mark.asyncio
async def test_apply_signal_passes_magnitude():
    mock_memory = AsyncMock()
    mock_memory.update_heuristic_confidence.return_value = {"success": True}
    module = LearningModule(memory_client=mock_memory, outcome_watcher=None, strategy=MagicMock())
    
    signal = FeedbackSignal(
        signal_type=SignalType.NEGATIVE,
        heuristic_id="h1",
        magnitude=0.5,
        source="test"
    )
    await module._apply_signal(signal)
    
    mock_memory.update_heuristic_confidence.assert_called_once_with(
        heuristic_id="h1", positive=False, magnitude=0.5, feedback_source="test"
    )
