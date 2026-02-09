"""Tests for bootstrapping candidate plumbing in orchestrator."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest

from gladys_orchestrator.clients.executive_client import ExecutiveClient
from gladys_orchestrator.clients.memory_client import MemoryStorageClient
from gladys_orchestrator.config import OrchestratorConfig
from gladys_orchestrator.event_queue import EventQueue
from gladys_orchestrator.generated import common_pb2
from gladys_orchestrator.generated import executive_pb2
from gladys_orchestrator.generated import memory_pb2
from gladys_orchestrator.router import EventRouter


class FakeRpcError(grpc.RpcError):
    """Minimal RpcError for failure-path testing."""


@dataclass
class MockEvent:
    """Minimal event object used by router tests."""

    id: str
    source: str = "game-sensor"
    raw_text: str = "player health low"
    salience: object | None = None


class TestBootstrappingCandidates:
    """Candidate delivery plumbing tests."""

    def test_proto_candidates_field_exists(self):
        """Proto includes repeated candidates field on ProcessEventRequest."""
        field = executive_pb2.ProcessEventRequest.DESCRIPTOR.fields_by_name["candidates"]
        assert field.number == 4
        assert field.label == field.LABEL_REPEATED

    def test_config_max_evaluation_candidates_default(self):
        """OrchestratorConfig.max_evaluation_candidates defaults to 5."""
        config = OrchestratorConfig()
        assert config.max_evaluation_candidates == 5

    @pytest.mark.asyncio
    async def test_memory_client_query_matching_heuristics(self):
        """Memory client returns normalized dicts from QueryMatchingHeuristics."""
        client = MemoryStorageClient("localhost:50051")
        stub = AsyncMock()
        stub.QueryMatchingHeuristics = AsyncMock(return_value=memory_pb2.QueryHeuristicsResponse(
            matches=[
                memory_pb2.HeuristicMatch(
                    heuristic=memory_pb2.Heuristic(
                        id="heur-1",
                        condition_text="low health in combat",
                        effects_json='{"message":"heal now"}',
                        confidence=0.55,
                    ),
                    similarity=0.91,
                )
            ]
        ))
        client._stub = stub

        matches = await client.query_matching_heuristics(
            event_text="health dropped in fight",
            min_confidence=0.0,
            limit=5,
            source_filter="game-sensor",
        )

        assert matches == [{
            "heuristic_id": "heur-1",
            "condition_text": "low health in combat",
            "effects_json": '{"message":"heal now"}',
            "confidence": pytest.approx(0.55),
            "similarity": pytest.approx(0.91),
        }]
        request = stub.QueryMatchingHeuristics.call_args.args[0]
        assert request.event_text == "health dropped in fight"
        assert request.min_confidence == 0.0
        assert request.limit == 5
        assert request.source_filter == "game-sensor"

    @pytest.mark.asyncio
    async def test_memory_client_query_matching_heuristics_failure(self):
        """Memory client returns [] on RPC failure."""
        client = MemoryStorageClient("localhost:50051")
        stub = AsyncMock()
        stub.QueryMatchingHeuristics = AsyncMock(side_effect=FakeRpcError("boom"))
        client._stub = stub

        matches = await client.query_matching_heuristics("health low")
        assert matches == []

    @pytest.mark.asyncio
    async def test_memory_client_query_matching_heuristics_not_connected(self):
        """Memory client returns [] if not connected."""
        client = MemoryStorageClient("localhost:50051")
        matches = await client.query_matching_heuristics("health low")
        assert matches == []

    @pytest.mark.asyncio
    async def test_router_populates_candidates(self):
        """Router adds below-threshold candidates and excludes best match."""
        config = OrchestratorConfig(
            max_evaluation_candidates=5,
            heuristic_confidence_threshold=0.7,
        )
        salience_client = AsyncMock()
        salience_client.evaluate_salience = AsyncMock(return_value={
            "novelty": 0.8,
            "_matched_heuristic": "heur-best",
        })
        memory_client = AsyncMock()
        memory_client.get_heuristic = AsyncMock(return_value={
            "confidence": 0.42,
            "effects_json": '{"message":"best response"}',
            "condition_text": "best condition",
        })
        memory_client.query_matching_heuristics = AsyncMock(return_value=[
            {
                "heuristic_id": "heur-best",
                "condition_text": "best condition",
                "effects_json": '{"message":"best response"}',
                "confidence": 0.42,
                "similarity": 0.99,
            },
            {
                "heuristic_id": "heur-1",
                "condition_text": "condition 1",
                "effects_json": '{"text":"candidate one"}',
                "confidence": 0.50,
                "similarity": 0.80,
            },
            {
                "heuristic_id": "heur-2",
                "condition_text": "condition 2",
                "effects_json": '{"response":"candidate two"}',
                "confidence": 0.60,
                "similarity": 0.90,
            },
        ])
        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)

        result = await router.route_event(MockEvent(id="evt-1"))

        assert result["_suggestion"]["heuristic_id"] == "heur-best"
        assert [c["heuristic_id"] for c in result["_candidates"]] == ["heur-2", "heur-1"]
        assert [c["suggested_action"] for c in result["_candidates"]] == ["candidate two", "candidate one"]
        memory_client.query_matching_heuristics.assert_awaited_once_with(
            event_text="player health low",
            min_confidence=0.0,
            limit=6,
            source_filter="game-sensor",
        )

    @pytest.mark.asyncio
    async def test_router_limits_candidates_to_max(self):
        """Router truncates candidates to max_evaluation_candidates."""
        config = OrchestratorConfig(max_evaluation_candidates=2, heuristic_confidence_threshold=0.7)
        salience_client = AsyncMock()
        salience_client.evaluate_salience = AsyncMock(return_value={"novelty": 0.8})
        memory_client = AsyncMock()
        memory_client.query_matching_heuristics = AsyncMock(return_value=[
            {
                "heuristic_id": "heur-1",
                "condition_text": "condition 1",
                "effects_json": '{"message":"a"}',
                "confidence": 0.10,
                "similarity": 0.40,
            },
            {
                "heuristic_id": "heur-2",
                "condition_text": "condition 2",
                "effects_json": '{"message":"b"}',
                "confidence": 0.20,
                "similarity": 0.90,
            },
            {
                "heuristic_id": "heur-3",
                "condition_text": "condition 3",
                "effects_json": '{"message":"c"}',
                "confidence": 0.30,
                "similarity": 0.80,
            },
        ])
        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)

        result = await router.route_event(MockEvent(id="evt-2"))

        assert len(result["_candidates"]) == 2
        assert [c["heuristic_id"] for c in result["_candidates"]] == ["heur-2", "heur-3"]

    @pytest.mark.asyncio
    async def test_router_no_candidates_without_memory_client(self):
        """Router does not query candidates when memory client is unavailable."""
        config = OrchestratorConfig(max_evaluation_candidates=5)
        salience_client = AsyncMock()
        salience_client.evaluate_salience = AsyncMock(return_value={"novelty": 0.8})
        router = EventRouter(config, salience_client=salience_client, memory_client=None)

        result = await router.route_event(MockEvent(id="evt-3"))

        assert result["_candidates"] == []

    @pytest.mark.asyncio
    async def test_router_no_candidates_without_raw_text(self):
        """Router skips candidate query when event has no raw_text."""
        config = OrchestratorConfig(max_evaluation_candidates=5)
        salience_client = AsyncMock()
        salience_client.evaluate_salience = AsyncMock(return_value={"novelty": 0.8})
        memory_client = AsyncMock()
        memory_client.query_matching_heuristics = AsyncMock(return_value=[{
            "heuristic_id": "heur-1",
            "condition_text": "condition",
            "effects_json": '{"message":"a"}',
            "confidence": 0.5,
            "similarity": 0.9,
        }])
        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)

        result = await router.route_event(MockEvent(id="evt-4", raw_text=""))

        assert result["_candidates"] == []
        memory_client.query_matching_heuristics.assert_not_called()

    @pytest.mark.asyncio
    async def test_router_filters_above_threshold_candidates(self):
        """Router excludes candidates at or above heuristic_confidence_threshold."""
        config = OrchestratorConfig(
            max_evaluation_candidates=5,
            heuristic_confidence_threshold=0.7,
        )
        salience_client = AsyncMock()
        salience_client.evaluate_salience = AsyncMock(return_value={"novelty": 0.8})
        memory_client = AsyncMock()
        memory_client.query_matching_heuristics = AsyncMock(return_value=[
            {
                "heuristic_id": "heur-high",
                "condition_text": "high",
                "effects_json": '{"message":"high"}',
                "confidence": 0.90,
                "similarity": 0.95,
            },
            {
                "heuristic_id": "heur-low",
                "condition_text": "low",
                "effects_json": '{"message":"low"}',
                "confidence": 0.60,
                "similarity": 0.85,
            },
        ])
        router = EventRouter(config, salience_client=salience_client, memory_client=memory_client)

        result = await router.route_event(MockEvent(id="evt-5"))

        assert [c["heuristic_id"] for c in result["_candidates"]] == ["heur-low"]

    @pytest.mark.asyncio
    async def test_executive_client_sends_candidates(self):
        """Executive client sends candidate protos in ProcessEventRequest."""
        client = ExecutiveClient("localhost:50053")
        stub = AsyncMock()
        stub.ProcessEvent = AsyncMock(return_value=executive_pb2.ProcessEventResponse(
            accepted=True,
            response_id="resp-1",
            response_text="ok",
        ))
        client._stub = stub

        event = common_pb2.Event(id="evt-10", source="game-sensor", raw_text="health low")
        suggestion = {
            "heuristic_id": "heur-best",
            "suggested_action": "best action",
            "confidence": 0.6,
            "condition_text": "best condition",
        }
        candidates = [
            {
                "heuristic_id": "heur-1",
                "suggested_action": "action one",
                "confidence": 0.5,
                "condition_text": "condition one",
            },
            {
                "heuristic_id": "heur-2",
                "suggested_action": "action two",
                "confidence": 0.4,
                "condition_text": "condition two",
            },
        ]

        response = await client.send_event_immediate(event, suggestion=suggestion, candidates=candidates)

        assert response["accepted"] is True
        request = stub.ProcessEvent.call_args.args[0]
        assert request.suggestion.heuristic_id == "heur-best"
        assert len(request.candidates) == 2
        assert request.candidates[0].heuristic_id == "heur-1"
        assert request.candidates[1].heuristic_id == "heur-2"

    @pytest.mark.asyncio
    async def test_event_queue_carries_candidates(self):
        """EventQueue passes candidates from enqueue() through process callback."""
        config = OrchestratorConfig(event_timeout_ms=5000, timeout_scan_interval_ms=100)
        process = AsyncMock(return_value={"response_text": "ok"})
        queue = EventQueue(
            config=config,
            process_callback=process,
            broadcast_callback=AsyncMock(),
            store_callback=AsyncMock(),
        )

        event = MagicMock()
        event.id = "evt-queue-1"
        event.source = "game-sensor"
        candidates = [{
            "heuristic_id": "heur-c1",
            "suggested_action": "candidate action",
            "confidence": 0.55,
            "condition_text": "candidate condition",
        }]

        await queue.start()
        queue.enqueue(
            event=event,
            salience=0.5,
            matched_heuristic_id="heur-best",
            suggested_action="best action",
            heuristic_confidence=0.6,
            condition_text="best condition",
            candidates=candidates,
        )
        await asyncio.sleep(0.25)
        await queue.stop()

        process.assert_called_once()
        call_args = process.call_args.args
        assert call_args[0] is event
        assert call_args[1]["heuristic_id"] == "heur-best"
        assert call_args[2] == candidates
