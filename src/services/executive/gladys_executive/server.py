"""Executive stub server implementation.

This is a minimal Python implementation of the Executive service
for integration testing. The real Executive will be in C#/.NET.
"""

import asyncio
import json
import os
import random
import time
import uuid
from concurrent import futures
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
import sys
from typing import Any, Protocol, runtime_checkable

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


@dataclass
class LLMRequest:
    """Request to an LLM provider."""
    prompt: str
    system_prompt: str | None = None
    format: str | None = None  # "json" for structured output
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    text: str
    model: str
    tokens_used: int | None = None
    latency_ms: float | None = None
    raw_response: dict[str, Any] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Interface for LLM text generation."""

    async def generate(self, request: LLMRequest) -> LLMResponse | None:
        """Generate a response. Returns None if unavailable."""
        ...

    async def check_available(self) -> bool:
        """Check if the provider is reachable."""
        ...

    @property
    def model_name(self) -> str:
        """Return model identifier for logging."""
        ...


class DecisionPath(Enum):
    """Which path the decision took."""
    HEURISTIC = "heuristic"
    LLM = "llm"
    FALLBACK = "fallback"
    REJECTED = "rejected"


@dataclass
class HeuristicCandidate:
    """A heuristic candidate for LLM prompt inclusion (F-04).

    Deliberately minimal — only condition and action text.
    No confidence scores, fire counts, or similarity scores (avoids anchoring bias).
    """
    heuristic_id: str
    condition_text: str
    suggested_action: str
    confidence: float  # Used for heuristic-path threshold check, NOT shown to LLM


@dataclass
class DecisionContext:
    """Input to a decision strategy."""
    event_id: str
    event_text: str
    event_source: str
    salience: dict[str, float]
    candidates: list[HeuristicCandidate]  # Best match first, then additional candidates.
    immediate: bool
    goals: list[str] = field(default_factory=list)  # Active user goals (F-07). Injected into system prompt.
    personality_biases: dict[str, float] = field(default_factory=dict)  # F-24: threshold adjustments per-domain/user


@dataclass
class DecisionResult:
    """Output from a decision strategy."""
    path: DecisionPath
    response_text: str
    response_id: str
    matched_heuristic_id: str | None
    predicted_success: float
    prediction_confidence: float
    prompt_text: str
    metadata: dict[str, Any]  # Includes convergence info when detected


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


class DecisionStrategy(Protocol):
    """Interface for event decision logic."""

    async def decide(
        self,
        context: DecisionContext,
        llm: LLMProvider | None,
    ) -> DecisionResult:
        """Decide how to respond to an event."""
        ...

    def get_trace(self, response_id: str) -> ReasoningTrace | None:
        """Get reasoning trace for feedback handling."""
        ...

    def delete_trace(self, response_id: str) -> None:
        """Delete trace after use."""
        ...

    @property
    def trace_count(self) -> int:
        """Return number of active traces."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Return configuration for logging."""
        ...


EXECUTIVE_SYSTEM_PROMPT = """You are GLADyS, a helpful AI assistant observing events in a user's environment.

When given events, briefly acknowledge what happened and suggest any relevant actions or responses.
Keep responses concise (1-2 sentences). Focus on what's most important or actionable.

If there's a high-threat event, prioritize addressing it.
If events are routine, a brief acknowledgment is sufficient."""


PREDICTION_PROMPT = """Given this situation and response:
Situation: {context}
Response: {response}

Predict the probability this action will succeed (0.0-1.0) and your confidence in that prediction (0.0-1.0).
Output ONLY valid JSON with no other text: {{"success": 0.X, "confidence": 0.Y}}"""


@dataclass
class HeuristicFirstConfig:
    confidence_threshold: float = 0.7
    max_candidates: int = 3          # Max candidates in LLM prompt (F-04 Q5)
    llm_confidence_ceiling: float = 0.8  # Cap LLM self-reported confidence (F-06)
    system_prompt: str = EXECUTIVE_SYSTEM_PROMPT
    prediction_prompt_template: str = PREDICTION_PROMPT


class HeuristicFirstStrategy:
    """Use heuristic if confident, else LLM.

    Decision flow:
    1. If best candidate confidence >= threshold → heuristic fast-path
    2. If LLM available and immediate → LLM path (remaining candidates shown as neutral context)
    3. Otherwise → rejected
    """

    def __init__(self, config: HeuristicFirstConfig | None = None):
        self._config = config or HeuristicFirstConfig()
        self._trace_store: dict[str, ReasoningTrace] = {}

    async def decide(self, context: DecisionContext, llm: LLMProvider | None) -> DecisionResult:
        # Apply personality bias to threshold (F-24)
        threshold = self._config.confidence_threshold + context.personality_biases.get("confidence_threshold", 0.0)
        threshold = max(0.3, min(0.95, threshold))  # Clamp to safe range

        # Path 1: High-confidence heuristic (best candidate above threshold)
        best = context.candidates[0] if context.candidates else None
        if best and best.confidence >= threshold:
            return self._heuristic_path(context, best, threshold)

        # Path 2: LLM reasoning (with remaining candidates as neutral context)
        if llm and context.immediate:
            return await self._llm_path(context, llm)

        # Path 3: Rejected
        return DecisionResult(
            path=DecisionPath.REJECTED,
            response_text="",
            response_id="",
            matched_heuristic_id=None,
            predicted_success=0.0,
            prediction_confidence=0.0,
            prompt_text="",
            metadata={"reason": "llm_unavailable" if not llm else "not_immediate"},
        )

    def _heuristic_path(self, context: DecisionContext, candidate: HeuristicCandidate, threshold: float) -> DecisionResult:
        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=candidate.suggested_action,
            matched_heuristic_id=candidate.heuristic_id,
            predicted_success=candidate.confidence,
            prediction_confidence=candidate.confidence,
        )
        return DecisionResult(
            path=DecisionPath.HEURISTIC,
            response_text=candidate.suggested_action,
            response_id=response_id,
            matched_heuristic_id=candidate.heuristic_id,
            predicted_success=candidate.confidence,
            prediction_confidence=candidate.confidence,
            prompt_text="",
            metadata={"threshold": threshold},
        )

    async def _llm_path(self, context: DecisionContext, llm: LLMProvider) -> DecisionResult:
        prompt = self._build_prompt(context)

        # Compose system prompt with goals (F-07)
        system_prompt = self._config.system_prompt
        if context.goals:
            goals_text = "\n".join(f"- {g}" for g in context.goals)
            system_prompt += f"\n\nCurrent user goals:\n{goals_text}"

        llm_response = await llm.generate(LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
        ))

        if not llm_response:
            return DecisionResult(
                path=DecisionPath.FALLBACK,
                response_text="",
                response_id="",
                matched_heuristic_id=None,
                predicted_success=0.0,
                prediction_confidence=0.0,
                prompt_text=prompt,
                metadata={"reason": "llm_no_response"},
            )

        response_text = llm_response.text.strip()
        predicted_success, prediction_confidence = await self._get_prediction(
            llm, context, response_text
        )

        # Cap LLM self-reported confidence (F-06)
        predicted_success = min(predicted_success, self._config.llm_confidence_ceiling)
        prediction_confidence = min(prediction_confidence, self._config.llm_confidence_ceiling)

        # Determine matched heuristic (best candidate if present)
        matched_id = context.candidates[0].heuristic_id if context.candidates else None

        response_id = self._store_trace(
            event_id=context.event_id,
            context_text=context.event_text,
            response=response_text,
            matched_heuristic_id=matched_id,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
        )

        metadata: dict[str, Any] = {"model": llm.model_name}

        return DecisionResult(
            path=DecisionPath.LLM,
            response_text=response_text,
            response_id=response_id,
            matched_heuristic_id=matched_id,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
            prompt_text=prompt,
            metadata=metadata,
        )

    def _build_prompt(self, context: DecisionContext) -> str:
        """Build LLM prompt with neutral candidate presentation (F-04)."""
        prompt = f"URGENT event: [{context.event_source}]: {context.event_text}\n\n"

        # Include candidates as neutral context (up to max_candidates)
        display_candidates = context.candidates[:self._config.max_candidates]
        if display_candidates:
            # Randomize order to avoid positional bias
            shuffled = list(display_candidates)
            random.shuffle(shuffled)

            prompt += "Previous responses to similar situations (for context — you may ignore these):\n"
            for i, c in enumerate(shuffled, 1):
                prompt += f"{i}. Situation: \"{c.condition_text}\" → Response: \"{c.suggested_action}\"\n"
            prompt += "\n"

        prompt += "How should I respond?"
        return prompt

    async def _get_prediction(self, llm: LLMProvider, context: DecisionContext, response_text: str) -> tuple[float, float]:
        prediction_prompt = self._config.prediction_prompt_template.format(
            context=context.event_text,
            response=response_text
        )

        if context.goals:
            goals_text = "\n".join(f"- {g}" for g in context.goals)
            prediction_prompt += f"\n\nSuccess should be evaluated against these goals:\n{goals_text}"

        prediction_response = await llm.generate(LLMRequest(
            prompt=prediction_prompt,
            format="json",
        ))

        if not prediction_response:
            return 0.5, 0.5

        try:
            clean_json = prediction_response.text.strip()
            if clean_json.startswith("```"):
                lines = clean_json.split("\n")
                clean_json = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()
            pred_data = json.loads(clean_json)
            predicted_success = float(pred_data.get("success", 0.5))
            prediction_confidence = float(pred_data.get("confidence", 0.5))
            return predicted_success, prediction_confidence
        except Exception:
            return 0.5, 0.5

    def _cleanup_old_traces(self) -> int:
        old_ids = [
            rid for rid, trace in self._trace_store.items()
            if trace.age_seconds() > TRACE_RETENTION_SECONDS
        ]
        for rid in old_ids:
            del self._trace_store[rid]
        return len(old_ids)

    def _store_trace(
        self,
        event_id: str,
        context_text: str,
        response: str,
        matched_heuristic_id: str | None = None,
        predicted_success: float = 0.0,
        prediction_confidence: float = 0.0,
    ) -> str:
        response_id = str(uuid.uuid4())
        self._trace_store[response_id] = ReasoningTrace(
            event_id=event_id,
            response_id=response_id,
            context=context_text,
            response=response,
            timestamp=time.time(),
            matched_heuristic_id=matched_heuristic_id,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
        )
        if len(self._trace_store) > 100:
            self._cleanup_old_traces()
        return response_id

    def get_trace(self, response_id: str) -> ReasoningTrace | None:
        return self._trace_store.get(response_id)

    def delete_trace(self, response_id: str) -> None:
        if response_id in self._trace_store:
            del self._trace_store[response_id]

    @property
    def trace_count(self) -> int:
        return len(self._trace_store)

    @property
    def config(self) -> dict[str, Any]:
        return {
            "strategy": "heuristic_first",
            "confidence_threshold": self._config.confidence_threshold,
            "max_candidates": self._config.max_candidates,
            "llm_confidence_ceiling": self._config.llm_confidence_ceiling,
        }


class OllamaProvider:
    """LLM provider wrapping Ollama's HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma:2b"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._available: bool | None = None

    async def check_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self._base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    self._available = resp.status == 200
                    return self._available
        except Exception as e:
            logger.debug("Ollama not available", error=str(e))
            self._available = False
            return False

    async def generate(
        self,
        request: LLMRequest | str,
        system: str | None = None,
        format: str | None = None,
    ) -> LLMResponse | str | None:
        """Generate a response. Supports both Protocol and legacy signatures."""
        if isinstance(request, str):
            # Legacy call: await generate(prompt, system=..., format=...)
            llm_request = LLMRequest(prompt=request, system_prompt=system, format=format)
            response = await self._generate_impl(llm_request)
            return response.text if response else None

        # Protocol call: await generate(LLMRequest(...))
        return await self._generate_impl(request)

    async def _generate_impl(self, request: LLMRequest) -> LLMResponse | None:
        """Internal implementation of generation."""
        if self._available is False:
            return None

        payload = {
            "model": self._model,
            "prompt": request.prompt,
            "stream": False,
            "keep_alive": "30m",
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.format:
            payload["format"] = request.format

        try:
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return LLMResponse(
                            text=data.get("response", ""),
                            model=self._model,
                            latency_ms=(time.time() - start) * 1000,
                            raw_response=data,
                        )
                    else:
                        logger.warning("Ollama returned error status", status=resp.status)
                        return None
        except asyncio.TimeoutError:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.warning("Ollama request failed", error=str(e))
            return None

    @property
    def model_name(self) -> str:
        """Return model identifier for logging."""
        return f"ollama/{self._model}"


def create_llm_provider(provider_type: str, **kwargs) -> LLMProvider | None:
    """Factory function for LLM providers."""
    if provider_type == "ollama":
        return OllamaProvider(
            base_url=kwargs.get("url", os.environ.get("OLLAMA_URL", "http://localhost:11434")),
            model=kwargs.get("model", os.environ.get("OLLAMA_MODEL", "gemma:2b")),
        )
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
        llm_provider: LLMProvider | None = None,
        memory_client: MemoryClient | None = None,
        heuristic_store: HeuristicStore | None = None,
        decision_strategy: DecisionStrategy | None = None,
    ):
        self.events_received = 0
        self.moments_received = 0
        self.heuristics_created = 0
        self.ollama = llm_provider  # Keep attribute name for backward compatibility
        self.memory_client = memory_client
        self.heuristic_store = heuristic_store or HeuristicStore()
        self._strategy = decision_strategy or HeuristicFirstStrategy()
        self._started_at = time.time()

    @staticmethod
    def _setup_trace(context) -> str:
        """Extract or generate trace ID and bind to logging context."""
        metadata = dict(context.invocation_metadata())
        trace_id = get_or_create_trace_id(metadata)
        bind_trace_id(trace_id)
        return trace_id

    @staticmethod
    def _get_active_goals() -> list[str]:
        """Read active goals from environment (F-07)."""
        goals_str = os.environ.get("EXECUTIVE_GOALS", "")
        if not goals_str:
            return []
        return [g.strip() for g in goals_str.split(";") if g.strip()]

    @staticmethod
    def _extract_salience(salience_proto) -> dict[str, float]:
        """Extract salience dimensions from proto."""
        if not salience_proto:
            return {}
        return {
            "threat": salience_proto.threat,
            "opportunity": salience_proto.opportunity,
            "novelty": salience_proto.novelty,
        }

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

    async def ProcessEvent(
        self,
        request: executive_pb2.ProcessEventRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProcessEventResponse:
        """Process an event via DecisionStrategy Protocol."""
        self._setup_trace(context)
        self.events_received += 1

        logger.info(
            "ProcessEvent received",
            event_id=request.event.id,
            source=request.event.source,
            immediate=request.immediate,
            text_preview=request.event.raw_text[:50] if request.event.raw_text else "",
        )

        # Build candidates list
        candidates = []
        if request.HasField("suggestion") and request.suggestion.heuristic_id:
            candidates.append(HeuristicCandidate(
                heuristic_id=request.suggestion.heuristic_id,
                condition_text=request.suggestion.condition_text,
                suggested_action=request.suggestion.suggested_action,
                confidence=request.suggestion.confidence,
            ))

        decision_context = DecisionContext(
            event_id=request.event.id,
            event_text=request.event.raw_text or "",
            event_source=request.event.source,
            salience=self._extract_salience(request.event.salience),
            candidates=candidates,
            immediate=request.immediate,
            goals=self._get_active_goals(),
        )

        result = await self._strategy.decide(decision_context, self.ollama)

        return executive_pb2.ProcessEventResponse(
            accepted=result.path != DecisionPath.REJECTED,
            response_id=result.response_id,
            response_text=result.response_text,
            predicted_success=result.predicted_success,
            prediction_confidence=result.prediction_confidence,
            prompt_text=result.prompt_text,
            decision_path=result.path.value,
            matched_heuristic_id=result.matched_heuristic_id or "",
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

        trace = self._strategy.get_trace(request.response_id)
        if not request.positive:
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
        self._strategy.delete_trace(request.response_id)

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
            "active_traces": str(self._strategy.trace_count),
        }
        return types_pb2.GetHealthDetailsResponse(
            status=types_pb2.HEALTH_STATUS_HEALTHY,
            uptime_seconds=uptime,
            details=details,
        )


def create_decision_strategy(strategy_type: str, **kwargs) -> DecisionStrategy | None:
    """Factory function for decision strategies."""
    if strategy_type == "heuristic_first":
        return HeuristicFirstStrategy(HeuristicFirstConfig(
            confidence_threshold=float(kwargs.get("threshold", 0.7)),
        ))
    return None


async def serve(
    port: int = 50053,
    ollama_url: str | None = None,
    ollama_model: str = "gemma:2b",
    memory_address: str | None = None,
    heuristic_store_path: str = "heuristics.json",
) -> None:
    """Start the Executive stub server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))

    llm_provider = None
    if ollama_url:
        provider_type = os.environ.get("EXECUTIVE_LLM_PROVIDER", "ollama")
        llm_provider = create_llm_provider(
            provider_type,
            url=ollama_url,
            model=ollama_model
        )
        if llm_provider and await llm_provider.check_available():
            logger.info("Connected to LLM provider", provider=provider_type, model=ollama_model)
        elif llm_provider:
            logger.warning("LLM provider not available", provider=provider_type)
            llm_provider = None

    memory_client = None
    if memory_address:
        memory_client = MemoryClient(address=memory_address)
        if await memory_client.connect():
            logger.info("Connected to Memory service", address=memory_address)
        else:
            memory_client = None

    strategy_type = os.environ.get("EXECUTIVE_DECISION_STRATEGY", "heuristic_first")
    threshold = os.environ.get("EXECUTIVE_HEURISTIC_THRESHOLD", "0.7")
    decision_strategy = create_decision_strategy(strategy_type, threshold=threshold)
    if decision_strategy:
        logger.info("Decision strategy initialized", strategy=strategy_type, threshold=threshold)

    heuristic_store = HeuristicStore(heuristic_store_path)

    servicer = ExecutiveServicer(
        llm_provider=llm_provider,
        memory_client=memory_client,
        heuristic_store=heuristic_store,
        decision_strategy=decision_strategy,
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
