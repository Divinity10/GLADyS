import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gladys_executive.server import (
    DecisionContext,
    DecisionPath,
    HeuristicCandidate,
    HeuristicFirstConfig,
    HeuristicFirstStrategy,
    LLMResponse,
    MemoryClient,
    SalienceGatewayClient,
    cosine_similarity,
)
from gladys_orchestrator.generated import memory_pb2


def make_embedding(values: list[float]) -> bytes:
    """Create deterministic 384-d float32 embedding bytes for tests."""
    padded = (values + [0.0] * 384)[:384]
    return struct.pack(f"{384}f", *padded)


def make_context(candidates: list[HeuristicCandidate] | None = None) -> DecisionContext:
    return DecisionContext(
        event_id="e1",
        event_text="Player health dropped during combat",
        event_source="game_sensor",
        salience={},
        candidates=candidates or [],
        immediate=True,
    )


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    llm.model_name = "test-model"
    return llm


def test_evaluation_prompt_includes_candidates():
    strategy = HeuristicFirstStrategy()
    c1 = HeuristicCandidate("h1", "Condition A", "Action A", 0.4)
    c2 = HeuristicCandidate("h2", "Condition B", "Action B", 0.5)
    context = make_context([c1, c2])

    with patch("gladys_executive.server.random.shuffle", side_effect=lambda items: items.reverse()):
        prompt = strategy._build_evaluation_prompt(context)

    assert "Here are some possible responses to this situation:" in prompt
    assert '1. Context: "Condition B"' in prompt
    assert '   Response: "Action B"' in prompt
    assert '2. Context: "Condition A"' in prompt
    assert '   Response: "Action A"' in prompt


def test_evaluation_prompt_no_metadata_leaks():
    strategy = HeuristicFirstStrategy()
    candidate = HeuristicCandidate("h1", "Low health during active combat", "Use a healing item now", 0.99)
    prompt = strategy._build_evaluation_prompt(make_context([candidate]))
    lower = prompt.lower()

    assert "confidence" not in lower
    assert "learned" not in lower
    assert "seeded" not in lower
    assert "skill_pack" not in lower
    assert "fire_count" not in lower
    assert "metadata" not in lower


def test_evaluation_prompt_generation_instruction():
    strategy = HeuristicFirstStrategy()
    candidate = HeuristicCandidate("h1", "Low health during active combat", "Use a healing item now", 0.5)
    prompt = strategy._build_evaluation_prompt(make_context([candidate]))

    assert "Generate your own response to this event" in prompt
    assert "judge" not in prompt.lower()


def test_prompt_no_candidates_no_context_section():
    strategy = HeuristicFirstStrategy()
    prompt = strategy._build_prompt(make_context([]))

    assert "possible responses" not in prompt
    assert "Previous responses to similar situations" not in prompt
    assert "How should I respond?" in prompt


@pytest.mark.asyncio
async def test_cosine_similarity_computation():
    llm_embedding = make_embedding([1.0, 0.0])
    candidate_embedding = make_embedding([0.8, 0.6])  # cosine=0.8 with llm_embedding
    memory = MagicMock()
    memory.generate_embedding = AsyncMock(side_effect=[llm_embedding, candidate_embedding])
    memory.update_heuristic_confidence_weighted = AsyncMock(return_value=(True, "", 0.3, 0.7))
    salience = MagicMock()
    salience.notify_heuristic_change = AsyncMock(return_value=True)

    strategy = HeuristicFirstStrategy(
        HeuristicFirstConfig(endorsement_similarity_threshold=0.75, endorsement_boost_weight=0.5),
        memory_client=memory,
        salience_client=salience,
    )
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.4)

    await strategy._process_llm_endorsements("llm response", [candidate])

    kwargs = memory.update_heuristic_confidence_weighted.await_args.kwargs
    assert kwargs["heuristic_id"] == "h1"
    assert kwargs["magnitude"] == pytest.approx(0.4, rel=1e-3)


@pytest.mark.asyncio
async def test_endorsement_updates_confidence():
    embedding = make_embedding([1.0, 0.0])
    memory = MagicMock()
    memory.generate_embedding = AsyncMock(side_effect=[embedding, embedding])
    memory.update_heuristic_confidence_weighted = AsyncMock(return_value=(True, "", 0.3, 0.8))
    salience = MagicMock()
    salience.notify_heuristic_change = AsyncMock(return_value=True)

    strategy = HeuristicFirstStrategy(
        HeuristicFirstConfig(endorsement_similarity_threshold=0.75, endorsement_boost_weight=0.5),
        memory_client=memory,
        salience_client=salience,
    )
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.2)

    await strategy._process_llm_endorsements("llm response", [candidate])

    kwargs = memory.update_heuristic_confidence_weighted.await_args.kwargs
    assert kwargs["positive"] is True
    assert kwargs["feedback_source"] == "llm_endorsement"
    assert kwargs["magnitude"] == pytest.approx(0.5, rel=1e-4)


@pytest.mark.asyncio
async def test_below_threshold_no_update():
    llm_embedding = make_embedding([1.0, 0.0])
    candidate_embedding = make_embedding([0.0, 1.0])  # cosine=0.0
    memory = MagicMock()
    memory.generate_embedding = AsyncMock(side_effect=[llm_embedding, candidate_embedding])
    memory.update_heuristic_confidence_weighted = AsyncMock()
    salience = MagicMock()
    salience.notify_heuristic_change = AsyncMock(return_value=True)

    strategy = HeuristicFirstStrategy(
        HeuristicFirstConfig(endorsement_similarity_threshold=0.75, endorsement_boost_weight=0.5),
        memory_client=memory,
        salience_client=salience,
    )
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.2)

    await strategy._process_llm_endorsements("llm response", [candidate])

    memory.update_heuristic_confidence_weighted.assert_not_called()
    salience.notify_heuristic_change.assert_not_called()


@pytest.mark.asyncio
async def test_cache_invalidation_after_endorsement():
    embedding = make_embedding([1.0, 0.0])
    memory = MagicMock()
    memory.generate_embedding = AsyncMock(side_effect=[embedding, embedding])
    memory.update_heuristic_confidence_weighted = AsyncMock(return_value=(True, "", 0.4, 0.6))
    salience = MagicMock()
    salience.notify_heuristic_change = AsyncMock(return_value=True)

    strategy = HeuristicFirstStrategy(
        memory_client=memory,
        salience_client=salience,
    )
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.2)

    await strategy._process_llm_endorsements("llm response", [candidate])

    salience.notify_heuristic_change.assert_awaited_once_with(heuristic_id="h1", change_type="updated")


@pytest.mark.asyncio
async def test_response_returned_before_comparison(mock_llm):
    memory = MagicMock()
    salience = MagicMock()
    strategy = HeuristicFirstStrategy(memory_client=memory, salience_client=salience)
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.2)
    context = make_context([candidate])

    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_endorsement(_response_text: str, _candidates: list[HeuristicCandidate]) -> None:
        started.set()
        await release.wait()

    strategy._process_llm_endorsements = AsyncMock(side_effect=delayed_endorsement)  # type: ignore[method-assign]

    mock_llm.generate.side_effect = [
        LLMResponse(text="llm output", model="test-model"),
        LLMResponse(text='{"success": 0.6, "confidence": 0.6}', model="test-model"),
    ]

    result = await asyncio.wait_for(strategy.decide(context, mock_llm), timeout=0.5)

    assert result.path == DecisionPath.LLM
    await asyncio.wait_for(started.wait(), timeout=0.5)
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    class BlockingLLM:
        def __init__(self):
            self.model_name = "test-model"
            self._release = asyncio.Event()
            self._active = 0
            self.max_active = 0

        async def generate(self, request):
            if request.format == "json":
                return LLMResponse(text='{"success": 0.5, "confidence": 0.5}', model="test-model")

            self._active += 1
            self.max_active = max(self.max_active, self._active)
            try:
                await self._release.wait()
                return LLMResponse(text="response", model="test-model")
            finally:
                self._active -= 1

        async def check_available(self) -> bool:
            return True

    llm = BlockingLLM()
    strategy = HeuristicFirstStrategy(HeuristicFirstConfig(max_concurrent_llm=2))

    contexts = [
        DecisionContext(
            event_id=f"e{i}",
            event_text=f"event-{i}",
            event_source="src",
            salience={},
            candidates=[],
            immediate=True,
        )
        for i in range(4)
    ]
    tasks = [asyncio.create_task(strategy.decide(context, llm)) for context in contexts]

    await asyncio.sleep(0.1)
    assert llm.max_active <= 2

    llm._release.set()
    await asyncio.gather(*tasks)


def test_cosine_similarity_known_vectors():
    a = make_embedding([1.0, 0.0])
    b = make_embedding([1.0, 0.0])
    c = make_embedding([0.0, 1.0])

    assert cosine_similarity(a, b) == pytest.approx(1.0)
    assert cosine_similarity(a, c) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector():
    zero = make_embedding([0.0, 0.0])
    a = make_embedding([1.0, 0.0])

    assert cosine_similarity(zero, a) == 0.0
    assert cosine_similarity(zero, zero) == 0.0


@pytest.mark.asyncio
async def test_memory_client_generate_embedding():
    expected = make_embedding([0.2, 0.3, 0.4])
    client = MemoryClient("localhost:50051")
    client._available = True
    client._stub = MagicMock()
    client._stub.GenerateEmbedding = AsyncMock(
        return_value=memory_pb2.GenerateEmbeddingResponse(embedding=expected, error="")
    )

    result = await client.generate_embedding("hello world")

    assert result == expected
    request = client._stub.GenerateEmbedding.await_args.args[0]
    assert request.text == "hello world"


@pytest.mark.asyncio
async def test_memory_client_weighted_confidence_update():
    client = MemoryClient("localhost:50051")
    client._available = True
    client._stub = MagicMock()
    client._stub.UpdateHeuristicConfidence = AsyncMock(
        return_value=memory_pb2.UpdateHeuristicConfidenceResponse(
            success=True,
            old_confidence=0.3,
            new_confidence=0.6,
        )
    )

    success, error, old_conf, new_conf = await client.update_heuristic_confidence_weighted(
        heuristic_id="h1",
        positive=True,
        magnitude=0.45,
        feedback_source="llm_endorsement",
    )

    assert success is True
    assert error == ""
    assert old_conf == pytest.approx(0.3)
    assert new_conf == pytest.approx(0.6)

    request = client._stub.UpdateHeuristicConfidence.await_args.args[0]
    assert request.heuristic_id == "h1"
    assert request.positive is True
    assert request.magnitude == pytest.approx(0.45)
    assert request.feedback_source == "llm_endorsement"


@pytest.mark.asyncio
async def test_salience_client_notify_change():
    client = SalienceGatewayClient("localhost:50051")
    client._available = True
    client._stub = MagicMock()
    client._stub.NotifyHeuristicChange = AsyncMock(
        return_value=memory_pb2.NotifyHeuristicChangeResponse(success=True)
    )

    result = await client.notify_heuristic_change("h1", "updated")

    assert result is True
    request = client._stub.NotifyHeuristicChange.await_args.args[0]
    assert request.heuristic_id == "h1"
    assert request.change_type == "updated"


@pytest.mark.asyncio
async def test_background_task_handles_errors_gracefully():
    candidate = HeuristicCandidate("h1", "c1", "a1", 0.4)

    # Case 1: embedding generation fails
    memory = MagicMock()
    memory.generate_embedding = AsyncMock(return_value=None)
    memory.update_heuristic_confidence_weighted = AsyncMock()
    salience = MagicMock()
    salience.notify_heuristic_change = AsyncMock(return_value=True)
    strategy = HeuristicFirstStrategy(memory_client=memory, salience_client=salience)

    with patch("gladys_executive.server.logger.warning") as warning_log:
        await strategy._process_llm_endorsements("llm response", [candidate])
        assert warning_log.called

    # Case 2: update RPC fails
    memory2 = MagicMock()
    emb = make_embedding([1.0, 0.0])
    memory2.generate_embedding = AsyncMock(side_effect=[emb, emb])
    memory2.update_heuristic_confidence_weighted = AsyncMock(side_effect=RuntimeError("rpc failure"))
    salience2 = MagicMock()
    salience2.notify_heuristic_change = AsyncMock(return_value=True)
    strategy2 = HeuristicFirstStrategy(memory_client=memory2, salience_client=salience2)

    with patch("gladys_executive.server.logger.warning") as warning_log:
        await strategy2._process_llm_endorsements("llm response", [candidate])
        assert warning_log.called
