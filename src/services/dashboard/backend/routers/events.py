"""Events router — submit, list, SSE streams, feedback (HTMX/HTML endpoints)."""

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

import structlog

from backend.env import PROJECT_ROOT, env, PROTOS_AVAILABLE
from backend.utils import format_relative_time

logger = structlog.get_logger()

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import (
        common_pb2,
        executive_pb2,
        executive_pb2_grpc,
        memory_pb2,
        orchestrator_pb2,
        orchestrator_pb2_grpc,
    )

router = APIRouter(prefix="/api")

FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


def _make_event_dict(event_id: str, source: str, text: str,
                     timestamp=None, salience: dict = None,
                     response_text: str = "", response_id: str = "",
                     predicted_success: float = None,
                     prediction_confidence: float = None,
                     matched_heuristic_id: str = "",
                     decision_path: str = "") -> dict:
    """Build an event dict matching the event_row.html template."""
    now = datetime.now(timezone.utc)

    if response_text:
        status = "responded"
    elif response_id:
        status = "processing"
    else:
        status = "queued"

    # Use stored decision_path when available; fall back to derivation for old data
    if decision_path:
        path = decision_path.upper()
    elif matched_heuristic_id:
        path = "HEURISTIC"
    elif response_text or response_id:
        path = "LLM"
    else:
        path = ""

    salience_breakdown = {}
    if isinstance(salience, dict):
        for key in ("threat", "opportunity", "humor", "novelty", "goal_relevance",
                     "social", "emotional", "actionability", "habituation"):
            if key in salience:
                salience_breakdown[key] = f"{salience[key]:.2f}"

    time_abs = timestamp.strftime("%H:%M:%S") if timestamp else now.strftime("%H:%M:%S")
    time_rel = format_relative_time(timestamp) if timestamp else "just now"

    salience_score = "\u2014"
    if predicted_success is not None:
        salience_score = f"{predicted_success:.2f}"
    elif salience_breakdown:
        vals = [float(v) for v in salience_breakdown.values()]
        salience_score = f"{sum(vals) / len(vals):.2f}"

    return {
        "id": event_id,
        "source": source,
        "text": text,
        "status": status,
        "path": path,
        "response_text": response_text or "",
        "response_id": response_id or "",
        "time_relative": time_rel,
        "time_absolute": time_abs,
        "salience_score": salience_score,
        "confidence": f"{prediction_confidence:.2f}" if prediction_confidence else "\u2014",
        "salience_breakdown": salience_breakdown,
    }


def _proto_event_to_dict(ev) -> dict:
    """Convert a memory_pb2.EpisodicEvent proto to template-ready dict."""
    salience_data = {}
    if ev.salience:
        for key in ("threat", "opportunity", "humor", "novelty", "goal_relevance",
                     "social", "emotional", "actionability", "habituation"):
            salience_data[key] = getattr(ev.salience, key, 0.0)

    ts = datetime.fromtimestamp(ev.timestamp_ms / 1000, tz=timezone.utc) if ev.timestamp_ms else None

    # proto3 floats default to 0.0 — can't distinguish "unset" from "set to 0.0".
    # Pass the value through; _make_event_dict shows "0.00" which is correct when
    # the event was actually scored. The None/"—" path is lost at the proto layer.
    ps = ev.predicted_success if ev.predicted_success != 0.0 else None
    pc = ev.prediction_confidence if ev.prediction_confidence != 0.0 else None

    return _make_event_dict(
        event_id=ev.id,
        source=ev.source,
        text=ev.raw_text,
        timestamp=ts,
        salience=salience_data,
        response_text=ev.response_text,
        response_id=ev.response_id,
        predicted_success=ps,
        prediction_confidence=pc,
        matched_heuristic_id=ev.matched_heuristic_id or "",
        decision_path=ev.decision_path or "",
    )


async def _fetch_events(limit: int = 25, offset: int = 0,
                        source: str = None) -> list[dict]:
    """Fetch events via Memory service gRPC and convert to template-ready dicts."""
    stub = env.memory_stub()
    if not stub:
        return []
    try:
        resp = await stub.ListEvents(memory_pb2.ListEventsRequest(
            limit=limit,
            offset=offset,
            source=source or "",
        ))
        if resp.error:
            logger.error("ListEvents gRPC error", error=resp.error)
            return []
        return [_proto_event_to_dict(ev) for ev in resp.events]
    except grpc.RpcError as e:
        logger.error("ListEvents gRPC call failed", error=str(e))
        return []


@router.post("/events")
async def submit_event(request: Request):
    """Submit a single event to the orchestrator."""
    form = await request.form()
    source = form.get("source", "dashboard")
    text = form.get("text", "")
    salience_override = form.get("salience_override", "")

    if not text:
        return HTMLResponse('<span class="text-red-400">Error: text is required</span>', status_code=400)

    event_id = str(uuid.uuid4())

    # PublishEvents is a streaming RPC — must use sync stub in a thread
    stub = env.sync_orchestrator_stub()
    if not stub:
        return HTMLResponse('<span class="text-red-400">Error: orchestrator not available (proto stubs missing)</span>', status_code=503)

    salience = None
    if salience_override == "high":
        salience = common_pb2.SalienceVector(novelty=0.95, urgency=0.95, threat=0.0)
    elif salience_override == "low":
        salience = common_pb2.SalienceVector(novelty=0.1, urgency=0.1, threat=0.0)

    event = common_pb2.Event(
        id=event_id,
        source=source,
        raw_text=text,
    )
    if salience:
        event.salience.CopyFrom(salience)

    def _publish():
        try:
            def event_gen():
                yield event
            for _ack in stub.PublishEvents(event_gen()):
                break
        except grpc.RpcError as e:
            logger.error("PublishEvents gRPC failed", event_id=event_id, error=str(e))

    threading.Thread(target=_publish, daemon=True).start()

    return HTMLResponse(
        f'<span class="text-green-400" data-event-id="{event_id}" '
        f'data-source="{source}" data-text="{text[:60]}">Sent (id: {event_id[:8]})</span>'
    )


@router.get("/events")
async def list_events(request: Request, limit: int = 25, offset: int = 0,
                      source: Optional[str] = None):
    """List historical events — returns full lab tab."""
    events = await _fetch_events(limit=limit, offset=offset, source=source)
    return templates.TemplateResponse(request, "components/lab.html", {
        "initial_events": events,
    })


@router.get("/events/rows")
async def list_event_rows(request: Request, limit: int = 25, offset: int = 0,
                          source: Optional[str] = None):
    """Return just the event table rows (for htmx partial swap)."""
    events = await _fetch_events(limit=limit, offset=offset, source=source)
    html = ""
    for event in events:
        html += templates.get_template("components/event_row.html").render(event=event)
    return HTMLResponse(html)


@router.get("/queue/rows")
async def get_queue_rows(request: Request):
    """Queue contents as HTML rows for polling."""
    stub = env.orchestrator_stub()
    if not stub:
        return HTMLResponse("")
    try:
        resp = await stub.ListQueuedEvents(orchestrator_pb2.ListQueuedEventsRequest(limit=100))
        html = ""
        for qi in resp.events:
            html += templates.get_template("components/queue_row.html").render(item={
                "event_id": qi.event_id,
                "source": qi.source,
                "salience": qi.salience,
                "age_ms": qi.age_ms,
                "raw_text": qi.raw_text,
            })
        return HTMLResponse(html)
    except grpc.RpcError:
        return HTMLResponse("")


@router.get("/events/stream")
async def event_stream(request: Request):
    """SSE stream of event lifecycle updates via orchestrator subscription."""

    async def generate():
        # SSE runs a blocking gRPC stream in a thread — use sync stubs
        stub = env.sync_orchestrator_stub()
        if not stub:
            yield {"event": "error", "data": json.dumps({"error": "Proto stubs not available"})}
            return

        subscriber_id = f"dashboard-{uuid.uuid4().hex[:8]}"
        try:
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=True,
            )

            loop = asyncio.get_event_loop()
            response_queue = asyncio.Queue()

            def _subscribe():
                try:
                    mem_stub = env.sync_memory_stub()
                    for resp in stub.SubscribeResponses(req):
                        import time as _time
                        event_id = resp.event_id
                        event_data = None

                        # Retry fetching from Memory service (event may not be stored yet)
                        if mem_stub:
                            for _attempt in range(4):
                                try:
                                    get_resp = mem_stub.GetEvent(
                                        memory_pb2.GetEventRequest(event_id=event_id)
                                    )
                                    if get_resp.event and get_resp.event.id:
                                        ev = get_resp.event
                                        # Use response_text from SSE notification if available
                                        if hasattr(resp, "response_text") and resp.response_text:
                                            ev_copy = memory_pb2.EpisodicEvent()
                                            ev_copy.CopyFrom(ev)
                                            ev_copy.response_text = resp.response_text
                                            event_data = _proto_event_to_dict(ev_copy)
                                        else:
                                            event_data = _proto_event_to_dict(ev)
                                        break
                                except grpc.RpcError:
                                    pass
                                _time.sleep(0.25 * (_attempt + 1))

                        if not event_data:
                            event_data = _make_event_dict(
                                event_id=event_id,
                                source="",
                                text="",
                                response_text=resp.response_text if hasattr(resp, "response_text") else "",
                            )

                        asyncio.run_coroutine_threadsafe(
                            response_queue.put(event_data), loop
                        )
                except grpc.RpcError:
                    asyncio.run_coroutine_threadsafe(
                        response_queue.put(None), loop
                    )

            loop.run_in_executor(None, _subscribe)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(response_queue.get(), timeout=30)
                    if event_data is None:
                        break
                    html = templates.get_template("components/event_row.html").render(
                        event=event_data
                    )
                    yield {"data": html}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generate())


@router.get("/responses/stream")
async def response_stream(request: Request):
    """SSE stream for response arrival notifications."""
    return await event_stream(request)


@router.post("/feedback")
async def submit_feedback(request: Request):
    """Submit feedback on a response."""
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else dict(await request.form())

    event_id = body.get("event_id", "")
    response_id = body.get("response_id", "")
    feedback = body.get("feedback", "")

    if not event_id:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "event_id required"}, status_code=400)

    stub = env.executive_stub()
    if not stub:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        positive = feedback in ("good", "positive", "true", "1")
        resp = await stub.ProvideFeedback(executive_pb2.ProvideFeedbackRequest(
            event_id=event_id,
            positive=positive,
            response_id=response_id,
        ))
        if getattr(resp, "created_heuristic_id", ""):
            label = f"\u2728 Created heuristic {resp.created_heuristic_id[:8]}\u2026"
        elif positive:
            label = "\U0001f44d Saved"
        else:
            label = "\U0001f44e Saved"
        if getattr(resp, "error_message", ""):
            label += f" ({resp.error_message})"
        return HTMLResponse(f'<span class="text-green-400 text-[10px]">{label}</span>')
    except grpc.RpcError as e:
        return HTMLResponse(f'<span class="text-red-400 text-[10px]">Error: {e.code().name}</span>', status_code=502)
