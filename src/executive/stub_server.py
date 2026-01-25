#!/usr/bin/env python3
"""Executive stub server for testing.

This is a minimal Python implementation of the Executive service
for integration testing. The real Executive will be in C#/.NET.

Usage:
    python stub_server.py [--port PORT] [--memory-address ADDRESS]

Environment variables (or use .env file):
    OLLAMA_URL: URL of Ollama server (required for LLM features)
    OLLAMA_MODEL: Model to use (required for LLM features)
    MEMORY_ADDRESS: Address of Memory service for heuristic storage (e.g., localhost:50051)
    HEURISTIC_STORE_PATH: Path to heuristics JSON file (fallback when Memory unavailable)
"""

import argparse
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

# Load .env file (searches up directory tree to find project root .env)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass  # dotenv not installed, rely on environment variables

# Add orchestrator and memory to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))
sys.path.insert(0, str(Path(__file__).parent.parent / "memory" / "python"))

import grpc
from grpc_reflection.v1alpha import reflection

from gladys_orchestrator.generated import executive_pb2
from gladys_orchestrator.generated import executive_pb2_grpc
from gladys_orchestrator.generated import common_pb2

# Memory proto imports (for StoreHeuristic RPC)
# Try orchestrator's generated stubs first (same protos), then memory's
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

    async def generate(self, prompt: str, system: str | None = None) -> str | None:
        """Generate a response from the LLM.

        Returns None if Ollama is not available or request fails.
        """
        if self._available is False:
            return None

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

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
    """Async gRPC client for Memory service's StoreHeuristic RPC."""

    def __init__(self, address: str = "localhost:50051"):
        self.address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub = None
        self._available: bool | None = None

    async def connect(self) -> bool:
        """Connect to the Memory service."""
        if not MEMORY_PROTO_AVAILABLE:
            logger.warning("Memory proto stubs not available - cannot connect")
            self._available = False
            return False

        try:
            self._channel = grpc.aio.insecure_channel(self.address)
            # Wait for channel to be ready (with timeout)
            await asyncio.wait_for(
                self._channel.channel_ready(),
                timeout=5.0,
            )
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
        """Store a heuristic via the Memory service.

        Args:
            heuristic: The Heuristic dataclass to store

        Returns:
            Tuple of (success, heuristic_id or error_message)
        """
        if not self._available or not self._stub:
            return False, "Memory service not available"

        try:
            # Convert effects_json dict to JSON string
            effects_json_str = json.dumps(heuristic.effects_json) if heuristic.effects_json else "{}"

            # Build the proto Heuristic message
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

            # Call StoreHeuristic RPC with generate_embedding=True
            request = memory_pb2.StoreHeuristicRequest(
                heuristic=proto_heuristic,
                generate_embedding=True,
            )

            response = await self._stub.StoreHeuristic(request)

            if response.success:
                logger.info(f"Stored heuristic in Memory: id={response.heuristic_id}")
                return True, response.heuristic_id
            else:
                logger.warning(f"Memory StoreHeuristic failed: {response.error}")
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
        """Update heuristic confidence based on feedback (TD learning).

        Args:
            heuristic_id: UUID of the heuristic to update
            positive: True for positive feedback, False for negative
            learning_rate: Optional learning rate override

        Returns:
            Tuple of (success, error_or_empty, old_confidence, new_confidence)
        """
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
                logger.info(
                    f"TD_LEARNING: heuristic={heuristic_id}, positive={positive}, "
                    f"old={response.old_confidence:.3f}, new={response.new_confidence:.3f}"
                )
                return True, "", response.old_confidence, response.new_confidence
            else:
                logger.warning(f"UpdateHeuristicConfidence failed: {response.error}")
                return False, response.error, 0.0, 0.0

        except grpc.aio.AioRpcError as e:
            logger.warning(f"UpdateHeuristicConfidence RPC error: {e.code()} - {e.details()}")
            return False, str(e.details()), 0.0, 0.0
        except Exception as e:
            logger.warning(f"UpdateHeuristicConfidence failed: {e}")
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


def format_moment_for_llm(moment: Any) -> str:
    """Format a moment (batch of events) into an LLM prompt."""
    lines = ["Recent events:"]
    for event in moment.events:
        lines.append(f"  - {format_event_for_llm(event)}")
    return "\n".join(lines)


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
    context: str  # Formatted event context
    response: str  # LLM response
    timestamp: float
    matched_heuristic_id: str | None = None  # For TD learning confidence updates
    predicted_success: float = 0.0
    prediction_confidence: float = 0.0

    def age_seconds(self) -> float:
        return time.time() - self.timestamp


# How long to keep reasoning traces (5 minutes)
TRACE_RETENTION_SECONDS = 300


@dataclass
class Heuristic:
    """A learned heuristic (CBR case) for the PoC."""
    id: str
    name: str
    condition_text: str  # Human-readable condition
    effects_json: dict   # Action to take
    confidence: float    # Starts at 0.3 for learned heuristics
    origin: str          # 'built_in', 'pack', 'learned', 'user'
    origin_id: str       # Reasoning trace ID for learned heuristics
    created_at: float    # Unix timestamp


class HeuristicStore:
    """Simple file-based heuristic storage for PoC testing.

    Stores heuristics in a JSON file. For production, this would be
    replaced by the Memory service with pgvector for embedding-based matching.
    """

    def __init__(self, path: str | Path = "heuristics.json"):
        self.path = Path(path)
        self.heuristics: dict[str, Heuristic] = {}
        self._load()

    def _load(self) -> None:
        """Load heuristics from file."""
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                    for h_data in data.get("heuristics", []):
                        h = Heuristic(**h_data)
                        self.heuristics[h.id] = h
                logger.info(f"Loaded {len(self.heuristics)} heuristics from {self.path}")
            except Exception as e:
                logger.warning(f"Failed to load heuristics from {self.path}: {e}")

    def _save(self) -> None:
        """Save heuristics to file."""
        try:
            data = {
                "heuristics": [asdict(h) for h in self.heuristics.values()]
            }
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save heuristics to {self.path}: {e}")

    def add(self, heuristic: Heuristic) -> None:
        """Add a new heuristic."""
        self.heuristics[heuristic.id] = heuristic
        self._save()
        logger.info(f"Stored heuristic: id={heuristic.id}, condition='{heuristic.condition_text}'")

    def get(self, heuristic_id: str) -> Heuristic | None:
        """Get a heuristic by ID."""
        return self.heuristics.get(heuristic_id)

    def list_all(self) -> list[Heuristic]:
        """List all heuristics."""
        return list(self.heuristics.values())


class ExecutiveServicer(executive_pb2_grpc.ExecutiveServiceServicer):
    """Stub implementation of ExecutiveService for testing.

    Processes events/moments and optionally calls an LLM for responses.
    Tracks reasoning traces for heuristic formation via feedback.
    """

    def __init__(
        self,
        ollama_client: OllamaClient | None = None,
        memory_client: MemoryClient | None = None,
        heuristic_store: HeuristicStore | None = None,
    ):
        self.events_received = 0
        self.moments_received = 0
        self.total_events_in_moments = 0
        self.heuristics_created = 0
        self.ollama = ollama_client
        self.memory_client = memory_client
        # File-based store as fallback when Memory service unavailable
        self.heuristic_store = heuristic_store or HeuristicStore()
        # Reasoning trace storage: response_id -> ReasoningTrace
        self.reasoning_traces: dict[str, ReasoningTrace] = {}

    def _cleanup_old_traces(self) -> int:
        """Remove traces older than TRACE_RETENTION_SECONDS. Returns count removed."""
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
        """Store a reasoning trace and return the response_id."""
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
        # Cleanup old traces periodically
        if len(self.reasoning_traces) > 100:
            removed = self._cleanup_old_traces()
            if removed:
                logger.debug(f"Cleaned up {removed} old reasoning traces")
        return response_id

    async def ProcessEvent(
        self,
        request: executive_pb2.ProcessEventRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProcessEventResponse:
        """Process a high-salience event."""
        self.events_received += 1
        event = request.event

        # Log event details
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

        # If we have an LLM, get a response for high-salience events
        if self.ollama and request.immediate:
            event_context = format_event_for_llm(event)
            prompt = f"URGENT event: {event_context}\n\nHow should I respond?"
            llm_response = await self.ollama.generate(prompt, system=EXECUTIVE_SYSTEM_PROMPT)
            if llm_response:
                response_text = llm_response.strip()
                logger.info(f"GLADyS: {response_text}")

                # Predict success (Instrument Now, Analyze Later)
                prediction_json = await self.ollama.generate(
                    PREDICTION_PROMPT.format(context=event_context, response=response_text)
                )
                if prediction_json:
                    try:
                        # Clean up the response - LLM might include markdown code blocks
                        clean_json = prediction_json.strip()
                        if clean_json.startswith("```"):
                            lines = clean_json.split("\n")
                            clean_json = "\n".join(
                                line for line in lines
                                if not line.startswith("```")
                            ).strip()

                        pred_data = json.loads(clean_json)
                        predicted_success = float(pred_data.get("success", 0.5))
                        prediction_confidence = float(pred_data.get("confidence", 0.5))
                        logger.debug(f"Prediction: success={predicted_success:.2f}, conf={prediction_confidence:.2f}")
                    except Exception as e:
                        logger.warning(f"Failed to parse prediction JSON: {e}")
                        predicted_success = 0.5
                        prediction_confidence = 0.5

                # Extract matched heuristic ID for TD learning (if present)
                matched_heuristic = getattr(event, "matched_heuristic_id", "") or ""
                # Store reasoning trace for potential heuristic formation
                response_id = self._store_trace(
                    event_id=event.id,
                    context=event_context,
                    response=response_text,
                    matched_heuristic_id=matched_heuristic if matched_heuristic else None,
                    predicted_success=predicted_success,
                    prediction_confidence=prediction_confidence,
                )
                logger.debug(
                    f"Stored reasoning trace: response_id={response_id}, "
                    f"matched_heuristic={matched_heuristic or 'none'}"
                )

        return executive_pb2.ProcessEventResponse(
            accepted=True,
            response_id=response_id,
            response_text=response_text,
            predicted_success=predicted_success,
            prediction_confidence=prediction_confidence,
        )

    async def ProcessMoment(
        self,
        request: executive_pb2.ProcessMomentRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProcessMomentResponse:
        """Process an accumulated moment."""
        self.moments_received += 1
        moment = request.moment
        event_count = len(moment.events)
        self.total_events_in_moments += event_count

        # Log moment summary
        logger.info(f"MOMENT: {event_count} events")
        for i, event in enumerate(moment.events[:3]):  # Log first 3 events
            threat = event.salience.threat if event.salience else 0.0
            logger.info(f"  [{i}] id={event.id}, source={event.source}, threat={threat:.2f}")
        if event_count > 3:
            logger.info(f"  ... and {event_count - 3} more events")

        # If we have an LLM, summarize the moment
        if self.ollama and event_count > 0:
            prompt = format_moment_for_llm(moment) + "\n\nBriefly summarize and note anything that needs attention."
            response = await self.ollama.generate(prompt, system=EXECUTIVE_SYSTEM_PROMPT)
            if response:
                logger.info(f"GLADyS: {response.strip()}")

        # Log stats periodically
        if self.moments_received % 10 == 0:
            logger.info(
                f"STATS: {self.events_received} immediate events, "
                f"{self.moments_received} moments, {self.total_events_in_moments} total events"
            )

        return executive_pb2.ProcessMomentResponse(
            accepted=True,
            events_processed=event_count,
        )

    async def ProvideFeedback(
        self,
        request: executive_pb2.ProvideFeedbackRequest,
        context: grpc.aio.ServicerContext,
    ) -> executive_pb2.ProvideFeedbackResponse:
        """Handle feedback on a previous LLM response.

        If positive feedback:
        1. Look up the reasoning trace by response_id
        2. Ask LLM to extract a generalizable pattern
        3. Store as new heuristic (via Memory service)

        If negative feedback:
        - TD learning: decrease confidence of the matched heuristic
        """
        logger.info(
            f"FEEDBACK: response_id={request.response_id}, "
            f"event_id={request.event_id}, positive={request.positive}"
        )

        # Handle negative feedback with TD learning
        if not request.positive:
            # Look up the reasoning trace to find which heuristic matched
            trace = self.reasoning_traces.get(request.response_id)
            if not trace:
                logger.warning(
                    f"Negative feedback: no reasoning trace for response_id={request.response_id}"
                )
                return executive_pb2.ProvideFeedbackResponse(
                    accepted=True,
                    error_message="Reasoning trace not found or expired",
                )

            if not trace.matched_heuristic_id:
                logger.info(
                    f"Negative feedback: no heuristic was matched for this event "
                    f"(response_id={request.response_id}, event_id={trace.event_id})"
                )
                return executive_pb2.ProvideFeedbackResponse(accepted=True)

            # Call Memory service to decrease heuristic confidence
            if self.memory_client:
                success, error, old_conf, new_conf = await self.memory_client.update_heuristic_confidence(
                    heuristic_id=trace.matched_heuristic_id,
                    positive=False,
                )
                if success:
                    logger.info(
                        f"TD_LEARNING: Negative feedback decreased confidence for heuristic "
                        f"{trace.matched_heuristic_id}: {old_conf:.3f} -> {new_conf:.3f}"
                    )
                else:
                    logger.warning(
                        f"TD_LEARNING: Failed to update confidence for heuristic "
                        f"{trace.matched_heuristic_id}: {error}"
                    )
            else:
                logger.warning("TD_LEARNING: Memory service not available for confidence update")

            return executive_pb2.ProvideFeedbackResponse(accepted=True)

        # Look up the reasoning trace
        trace = self.reasoning_traces.get(request.response_id)
        if not trace:
            logger.warning(f"No reasoning trace found for response_id={request.response_id}")
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="Reasoning trace not found or expired",
            )

        # If no LLM available, can't extract pattern
        if not self.ollama:
            logger.warning("Cannot extract pattern - no LLM available")
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="LLM not available for pattern extraction",
            )

        # Ask LLM to extract a generalizable pattern
        extraction_prompt = PATTERN_EXTRACTION_PROMPT.format(
            context=trace.context,
            response=trace.response,
        )
        logger.debug(f"Extracting pattern with prompt: {extraction_prompt[:200]}...")

        pattern_json = await self.ollama.generate(extraction_prompt)
        if not pattern_json:
            logger.warning("LLM did not return a pattern")
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message="Pattern extraction failed",
            )

        # Parse the extracted pattern
        try:
            # Clean up the response - LLM might include markdown code blocks
            pattern_text = pattern_json.strip()
            if pattern_text.startswith("```"):
                # Remove markdown code block markers
                lines = pattern_text.split("\n")
                pattern_text = "\n".join(
                    line for line in lines
                    if not line.startswith("```")
                ).strip()

            pattern = json.loads(pattern_text)
            condition = pattern.get("condition", "")
            action = pattern.get("action", {})

            if not condition:
                raise ValueError("Missing 'condition' in extracted pattern")

            logger.info(f"Extracted pattern: condition='{condition}', action={action}")

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse pattern JSON: {e}\nRaw: {pattern_json}")
            return executive_pb2.ProvideFeedbackResponse(
                accepted=True,
                error_message=f"Pattern parsing failed: {e}",
            )

        # TD learning: if there was a matched heuristic, increase its confidence
        if trace.matched_heuristic_id and self.memory_client:
            success, error, old_conf, new_conf = await self.memory_client.update_heuristic_confidence(
                heuristic_id=trace.matched_heuristic_id,
                positive=True,
            )
            if success:
                logger.info(
                    f"TD_LEARNING: Positive feedback increased confidence for heuristic "
                    f"{trace.matched_heuristic_id}: {old_conf:.3f} -> {new_conf:.3f}"
                )
            else:
                logger.warning(
                    f"TD_LEARNING: Failed to update confidence for heuristic "
                    f"{trace.matched_heuristic_id}: {error}"
                )

        # Create and store the new heuristic
        heuristic_id = str(uuid.uuid4())
        heuristic = Heuristic(
            id=heuristic_id,
            name=f"Learned: {condition[:50]}..." if len(condition) > 50 else f"Learned: {condition}",
            condition_text=condition,
            effects_json=action,
            confidence=0.3,  # Low initial confidence - must earn trust
            origin="learned",
            origin_id=trace.response_id,
            created_at=time.time(),
        )

        # Try to store via Memory service (preferred path)
        stored_via_memory = False
        if self.memory_client:
            success, result = await self.memory_client.store_heuristic(heuristic)
            if success:
                stored_via_memory = True
                logger.info(f"Stored heuristic via Memory service: id={result}")
            else:
                logger.warning(f"Memory service storage failed: {result}, falling back to file storage")

        # Fallback to file-based storage if Memory not available
        if not stored_via_memory:
            self.heuristic_store.add(heuristic)
            logger.info(f"Stored heuristic via file storage: id={heuristic_id}")

        self.heuristics_created += 1

        logger.info(
            f"HEURISTIC CREATED: id={heuristic_id}, "
            f"condition='{condition}', origin_id={trace.response_id}, "
            f"storage={'memory' if stored_via_memory else 'file'}"
        )

        # Clean up the used trace
        del self.reasoning_traces[request.response_id]

        return executive_pb2.ProvideFeedbackResponse(
            accepted=True,
            created_heuristic_id=heuristic_id,
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

    # Initialize Ollama client if URL provided
    ollama_client = None
    if ollama_url:
        ollama_client = OllamaClient(base_url=ollama_url, model=ollama_model)
        if await ollama_client.check_available():
            logger.info(f"Connected to Ollama at {ollama_url} (model: {ollama_model})")
        else:
            logger.warning(f"Ollama not available at {ollama_url} - running without LLM")
            ollama_client = None

    # Initialize Memory client for heuristic storage
    memory_client = None
    if memory_address:
        memory_client = MemoryClient(address=memory_address)
        if await memory_client.connect():
            logger.info(f"Connected to Memory service at {memory_address}")
        else:
            logger.warning(f"Memory service not available at {memory_address} - using file storage")
            memory_client = None

    # Initialize file-based heuristic store (fallback)
    heuristic_store = HeuristicStore(heuristic_store_path)
    logger.info(f"Heuristic file store: {heuristic_store_path} ({len(heuristic_store.heuristics)} loaded)")

    servicer = ExecutiveServicer(
        ollama_client=ollama_client,
        memory_client=memory_client,
        heuristic_store=heuristic_store,
    )
    executive_pb2_grpc.add_ExecutiveServiceServicer_to_server(servicer, server)

    # Enable reflection for debugging
    SERVICE_NAMES = (
        executive_pb2.DESCRIPTOR.services_by_name["ExecutiveService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    address = f"0.0.0.0:{port}"
    server.add_insecure_port(address)

    logger.info(f"Starting Executive stub server on {address}")
    if memory_client:
        logger.info(f"  Heuristic storage: Memory service ({memory_address})")
    else:
        logger.info(f"  Heuristic storage: File ({heuristic_store_path})")
    logger.info("(This is a test stub - the real Executive will be C#/.NET)")
    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        if memory_client:
            await memory_client.close()
        await server.stop(grace=5)


def main():
    parser = argparse.ArgumentParser(description="Executive stub server for testing")
    parser.add_argument("--port", type=int, default=50053, help="Port to listen on")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--ollama-url", type=str, default=None, help="Ollama server URL (or set OLLAMA_URL)")
    parser.add_argument("--ollama-model", type=str, default=None, help="Ollama model name (or set OLLAMA_MODEL)")
    parser.add_argument(
        "--memory-address",
        type=str,
        default=None,
        help="Memory service address for heuristic storage (e.g., localhost:50051)",
    )
    parser.add_argument(
        "--heuristic-store",
        type=str,
        default="heuristics.json",
        help="Path to heuristics JSON file (fallback when Memory unavailable)",
    )
    args = parser.parse_args()

    # Environment variables override CLI args
    ollama_url = os.environ.get("OLLAMA_URL", args.ollama_url)
    ollama_model = os.environ.get("OLLAMA_MODEL", args.ollama_model)
    memory_address = os.environ.get("MEMORY_ADDRESS", args.memory_address)
    heuristic_store_path = os.environ.get("HEURISTIC_STORE_PATH", args.heuristic_store)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        asyncio.run(serve(
            args.port,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            memory_address=memory_address,
            heuristic_store_path=heuristic_store_path,
        ))
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
