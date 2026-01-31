"""Executive stub server implementation.

This is a minimal Python implementation of the Executive service
for integration testing. The real Executive will be in C#/.NET.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from concurrent import futures
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
from typing import Any

import aiohttp

# Add orchestrator and memory to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "memory" / "python"))

import grpc
from grpc_reflection.v1alpha import reflection

from gladys_orchestrator.generated import executive_pb2
from gladys_orchestrator.generated import executive_pb2_grpc
from gladys_orchestrator.generated import common_pb2
from gladys_orchestrator.generated import types_pb2

# Memory proto imports (for StoreHeuristic RPC)
try:
    from gladys_orchestrator.generated import memory_pb2
    from gladys_orchestrator.generated import memory_pb2_grpc
    MEMORY_PROTO_AVAILABLE = True
except ImportError:
    try:
        from gladys_memory.generated import memory_pb2
        from gladys_memory.generated import memory_pb2_grpc
        MEMORY_PROTO_AVAILABLE = True
    except ImportError:
        MEMORY_PROTO_AVAILABLE = False
        memory_pb2 = None
        memory_pb2_grpc = None

logger = logging.getLogger(__name__)


class OllamaClient:
    """Simple async client for Ollama's HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma:2b"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._available: bool | None = None

    async def check_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    self._available = resp.status == 200
                    return self._available
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            self._available = False
            return False

    async def generate(self, prompt: str, system: str | None = None, format: str | None = None) -> str | None:
        """Generate a response from the LLM."""
        if self._available is False:
            return None

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
                    else:
                        logger.warning(f"Ollama returned status {resp.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.warning(f"Ollama request failed: {e}")
            return None


class MemoryClient:
    """Async gRPC client for Memory service."""

    def __init__(self, address: str = "localhost:50051"):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub = None
        self._available: bool | None = None

    async def connect(self) -> bool:
        """Connect to the Memory service."""
        if not MEMORY_PROTO_AVAILABLE:
            logger.warning("Memory proto stubs not available")
            self._available = False
            return False

        try:
            self._channel = grpc.aio.insecure_channel(self.address)
            await asyncio.wait_for(self._channel.channel_ready(), timeout=5.0)
            self._stub = memory_pb2_grpc.MemoryStorageStub(self._channel)
            self._available = True
            logger.info(f"Connected to Memory service at {self.address}")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Memory service not available at {self.address} (timeout)")
            self._available = False
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to Memory service: {e}")
            self._available = False
            return False

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def store_heuristic(self, heuristic: "Heuristic") -> tuple[bool, str]:
        """Store a heuristic via the Memory service."""
        if not self._available or not self._stub:
            return False, "Memory service not available"

        try:
            effects_json_str = json.dumps(heuristic.effects_json) if heuristic.effects_json else "{}"
            proto_heuristic = memory_pb2.Heuristic(
                id=heuristic.id,
                name=heuristic.name,
                condition_text=heuristic.condition_text,
                effects_json=effects_json_str,
                confidence=heuristic.confidence,
                origin=heuristic.origin,
                origin_id=heuristic.origin_id,
                created_at_ms=int(heuristic.created_at * 1000),
            )
            request = memory_pb2.StoreHeuristicRequest(
                heuristic=proto_heuristic,
                generate_embedding=True,
            )
            response = await self._stub.StoreHeuristic(request)
            if response.success:
                logger.info(f"Stored heuristic in Memory: id={response.heuristic_id}")
                return True, response.heuristic_id
            else:
                return False, response.error
        except grpc.aio.AioRpcError as e:
            logger.warning(f"Memory StoreHeuristic RPC error: {e.code()} - {e.details()}")
            return False, str(e.details())
        except Exception as e:
            logger.warning(f"Memory StoreHeuristic failed: {e}")
            return False, str(e)

    async def update_heuristic_confidence(
        self,
        heuristic_id: str,
        positive: bool,
        learning_rate: float | None = None,
    ) -> tuple[bool, str, float, float]:
        """Update heuristic confidence based on feedback."""
        if not self._available or not self._stub:
            return False, "Memory service not available", 0.0, 0.0

        try:
            request = memory_pb2.UpdateHeuristicConfidenceRequest(
                heuristic_id=heuristic_id,
                positive=positive,
            )
            if learning_rate is not None:
                request.learning_rate = learning_rate
            response = await self._stub.UpdateHeuristicConfidence(request)
            if response.success:
                return True, "", response.old_confidence, response.new_confidence
            else:
                return False, response.error, 0.0, 0.0
        except grpc.aio.AioRpcError as e:
            return False, str(e.details()), 0.0, 0.0
        except Exception as e:
            return False, str(e), 0.0, 0.0


def format_event_for_llm(event: Any) -> str:
    """Format a single event for LLM context."""
    salience_str = ""
    if event.salience:
        parts = []
        if event.salience.threat > 0.1:
            parts.append(f"threat={event.salience.threat:.2f}")
        if event.salience.opportunity > 0.1:
            parts.append(f"opportunity={event.salience.opportunity:.2f}")
        if event.salience.novelty > 0.1:
            parts.append(f"novelty={event.salience.novelty:.2f}")
        if parts:
            salience_str = f" [{', '.join(parts)}]"
    return f"[{event.source}]{salience_str}: {event.raw_text}"


EXECUTIVE_SYSTEM_PROMPT = """You are GLADyS, a helpful AI assistant observing events in a user's environment.

When given events, briefly acknowledge what happened and suggest any relevant actions or responses.
Keep responses concise (1-2 sentences). Focus on what's most important or actionable.

If there's a high-threat event, prioritize addressing it.
If events are routine, a brief acknowledgment is sufficient."""


PATTERN_EXTRACTION_PROMPT = """You just helped with this situation:

Context: {context}
Your response: {response}
User feedback: positive

Extract a generalizable heuristic that can be applied to similar situations in the future.
- condition: A general description of when this pattern applies (avoid specific names/numbers)
- action: What to do when the condition matches

Be general enough to match similar situations, specific enough to be useful.
Output ONLY valid JSON with no other text: {{"condition": "...", "action": {{"type": "...", "message": "..."}}}}"""


PREDICTION_PROMPT = """Given this situation and response:
Situation: {context}
Response: {response}

Predict the probability this action will succeed (0.0-1.0) and your confidence in that prediction (0.0-1.0).
Output ONLY valid JSON with no other text: {{"success": 0.X, "confidence": 0.Y}}"""


@dataclass
class ReasoningTrace:
    """Stores context for pattern extraction when feedback is received."""
    event_id: str
    response_id: str
    context: str
    response: str
    timestamp: float
    matched_heuristic_id: str | None = None
    predicted_success: float = 0.0
    prediction_confidence: float = 0.0

    def age_seconds(self) -> float:
        return time.time() - self.timestamp


TRACE_RETENTION_SECONDS = 300


@dataclass
class Heuristic:
    """A learned heuristic (CBR case)."""
    id: str
    name: str
    condition_text: str
    effects_json: dict
    confidence: float
    origin: str
    origin_id: str
    created_at: float


class HeuristicStore:
    """Simple file-based heuristic storage for PoC testing."""

    def __init__(self, path: str | Path = "heuristics.json"):
        self.path = Path(path)
        self.heuristics: dict[str, Heuristic] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for h_data in data.get("heuristics", []):
                        h = Heuristic(**h_data)
                        self.heuristics[h.id] = h
                logger.info(f"Loaded {len(self.heuristics)} heuristics from {self.path}")
            except Exception as e:
                logger.warning(f"Failed to load heuristics from {self.path}: {e}")

    def _save(self) -> None:
        try:
            data = {"heuristics": [asdict(h) for h in self.heuristics.values()]}
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save heuristics to {self.path}: {e}")

    def add(self, heuristic: Heuristic) -> None:
        self.heuristics[heuristic.id] = heuristic
        self._save()
        logger.info(f"Stored heuristic: id={heuristic.id}")

    def get(self, heuristic_id: str) -> Heuristic | None:
        return self.heuristics.get(heuristic_id)

    def list_all(self) -> list[Heuristic]:
        return list(self.heuristics.values())


class ExecutiveServicer(executive_pb2_grpc.ExecutiveServiceServicer):
    """Stub implementation of ExecutiveService for testing."""

    def __init__(
        self,
        ollama_client: OllamaClient | None = None,
        memory_client: MemoryClient | None = None,
        heuristic_store: HeuristicStore | None = None,
    ):
        self.events_received = 0
        self.moments_received = 0
        self.heuristics_created = 0
        self.ollama = ollama_client
        self.memory_client = memory_client
        self.heuristic_store = heuristic_store or HeuristicStore()
        self.reasoning_traces: dict[str, ReasoningTrace] = {}
        self._started_at = time.time()

    def _cleanup_old_traces(self) -> int:
        old_ids = [
            rid for rid, trace in self.reasoning_traces.items()
            if trace.age_seconds() > TRACE_RETENTION_SECONDS
        ]
        for rid in old_ids:
            del self.reasoning_traces[rid]
        return len(old_ids)

    def _store_trace(
        self,
        event_id: str,
        context: str,
        response: str,
        matched_heuristic_id: str | None = None,
        predicted_success: float = 0.0,
        prediction_confidence: float = 0.0,
    ) -> str:
        response_id = str(uuid.uuid4())
        self.reasoning_traces[response_id] = ReasoningTrace(
            event_id=event_id,
            response_id=response_id,
            context=context,
            response=response,
            timestamp=time.time(),
            matched_heuristic_id=matched_heuristic_id,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
        )
        if len(self.reasoning_traces) > 100:
            self._cleanup_old_traces()
        return response_id

    async def ProcessEvent(
        self,
        request: executive_pb2.ProcessEventRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProcessEventResponse:
        """Process a high-salience event."""
        self.events_received += 1
        event = request.event

        immediate_str = " (IMMEDIATE)" if request.immediate else ""
        threat = event.salience.threat if event.salience else 0.0
        logger.info(
            f"EVENT{immediate_str}: id={event.id}, source={event.source}, "
            f"threat={threat:.2f}, text={event.raw_text[:50] if event.raw_text else ''}..."
        )

        response_id = ""
        response_text = ""
        predicted_success = 0.0
        prediction_confidence = 0.0

        if self.ollama and request.immediate:
            event_context = format_event_for_llm(event)

            # Build prompt, including suggestion if present (Scenario 2)
            prompt = f"URGENT event: {event_context}\n\n"
            if request.suggestion and request.suggestion.heuristic_id:
                # Include low-confidence heuristic suggestion for LLM to consider
                suggestion = request.suggestion
                prompt += f"""A learned pattern matched this situation:
- Pattern: "{suggestion.condition_text}"
- Suggested action: "{suggestion.suggested_action}"
- Confidence: {suggestion.confidence:.0%}

Consider this suggestion in your response.

"""
                logger.info(
                    f"Including suggestion in prompt: heuristic={suggestion.heuristic_id}, "
                    f"confidence={suggestion.confidence:.2f}"
                )
            prompt += "How should I respond?"
            llm_response = await self.ollama.generate(prompt, system=EXECUTIVE_SYSTEM_PROMPT)
            if llm_response:
                response_text = llm_response.strip()
                logger.info(f"GLADyS: {response_text}")

                prediction_json = await self.ollama.generate(
                    PREDICTION_PROMPT.format(context=event_context, response=response_text),
                    format="json",
                )
                if prediction_json:
                    try:
                        clean_json = prediction_json.strip()
                        if clean_json.startswith("```"):
                            lines = clean_json.split("\n")
                            clean_json = "\n".join(
                                line for line in lines if not line.startswith("```")
                            ).strip()
                        pred_data = json.loads(clean_json)
                        predicted_success = float(pred_data.get("success", 0.5))
                        prediction_confidence = float(pred_data.get("confidence", 0.5))
                    except Exception:
                        predicted_success = 0.5
                        prediction_confidence = 0.5

                matched_heuristic = getattr(event, "matched_heuristic_id", "") or ""
                response_id = self._store_trace(
                    event_id=event.id,
                    context=event_context,
                    response=response_text,
                    matched_heuristic_id=matched_heuristic if matched_heuristic else None,
                    predicted_success=predicted_success,
                    prediction_confidence=prediction_confidence,
                )

        return executive_pb2.ProcessEventResponse(
            accepted=True,
            response_id=response_id,
            response_text=response_text,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
        )

    async def ProvideFeedback(
        self,
        request: executive_pb2.ProvideFeedbackRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProvideFeedbackResponse:
        """Handle feedback on a previous LLM response."""
        logger.info(
            f"FEEDBACK: response_id={request.response_id}, "
            f"event_id={request.event_id}, positive={request.positive}"
        )

        if not request.positive:
            trace = self.reasoning_traces.get(request.response_id)
            if not trace:
                return executive_pb2.ProvideFeedbackResponse(
                    accepted=True,
                    error_message="Reasoning trace not found or expired",
                )
            if trace.matched_heuristic_id and self.memory_client:
                success, error, old_conf, new_conf = await self.memory_client.update_heuristic_confidence(
                    heuristic_id=trace.matched_heuristic_id,
                    positive=False,
                )
                if success:
                    logger.info(
                        f"TD_LEARNING: Negative feedback decreased confidence: "
                        f"{old_conf:.3f} -> {new_conf:.3f}"
                    )
            return executive_pb2.ProvideFeedbackResponse(accepted=True)

        trace = self.reasoning_traces.get(request.response_id)
        if not trace:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="Reasoning trace not found or expired",
            )

        if not self.ollama:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="LLM not available for pattern extraction",
            )

        extraction_prompt = PATTERN_EXTRACTION_PROMPT.format(
            context=trace.context,
            response=trace.response,
        )
        pattern_json = await self.ollama.generate(extraction_prompt, format="json")
        if not pattern_json:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="Pattern extraction failed",
            )

        try:
            pattern_text = pattern_json.strip()
            if pattern_text.startswith("```"):
                lines = pattern_text.split("\n")
                pattern_text = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()
            pattern = json.loads(pattern_text)
            condition = pattern.get("condition", "")
            action = pattern.get("action", {})
            if not condition:
                raise ValueError("Missing 'condition'")
            logger.info(f"Extracted pattern: condition='{condition}'")
        except (json.JSONDecodeError, ValueError) as e:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message=f"Pattern parsing failed: {e}",
            )

        if trace.matched_heuristic_id and self.memory_client:
            await self.memory_client.update_heuristic_confidence(
                heuristic_id=trace.matched_heuristic_id,
                positive=True,
            )

        heuristic_id = str(uuid.uuid4())
        heuristic = Heuristic(
            id=heuristic_id,
            name=f"Learned: {condition[:50]}..." if len(condition) > 50 else f"Learned: {condition}",
            condition_text=condition,
            effects_json=action,
            confidence=0.3,
            origin="learned",
            origin_id=trace.response_id,
            created_at=time.time(),
        )

        stored_via_memory = False
        if self.memory_client:
            success, result = await self.memory_client.store_heuristic(heuristic)
            if success:
                stored_via_memory = True
        if not stored_via_memory:
            self.heuristic_store.add(heuristic)

        self.heuristics_created += 1
        del self.reasoning_traces[request.response_id]

        return executive_pb2.ProvideFeedbackResponse(
            accepted=True,
            created_heuristic_id=heuristic_id,
        )

    async def GetHealth(
        self,
        request: types_pb2.GetHealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> types_pb2.GetHealthResponse:
        """Return basic health status."""
        return types_pb2.GetHealthResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            message="",
        )

    async def GetHealthDetails(
        self,
        request: types_pb2.GetHealthDetailsRequest,
        context: grpc.aio.ServicerContext,
    ) -> types_pb2.GetHealthDetailsResponse:
        """Return detailed health information."""
        uptime = int(time.time() - self._started_at)
        details = {
            "ollama_connected": str(self.ollama is not None).lower(),
            "memory_connected": str(self.memory_client is not None and self.memory_client._available).lower(),
            "events_received": str(self.events_received),
            "moments_received": str(self.moments_received),
            "heuristics_created": str(self.heuristics_created),
            "active_traces": str(len(self.reasoning_traces)),
        }
        return types_pb2.GetHealthDetailsResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            uptime_seconds=uptime,
            details=details,
        )


async def serve(
    port: int = 50053,
    ollama_url: str | None = None,
    ollama_model: str = "gemma:2b",
    memory_address: str | None = None,
    heuristic_store_path: str = "heuristics.json",
) -> None:
    """Start the Executive stub server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))

    ollama_client = None
    if ollama_url:
        ollama_client = OllamaClient(base_url=ollama_url, model=ollama_model)
        if await ollama_client.check_available():
            logger.info(f"Connected to Ollama at {ollama_url} (model: {ollama_model})")
        else:
            logger.warning(f"Ollama not available at {ollama_url}")
            ollama_client = None

    memory_client = None
    if memory_address:
        memory_client = MemoryClient(address=memory_address)
        if await memory_client.connect():
            logger.info(f"Connected to Memory service at {memory_address}")
        else:
            memory_client = None

    heuristic_store = HeuristicStore(heuristic_store_path)

    servicer = ExecutiveServicer(
        ollama_client=ollama_client,
        memory_client=memory_client,
        heuristic_store=heuristic_store,
    )
    executive_pb2_grpc.add_ExecutiveServiceServicer_to_server(servicer, server)

    SERVICE_NAMES = (
        executive_pb2.DESCRIPTOR.services_by_name["ExecutiveService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    address = f"0.0.0.0:{port}"
    server.add_insecure_port(address)

    logger.info(f"Executive stub server started on {address}")
    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        if memory_client:
            await memory_client.close()
        await server.stop(grace=5)
