"""Executive stub server implementation.

This is a minimal Python implementation of the Executive service
for integration testing. The real Executive will be in C#/.NET.
"""

import asyncio
import json
import os
import time
import uuid
from concurrent import futures
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
from typing import Any

import aiohttp

from gladys_common import get_logger, bind_trace_id, get_or_create_trace_id

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

logger = get_logger(__name__)


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
            logger.debug("Ollama not available", error=str(e))
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
            "keep_alive": "30m",
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
                        logger.warning("Ollama returned error status", status=resp.status)
                        return None
        except asyncio.TimeoutError:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.warning("Ollama request failed", error=str(e))
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
            logger.info("Connected to Memory service", address=self.address)
            return True
        except asyncio.TimeoutError:
            logger.warning("Memory service not available (timeout)", address=self.address)
            self._available = False
            return False
        except Exception as e:
            logger.warning("Failed to connect to Memory service", address=self.address, error=str(e))
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
                logger.info("Stored heuristic in Memory", heuristic_id=response.heuristic_id)
                return True, response.heuristic_id
            else:
                return False, response.error
        except grpc.aio.AioRpcError as e:
            logger.warning("Memory StoreHeuristic RPC error", code=str(e.code()), details=e.details())
            return False, str(e.details())
        except Exception as e:
            logger.warning("Memory StoreHeuristic failed", error=str(e))
            return False, str(e)

    async def query_matching_heuristics(
        self,
        event_text: str,
        min_confidence: float = 0.0,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Query heuristics by semantic similarity. Returns list of (heuristic_id, similarity)."""
        if not self._available or not self._stub:
            return []

        try:
            request = memory_pb2.QueryMatchingHeuristicsRequest(
                event_text=event_text,
                min_confidence=min_confidence,
                limit=limit,
            )
            response = await self._stub.QueryMatchingHeuristics(request)
            return [
                (match.heuristic.id, match.similarity)
                for match in response.matches
            ]
        except Exception as e:
            logger.warning("QueryMatchingHeuristics failed", error=str(e))
            return []

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

Extract a generalizable heuristic for similar future situations.

Rules:
- condition: Describe a SITUATION, not a person. Must be 10-50 words. No proper nouns or specific numbers.
- action.type: One of "suggest", "remind", "warn"
- action.message: The advice to give. Must be 10-50 words.

Good examples:
{{"condition": "When a player's health drops below a critical threshold during combat and healing items are available in inventory", "action": {{"type": "suggest", "message": "Use a healing item before continuing the fight to avoid being defeated and losing progress"}}}}
{{"condition": "When a puzzle cell has only one possible candidate remaining based on row column and box constraints", "action": {{"type": "suggest", "message": "Fill in the cell with the only remaining candidate since it is the sole valid option"}}}}

Bad examples (DO NOT generate these):
- Too vague: {{"condition": "When something happens", "action": {{"type": "suggest", "message": "Do the right thing"}}}}
- Too specific: {{"condition": "When John plays level 5 on Tuesday", "action": {{"type": "suggest", "message": "Press the blue button at coordinates 150 200"}}}}

Output valid JSON: {{"condition": "...", "action": {{"type": "...", "message": "..."}}}}"""


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
                logger.info("Loaded heuristics", count=len(self.heuristics), path=str(self.path))
            except Exception as e:
                logger.warning("Failed to load heuristics", path=str(self.path), error=str(e))

    def _save(self) -> None:
        try:
            data = {"heuristics": [asdict(h) for h in self.heuristics.values()]}
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save heuristics", path=str(self.path), error=str(e))

    def add(self, heuristic: Heuristic) -> None:
        self.heuristics[heuristic.id] = heuristic
        self._save()
        logger.info("Stored heuristic", heuristic_id=heuristic.id)

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

    @staticmethod
    def _setup_trace(context) -> str:
        """Extract or generate trace ID and bind to logging context."""
        metadata = dict(context.invocation_metadata())
        trace_id = get_or_create_trace_id(metadata)
        bind_trace_id(trace_id)
        return trace_id

    @staticmethod
    def _check_heuristic_quality(condition: str, action: dict) -> str | None:
        """Validate heuristic quality. Returns error message or None if valid."""
        word_count = len(condition.split())
        if word_count < 10:
            return f"Condition too short ({word_count} words, minimum 10)"
        if word_count > 50:
            return f"Condition too long ({word_count} words, maximum 50)"

        if not isinstance(action, dict):
            return "Action must be a JSON object"
        if "type" not in action:
            return "Action missing required field 'type'"
        if action.get("type") not in ("suggest", "remind", "warn"):
            return f"Action type must be suggest/remind/warn, got '{action.get('type')}'"
        if "message" not in action:
            return "Action missing required field 'message'"
        msg_words = len(action["message"].split())
        if msg_words < 10:
            return f"Action message too short ({msg_words} words, minimum 10)"
        if msg_words > 50:
            return f"Action message too long ({msg_words} words, maximum 50)"

        return None

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
        """Process an event, deciding between heuristic fast-path and LLM reasoning.

        §30 boundary change: Executive now decides heuristic-vs-LLM.
        If a high-confidence suggestion is attached, return the heuristic action
        directly without calling the LLM.
        """
        self._setup_trace(context)
        self.events_received += 1
        event = request.event

        logger.info(
            "ProcessEvent received",
            event_id=event.id,
            source=event.source,
            immediate=request.immediate,
            threat=round(event.salience.threat, 2) if event.salience else 0.0,
            text_preview=event.raw_text[:50] if event.raw_text else "",
        )

        # §30 fast-path: high-confidence heuristic → return action without LLM
        heuristic_threshold = float(os.environ.get("EXECUTIVE_HEURISTIC_THRESHOLD", "0.7"))
        if (request.suggestion
                and request.suggestion.heuristic_id
                and request.suggestion.confidence >= heuristic_threshold):
            suggestion = request.suggestion
            logger.info(
                "HEURISTIC_FASTPATH",
                event_id=event.id,
                heuristic_id=suggestion.heuristic_id,
                confidence=round(suggestion.confidence, 3),
                threshold=heuristic_threshold,
            )
            response_id = self._store_trace(
                event_id=event.id,
                context=event.raw_text or "",
                response=suggestion.suggested_action,
                matched_heuristic_id=suggestion.heuristic_id,
                predicted_success=suggestion.confidence,
                prediction_confidence=suggestion.confidence,
            )
            return executive_pb2.ProcessEventResponse(
                accepted=True,
                response_id=response_id,
                response_text=suggestion.suggested_action,
                predicted_success=suggestion.confidence,
                prediction_confidence=suggestion.confidence,
                prompt_text="",
                decision_path="heuristic",
                matched_heuristic_id=suggestion.heuristic_id,
            )

        response_id = ""
        response_text = ""
        predicted_success = 0.0
        prediction_confidence = 0.0
        prompt_text = ""
        decision_path = ""
        matched_heuristic_id_for_response = ""

        if self.ollama and request.immediate:
            logger.info("LLM_PATH", event_id=event.id)
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
                    "Including suggestion in prompt",
                    heuristic_id=suggestion.heuristic_id,
                    confidence=round(suggestion.confidence, 2),
                )
            prompt += "How should I respond?"
            prompt_text = prompt
            decision_path = "llm"
            if request.suggestion and request.suggestion.heuristic_id:
                matched_heuristic_id_for_response = request.suggestion.heuristic_id
            llm_response = await self.ollama.generate(prompt, system=EXECUTIVE_SYSTEM_PROMPT)
            if llm_response:
                response_text = llm_response.strip()
                logger.info("GLADyS response", response_text=response_text)

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

                matched_heuristic = request.suggestion.heuristic_id if request.HasField("suggestion") else ""
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
            prompt_text=prompt_text,
            decision_path=decision_path,
            matched_heuristic_id=matched_heuristic_id_for_response,
        )

    async def ProvideFeedback(
        self,
        request: executive_pb2.ProvideFeedbackRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProvideFeedbackResponse:
        """Handle feedback on a previous LLM response."""
        self._setup_trace(context)
        logger.info(
            "FEEDBACK received",
            response_id=request.response_id,
            event_id=request.event_id,
            positive=request.positive,
        )

        if not request.positive:
            trace = self.reasoning_traces.get(request.response_id)
            if not trace:
                return executive_pb2.ProvideFeedbackResponse(
                    accepted=False,
                    error_message="Reasoning trace not found or expired",
                )
            if trace.matched_heuristic_id and self.memory_client:
                success, error, old_conf, new_conf = await self.memory_client.update_heuristic_confidence(
                    heuristic_id=trace.matched_heuristic_id,
                    positive=False,
                )
                if success:
                    logger.info(
                        "TD_LEARNING: Negative feedback decreased confidence",
                        old_confidence=round(old_conf, 3),
                        new_confidence=round(new_conf, 3),
                    )
            return executive_pb2.ProvideFeedbackResponse(accepted=True)

        trace = self.reasoning_traces.get(request.response_id)
        if not trace:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=False,
                error_message="Reasoning trace not found or expired",
            )

        if not self.ollama:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=False,
                error_message="LLM not available for pattern extraction",
            )

        extraction_prompt = PATTERN_EXTRACTION_PROMPT.format(
            context=trace.context,
            response=trace.response,
        )
        pattern_json = await self.ollama.generate(extraction_prompt, format="json")
        if not pattern_json:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=False,
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
            logger.info("Extracted pattern", condition=condition)
        except (json.JSONDecodeError, ValueError) as e:
            return executive_pb2.ProvideFeedbackResponse(
                accepted=False,
                error_message=f"Pattern parsing failed: {e}",
            )

        # Quality gate: validate before storing
        gate_error = self._check_heuristic_quality(condition, action)
        if gate_error:
            logger.warning("QUALITY_GATE: Rejected heuristic", reason=gate_error)
            return executive_pb2.ProvideFeedbackResponse(
                accepted=False,
                error_message=f"Quality gate: {gate_error}",
            )

        # Dedup check: reject near-duplicates (similarity > 0.9)
        # Note: event_text param name is misleading — the RPC generates an embedding
        # and compares it against condition_embedding in the heuristics table (storage.py:378),
        # so passing condition text here correctly does condition-to-condition similarity.
        if self.memory_client:
            matches = await self.memory_client.query_matching_heuristics(
                event_text=condition, min_confidence=0.0, limit=1,
            )
            for heuristic_id, similarity in matches:
                if similarity > 0.9:
                    logger.warning(
                        "QUALITY_GATE: Near-duplicate detected",
                        similarity=round(similarity, 3),
                        existing_heuristic_id=heuristic_id,
                    )
                    return executive_pb2.ProvideFeedbackResponse(
                        accepted=False,
                        error_message=f"Near-duplicate of existing heuristic (similarity={similarity:.2f})",
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
            logger.info("Connected to Ollama", url=ollama_url, model=ollama_model)
        else:
            logger.warning("Ollama not available", url=ollama_url)
            ollama_client = None

    memory_client = None
    if memory_address:
        memory_client = MemoryClient(address=memory_address)
        if await memory_client.connect():
            logger.info("Connected to Memory service", address=memory_address)
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

    logger.info("Executive stub server started", address=address)
    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        if memory_client:
            await memory_client.close()
        await server.stop(grace=5)
