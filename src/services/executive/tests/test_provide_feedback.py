import pytest
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from gladys_executive.server import (
    ExecutiveServicer,
    DecisionContext,
    HeuristicCandidate,
    Heuristic,
    ReasoningTrace,
    HEURISTIC_REINFORCE_THRESHOLD
)
from gladys_orchestrator.generated import executive_pb2

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    llm.model_name = "test-model"
    return llm

@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.query_matching_heuristics = AsyncMock()
    memory.update_heuristic_confidence = AsyncMock()
    memory.store_heuristic = AsyncMock()
    memory._available = True
    return memory

@pytest.fixture
def servicer(mock_llm, mock_memory):
    # Mock the strategy to return a trace
    strategy = MagicMock()
    strategy.get_trace.return_value = ReasoningTrace(
        event_id="e1",
        response_id="r1",
        context="test situation",
        response="test response",
        timestamp=0.0,
        event_source="test-src"
    )
    strategy.delete_trace = MagicMock()
    
    return ExecutiveServicer(
        llm_provider=mock_llm,
        memory_client=mock_memory,
        decision_strategy=strategy
    )

async def call_provide_feedback(servicer, request):
    mock_context = MagicMock()
    mock_context.invocation_metadata.return_value = []
    return await servicer.ProvideFeedback(request, mock_context)

# 12 words condition
GOOD_CONDITION = "When a player needs healing items and has some in their inventory"
GOOD_ACTION = {"type": "suggest", "message": "Use healing items from your inventory to restore health quickly"}

@pytest.mark.asyncio
async def test_provide_feedback_reinforces_similar_heuristic(servicer, mock_llm, mock_memory):
    # Mock pattern extraction
    mock_llm.generate.return_value = json.dumps({"condition": GOOD_CONDITION, "action": GOOD_ACTION})
    
    # Mock similarity match (0.82 >= 0.75)
    mock_memory.query_matching_heuristics.return_value = [("h-existing", 0.82)]
    mock_memory.update_heuristic_confidence.return_value = (True, "", 0.3, 0.4)
    
    request = executive_pb2.ProvideFeedbackRequest(
        response_id="r1",
        event_id="e1",
        positive=True
    )
    
    response = await call_provide_feedback(servicer, request)
    
    assert response.accepted is True
    assert response.created_heuristic_id == ""
    
    # Verify reinforcement
    mock_memory.update_heuristic_confidence.assert_called_with(
        heuristic_id="h-existing",
        positive=True
    )
    # Verify no new heuristic created
    mock_memory.store_heuristic.assert_not_called()
    # Verify trace deleted
    servicer._strategy.delete_trace.assert_called_with("r1")

@pytest.mark.asyncio
async def test_provide_feedback_creates_new_when_no_similar(servicer, mock_llm, mock_memory):
    # Mock pattern extraction
    mock_llm.generate.return_value = json.dumps({"condition": GOOD_CONDITION, "action": GOOD_ACTION})
    
    # Mock no similarity match
    mock_memory.query_matching_heuristics.return_value = []
    mock_memory.store_heuristic.return_value = (True, "h-new")
    
    request = executive_pb2.ProvideFeedbackRequest(
        response_id="r1",
        event_id="e1",
        positive=True
    )
    
    response = await call_provide_feedback(servicer, request)
    
    assert response.accepted is True
    assert response.created_heuristic_id != ""
    
    # Verify new heuristic stored
    assert mock_memory.store_heuristic.called
    # Verify trace deleted
    servicer._strategy.delete_trace.assert_called_with("r1")

@pytest.mark.asyncio
async def test_provide_feedback_creates_new_when_low_similarity(servicer, mock_llm, mock_memory):
    # Mock pattern extraction
    mock_llm.generate.return_value = json.dumps({"condition": GOOD_CONDITION, "action": GOOD_ACTION})
    
    # Mock low similarity match (0.5 < 0.75)
    mock_memory.query_matching_heuristics.return_value = [("h-far", 0.5)]
    mock_memory.store_heuristic.return_value = (True, "h-new")
    
    request = executive_pb2.ProvideFeedbackRequest(
        response_id="r1",
        event_id="e1",
        positive=True
    )
    
    response = await call_provide_feedback(servicer, request)
    
    assert response.accepted is True
    assert response.created_heuristic_id != ""
    
    # Verify new heuristic stored
    assert mock_memory.store_heuristic.called

@pytest.mark.asyncio
async def test_provide_feedback_dedup_threshold_boundary(servicer, mock_llm, mock_memory):
    # Mock pattern extraction
    mock_llm.generate.return_value = json.dumps({"condition": GOOD_CONDITION, "action": GOOD_ACTION})
    
    # Case 1: Just below threshold (0.749)
    mock_memory.query_matching_heuristics.return_value = [("h-existing", 0.749)]
    mock_memory.store_heuristic.return_value = (True, "h-new")
    
    request = executive_pb2.ProvideFeedbackRequest(
        response_id="r1",
        event_id="e1",
        positive=True
    )
    
    response = await call_provide_feedback(servicer, request)
    assert response.created_heuristic_id != ""
    assert mock_memory.store_heuristic.called
    
    # Reset mocks
    mock_memory.store_heuristic.reset_mock()
    mock_memory.update_heuristic_confidence.reset_mock()
    
    # Case 2: Exactly at threshold (0.75)
    mock_memory.query_matching_heuristics.return_value = [("h-existing", 0.75)]
    mock_memory.update_heuristic_confidence.return_value = (True, "", 0.3, 0.4)
    
    response = await call_provide_feedback(servicer, request)
    assert response.created_heuristic_id == ""
    mock_memory.update_heuristic_confidence.assert_called_with(
        heuristic_id="h-existing",
        positive=True
    )
    mock_memory.store_heuristic.assert_not_called()
