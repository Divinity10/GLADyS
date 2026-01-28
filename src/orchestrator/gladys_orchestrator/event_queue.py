"""Event Queue for priority-based processing.

Replaces MomentAccumulator for PoC. Events are queued by salience priority
and processed asynchronously. Events without high-confidence heuristics
go through this queue to the LLM (Executive).

Architecture:
- Events added with salience priority (higher = process sooner)
- Background worker dequeues and sends to Executive
- Timeout scanner removes stale events
- All in-memory for PoC (events lost on restart is acceptable)
"""

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from gladys_common import get_logger

from .config import OrchestratorConfig

logger = get_logger(__name__)


@dataclass
class QueuedEvent:
    """An event waiting in the queue."""
    event_id: str
    event: Any
    salience: float
    enqueue_time_ms: int
    matched_heuristic_id: str = ""


class EventQueue:
    """
    Priority queue for events awaiting LLM processing.

    Events are ordered by salience (highest first). A background worker
    dequeues events and sends them to Executive for processing.

    For PoC: Pure in-memory, events lost on restart is acceptable.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        process_callback: Optional[Callable[[Any], Coroutine[Any, Any, dict]]] = None,
        broadcast_callback: Optional[Callable[[dict], Coroutine[Any, Any, None]]] = None,
    ):
        """
        Initialize the event queue.

        Args:
            config: Orchestrator configuration
            process_callback: Async function to process event (send to Executive)
            broadcast_callback: Async function to broadcast response to subscribers
        """
        self.config = config
        self._process_callback = process_callback
        self._broadcast_callback = broadcast_callback

        # Priority queue: (-salience, counter, event_id) for max-heap behavior
        # Counter breaks ties deterministically (FIFO for same salience)
        self._heap: list[tuple[float, int, str]] = []
        self._counter = 0

        # Pending events by ID for quick lookup
        self._pending: dict[str, QueuedEvent] = {}

        # Background tasks
        self._worker_task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Stats
        self._total_queued = 0
        self._total_processed = 0
        self._total_timed_out = 0

    async def start(self) -> None:
        """Start background worker and timeout scanner."""
        self._shutdown = False
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name="event_queue_worker"
        )
        self._timeout_task = asyncio.create_task(
            self._timeout_scanner(),
            name="event_queue_timeout"
        )
        logger.info("EventQueue started")

    async def stop(self) -> None:
        """Stop background tasks gracefully."""
        self._shutdown = True

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

        logger.info(
            f"EventQueue stopped: queued={self._total_queued}, "
            f"processed={self._total_processed}, timed_out={self._total_timed_out}"
        )

    def enqueue(
        self,
        event: Any,
        salience: float,
        matched_heuristic_id: str = "",
    ) -> None:
        """
        Add an event to the queue.

        Args:
            event: The event to queue
            salience: Priority (higher = process sooner)
            matched_heuristic_id: Optional matched heuristic (for tracking)
        """
        event_id = getattr(event, "id", str(id(event)))
        now_ms = int(time.time() * 1000)

        queued = QueuedEvent(
            event_id=event_id,
            event=event,
            salience=salience,
            enqueue_time_ms=now_ms,
            matched_heuristic_id=matched_heuristic_id,
        )

        self._pending[event_id] = queued

        # Use negative salience for max-heap behavior (heapq is min-heap)
        heapq.heappush(self._heap, (-salience, self._counter, event_id))
        self._counter += 1
        self._total_queued += 1

        logger.debug(
            f"Queued event {event_id}: salience={salience:.2f}, "
            f"queue_size={len(self._pending)}"
        )

    async def _worker_loop(self) -> None:
        """Background worker that processes queued events."""
        logger.info("EventQueue worker started")

        while not self._shutdown:
            try:
                # Get next event from queue
                queued = self._dequeue()
                if queued is None:
                    # Queue empty, wait a bit
                    await asyncio.sleep(0.05)  # 50ms polling
                    continue

                # Process the event
                await self._process_event(queued)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"EventQueue worker error: {e}")
                await asyncio.sleep(0.1)  # Back off on error

    def _dequeue(self) -> Optional[QueuedEvent]:
        """Remove and return highest-priority event, or None if empty."""
        while self._heap:
            _, _, event_id = heapq.heappop(self._heap)

            # Event might have been removed (timeout, etc.)
            if event_id in self._pending:
                return self._pending.pop(event_id)

        return None

    async def _process_event(self, queued: QueuedEvent) -> None:
        """Process a single queued event."""
        event_id = queued.event_id
        start_time = time.time()

        logger.info(f"Processing queued event {event_id}")

        try:
            # Call Executive via callback
            response = None
            if self._process_callback:
                response = await self._process_callback(queued.event)

            process_time_ms = int((time.time() - start_time) * 1000)
            self._total_processed += 1

            # Broadcast response
            if self._broadcast_callback and response:
                await self._broadcast_callback({
                    "event_id": event_id,
                    "response_id": response.get("response_id", ""),
                    "response_text": response.get("response_text", ""),
                    "predicted_success": response.get("predicted_success", 0.0),
                    "prediction_confidence": response.get("prediction_confidence", 0.0),
                    "routing_path": "QUEUED",
                    "matched_heuristic_id": queued.matched_heuristic_id,
                    "event_source": getattr(queued.event, "source", ""),
                    "event_timestamp_ms": queued.enqueue_time_ms,
                    "response_timestamp_ms": int(time.time() * 1000),
                })

            logger.info(
                f"Processed event {event_id}: "
                f"time={process_time_ms}ms, response={bool(response)}"
            )

        except Exception as e:
            logger.error(f"Failed to process event {event_id}: {e}")
            # Could broadcast error response here

    async def _timeout_scanner(self) -> None:
        """Background task to remove timed-out events."""
        timeout_ms = getattr(self.config, 'event_timeout_ms', 30000)
        scan_interval_ms = getattr(self.config, 'timeout_scan_interval_ms', 2000)
        scan_interval_sec = scan_interval_ms / 1000.0

        logger.info(
            f"EventQueue timeout scanner started: "
            f"timeout={timeout_ms}ms, interval={scan_interval_ms}ms"
        )

        while not self._shutdown:
            try:
                await asyncio.sleep(scan_interval_sec)

                now_ms = int(time.time() * 1000)
                timed_out = []

                for event_id, queued in list(self._pending.items()):
                    age_ms = now_ms - queued.enqueue_time_ms
                    if age_ms > timeout_ms:
                        timed_out.append(event_id)

                for event_id in timed_out:
                    queued = self._pending.pop(event_id, None)
                    if queued:
                        self._total_timed_out += 1
                        logger.warning(
                            f"Event {event_id} timed out after "
                            f"{now_ms - queued.enqueue_time_ms}ms"
                        )

                        # Broadcast timeout/error response
                        if self._broadcast_callback:
                            await self._broadcast_callback({
                                "event_id": event_id,
                                "response_id": "",
                                "response_text": "(Request timed out)",
                                "predicted_success": 0.0,
                                "prediction_confidence": 0.0,
                                "routing_path": "TIMEOUT",
                                "matched_heuristic_id": queued.matched_heuristic_id,
                                "event_source": getattr(queued.event, "source", ""),
                                "event_timestamp_ms": queued.enqueue_time_ms,
                                "response_timestamp_ms": int(time.time() * 1000),
                            })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Timeout scanner error: {e}")

    @property
    def queue_size(self) -> int:
        """Number of events currently queued."""
        return len(self._pending)

    @property
    def stats(self) -> dict:
        """Get queue statistics."""
        return {
            "queue_size": len(self._pending),
            "total_queued": self._total_queued,
            "total_processed": self._total_processed,
            "total_timed_out": self._total_timed_out,
        }
