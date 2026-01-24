#!/usr/bin/env python3
"""Executive stub server for testing.

This is a minimal Python implementation of the Executive service
for integration testing. The real Executive will be in C#/.NET.

Usage:
    python stub_server.py [--port PORT]

Environment variables:
    OLLAMA_URL: URL of Ollama server (default: http://localhost:11434)
    OLLAMA_MODEL: Model to use (default: gemma:2b)
    HEURISTIC_STORE_PATH: Path to heuristics JSON file (default: heuristics.json)
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

# Add orchestrator to path for generated protos
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator"))

import grpc
from grpc_reflection.v1alpha import reflection

from gladys_orchestrator.generated import executive_pb2
from gladys_orchestrator.generated import executive_pb2_grpc
from gladys_orchestrator.generated import common_pb2

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


@dataclass
class ReasoningTrace:
    """Stores context for pattern extraction when feedback is received."""
    event_id: str
    response_id: str
    context: str  # Formatted event context
    response: str  # LLM response
    timestamp: float

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
        heuristic_store: HeuristicStore | None = None,
    ):
        self.events_received = 0
        self.moments_received = 0
        self.total_events_in_moments = 0
        self.heuristics_created = 0
        self.ollama = ollama_client
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

    def _store_trace(self, event_id: str, context: str, response: str) -> str:
        """Store a reasoning trace and return the response_id."""
        response_id = str(uuid.uuid4())
        self.reasoning_traces[response_id] = ReasoningTrace(
            event_id=event_id,
            response_id=response_id,
            context=context,
            response=response,
            timestamp=time.time(),
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

        # If we have an LLM, get a response for high-salience events
        if self.ollama and request.immediate:
            event_context = format_event_for_llm(event)
            prompt = f"URGENT event: {event_context}\n\nHow should I respond?"
            llm_response = await self.ollama.generate(prompt, system=EXECUTIVE_SYSTEM_PROMPT)
            if llm_response:
                response_text = llm_response.strip()
                logger.info(f"GLADyS: {response_text}")
                # Store reasoning trace for potential heuristic formation
                response_id = self._store_trace(
                    event_id=event.id,
                    context=event_context,
                    response=response_text,
                )
                logger.debug(f"Stored reasoning trace: response_id={response_id}")

        return executive_pb2.ProcessEventResponse(
            accepted=True,
            response_id=response_id,
            response_text=response_text,
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
        - TODO: TD learning to decrease confidence of matched heuristic
        """
        logger.info(
            f"FEEDBACK: response_id={request.response_id}, "
            f"event_id={request.event_id}, positive={request.positive}"
        )

        # For negative feedback, just acknowledge for now
        # TD learning (confidence decrease) will be added later
        if not request.positive:
            logger.info("Negative feedback received - TD learning not yet implemented")
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

        self.heuristic_store.add(heuristic)
        self.heuristics_created += 1

        logger.info(
            f"HEURISTIC CREATED: id={heuristic_id}, "
            f"condition='{condition}', origin_id={trace.response_id}"
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

    # Initialize heuristic store
    heuristic_store = HeuristicStore(heuristic_store_path)
    logger.info(f"Heuristic store: {heuristic_store_path} ({len(heuristic_store.heuristics)} loaded)")

    servicer = ExecutiveServicer(
        ollama_client=ollama_client,
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
    logger.info("(This is a test stub - the real Executive will be C#/.NET)")
    await server.start()

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)


def main():
    parser = argparse.ArgumentParser(description="Executive stub server for testing")
    parser.add_argument("--port", type=int, default=50053, help="Port to listen on")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--ollama-url", type=str, default=None, help="Ollama server URL")
    parser.add_argument("--ollama-model", type=str, default="gemma:2b", help="Ollama model name")
    parser.add_argument(
        "--heuristic-store",
        type=str,
        default="heuristics.json",
        help="Path to heuristics JSON file",
    )
    args = parser.parse_args()

    # Environment variables override CLI args
    ollama_url = os.environ.get("OLLAMA_URL", args.ollama_url)
    ollama_model = os.environ.get("OLLAMA_MODEL", args.ollama_model)
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
            heuristic_store_path=heuristic_store_path,
        ))
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
