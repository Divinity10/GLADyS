import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from gladys_executive.server import (
    HeuristicFirstStrategy,
    HeuristicFirstConfig,
    DecisionContext,
    HeuristicCandidate,
    DecisionPath,
    LLMRequest,
    LLMResponse,
    create_decision_strategy,
    ReasoningTrace
)

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    llm.model_name = "test-model"
    return llm

@pytest.mark.asyncio
async def test_heuristic_path(mock_llm):
    config = HeuristicFirstConfig(confidence_threshold=0.7)
    strategy = HeuristicFirstStrategy(config)
    
    candidate = HeuristicCandidate(
        heuristic_id="h1",
        condition_text="condition1",
        suggested_action="action1",
        confidence=0.8
    )
    
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={"threat": 0.1},
        candidates=[candidate],
        immediate=True
    )
    
    result = await strategy.decide(context, mock_llm)
    
    assert result.path == DecisionPath.HEURISTIC
    assert result.response_text == "action1"
    assert result.matched_heuristic_id == "h1"
    assert result.predicted_success == 0.8
    assert result.prediction_confidence == 0.8
    mock_llm.generate.assert_not_called()

@pytest.mark.asyncio
async def test_llm_path(mock_llm):
    config = HeuristicFirstConfig(confidence_threshold=0.7)
    strategy = HeuristicFirstStrategy(config)
    
    candidate = HeuristicCandidate(
        heuristic_id="h1",
        condition_text="condition1",
        suggested_action="action1",
        confidence=0.5
    )
    
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={"threat": 0.1},
        candidates=[candidate],
        immediate=True
    )
    
    # Mock LLM responses
    mock_llm.generate.side_effect = [
        LLMResponse(text="llm_response", model="test-model"), # First call: generate response
        LLMResponse(text='{"success": 0.9, "confidence": 0.9}', model="test-model") # Second call: prediction
    ]
    
    result = await strategy.decide(context, mock_llm)
    
    assert result.path == DecisionPath.LLM
    assert result.response_text == "llm_response"
    assert result.matched_heuristic_id == "h1"
    # Capped at 0.8
    assert result.predicted_success == 0.8
    assert result.prediction_confidence == 0.8
    
    assert mock_llm.generate.call_count == 2
    
    # Verify candidates in prompt
    request = mock_llm.generate.call_args_list[0][0][0]
    assert 'Context: "condition1"' in request.prompt
    assert 'Response: "action1"' in request.prompt

@pytest.mark.asyncio
async def test_rejected_path_no_llm():
    strategy = HeuristicFirstStrategy()
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=True
    )
    
    result = await strategy.decide(context, None)
    assert result.path == DecisionPath.REJECTED
    assert result.metadata["reason"] == "llm_unavailable"

@pytest.mark.asyncio
async def test_rejected_path_not_immediate(mock_llm):
    strategy = HeuristicFirstStrategy()
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=False
    )
    
    result = await strategy.decide(context, mock_llm)
    assert result.path == DecisionPath.REJECTED
    assert result.metadata["reason"] == "not_immediate"

@pytest.mark.asyncio
async def test_fallback_path(mock_llm):
    strategy = HeuristicFirstStrategy()
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=True
    )
    
    mock_llm.generate.return_value = None
    
    result = await strategy.decide(context, mock_llm)
    assert result.path == DecisionPath.FALLBACK

@pytest.mark.asyncio
async def test_llm_confidence_ceiling(mock_llm):
    config = HeuristicFirstConfig(llm_confidence_ceiling=0.6)
    strategy = HeuristicFirstStrategy(config)
    
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=True
    )
    
    mock_llm.generate.side_effect = [
        LLMResponse(text="llm_response", model="test-model"),
        LLMResponse(text='{"success": 0.9, "confidence": 0.9}', model="test-model")
    ]
    
    result = await strategy.decide(context, mock_llm)
    assert result.predicted_success == 0.6
    assert result.prediction_confidence == 0.6

@pytest.mark.asyncio
async def test_goals_in_prompt(mock_llm):
    strategy = HeuristicFirstStrategy()
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=True,
        goals=["Goal 1", "Goal 2"]
    )
    
    mock_llm.generate.side_effect = [
        LLMResponse(text="llm_response", model="test-model"),
        LLMResponse(text='{"success": 0.5, "confidence": 0.5}', model="test-model")
    ]
    
    await strategy.decide(context, mock_llm)
    
    # Check system prompt in first call
    request = mock_llm.generate.call_args_list[0][0][0]
    assert "Current user goals:" in request.system_prompt
    assert "- Goal 1" in request.system_prompt
    assert "- Goal 2" in request.system_prompt
    
    # Check prediction prompt in second call
    pred_request = mock_llm.generate.call_args_list[1][0][0]
    assert "Success should be evaluated against these goals:" in pred_request.prompt

@pytest.mark.asyncio
async def test_empty_candidates(mock_llm):
    strategy = HeuristicFirstStrategy()
    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[],
        immediate=True
    )
    
    mock_llm.generate.side_effect = [
        LLMResponse(text="llm_response", model="test-model"),
        LLMResponse(text='{"success": 0.5, "confidence": 0.5}', model="test-model")
    ]
    
    result = await strategy.decide(context, mock_llm)
    assert result.path == DecisionPath.LLM
    
    request = mock_llm.generate.call_args_list[0][0][0]
    assert "Previous responses to similar situations" not in request.prompt

def test_create_decision_strategy():
    strategy = create_decision_strategy("heuristic_first", threshold="0.5")
    assert isinstance(strategy, HeuristicFirstStrategy)
    assert strategy._config.confidence_threshold == 0.5
    
    assert create_decision_strategy("unknown") is None

def test_get_trace():
    strategy = HeuristicFirstStrategy()
    trace_id = strategy._store_trace("e1", "ctx", "resp")
    trace = strategy.get_trace(trace_id)
    assert trace is not None
    assert trace.event_id == "e1"
    
    strategy.delete_trace(trace_id)
    assert strategy.get_trace(trace_id) is None

@pytest.mark.asyncio
async def test_personality_bias_lowers_threshold(mock_llm):
    """F-24: Personality bias can lower threshold to accept candidates that would otherwise be rejected."""
    config = HeuristicFirstConfig(confidence_threshold=0.7)
    strategy = HeuristicFirstStrategy(config)

    candidate = HeuristicCandidate(
        heuristic_id="h1",
        condition_text="condition1",
        suggested_action="action1",
        confidence=0.65,  # Below default 0.7 threshold
    )

    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={"threat": 0.1},
        candidates=[candidate],
        immediate=True,
        personality_biases={"confidence_threshold": -0.1},  # Lowers threshold to 0.6
    )

    result = await strategy.decide(context, mock_llm)

    assert result.path == DecisionPath.HEURISTIC
    assert result.matched_heuristic_id == "h1"
    assert result.metadata["threshold"] == pytest.approx(0.6)
    mock_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_personality_bias_clamped():
    """F-24: Extreme bias is clamped to safe range [0.3, 0.95]."""
    config = HeuristicFirstConfig(confidence_threshold=0.7)
    strategy = HeuristicFirstStrategy(config)

    candidate = HeuristicCandidate(
        heuristic_id="h1",
        condition_text="condition1",
        suggested_action="action1",
        confidence=0.35,  # Above clamped floor of 0.3
    )

    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={},
        candidates=[candidate],
        immediate=True,
        personality_biases={"confidence_threshold": -0.9},  # Would be -0.2, clamped to 0.3
    )

    result = await strategy.decide(context, None)

    # Should accept at clamped threshold of 0.3
    assert result.path == DecisionPath.HEURISTIC
    assert result.metadata["threshold"] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_no_personality_bias_default(mock_llm):
    """F-24: Empty personality_biases preserves original behavior."""
    config = HeuristicFirstConfig(confidence_threshold=0.7)
    strategy = HeuristicFirstStrategy(config)

    candidate = HeuristicCandidate(
        heuristic_id="h1",
        condition_text="condition1",
        suggested_action="action1",
        confidence=0.8,
    )

    context = DecisionContext(
        event_id="e1",
        event_text="event1",
        event_source="src1",
        salience={"threat": 0.1},
        candidates=[candidate],
        immediate=True,
        # personality_biases defaults to empty dict
    )

    result = await strategy.decide(context, mock_llm)

    assert result.path == DecisionPath.HEURISTIC
    assert result.metadata["threshold"] == pytest.approx(0.7)
    mock_llm.generate.assert_not_called()
