"""Events REST API — batch submit, queue, delete."""

import threading
import uuid

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.env import env, PROTOS_AVAILABLE
from gladys_client import db as _db

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import (
        common_pb2,
        orchestrator_pb2,
    )

router = APIRouter(prefix="/api")


class BatchEvent(BaseModel):
    source: str = "batch"
    text: str
    id: str | None = None


@router.post("/events/batch")
async def submit_batch(request: Request):
    """Submit a batch of events from JSON body."""
    body = await request.json()
    if not isinstance(body, list):
        return JSONResponse({"error": "Body must be a JSON array of events"}, status_code=400)

    if len(body) > 50:
        return JSONResponse({"error": "Maximum 50 events per batch"}, status_code=400)

    try:
        validated = [BatchEvent(**item) for item in body]
    except Exception as e:
        return JSONResponse({"error": f"Validation error: {e}"}, status_code=400)

    stub = env.orchestrator_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    event_ids = []
    events = []
    for item in validated:
        event_id = item.id or str(uuid.uuid4())
        event_ids.append(event_id)
        events.append(common_pb2.Event(
            id=event_id,
            source=item.source,
            raw_text=item.text,
        ))

    def _publish_all():
        for event in events:
            try:
                def gen():
                    yield event
                for _ack in stub.PublishEvents(gen()):
                    break
            except grpc.RpcError:
                pass

    threading.Thread(target=_publish_all, daemon=True).start()

    return JSONResponse({"accepted": len(events), "event_ids": event_ids})


@router.get("/queue")
async def get_queue():
    """Get current queue contents from orchestrator."""
    stub = env.orchestrator_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        resp = await stub.ListQueuedEvents(orchestrator_pb2.ListQueuedEventsRequest(limit=100))
        items = []
        for qi in resp.events:
            items.append({
                "event_id": qi.event_id,
                "source": qi.source,
                "salience": qi.salience,
                "age_ms": qi.age_ms,
                "matched_heuristic_id": qi.matched_heuristic_id,
                "raw_text": qi.raw_text,
            })
        return JSONResponse({"events": items, "count": len(items)})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    """Archive a single event."""
    try:
        found = _db.delete_event(env.get_db_dsn(), event_id)
        if not found:
            return JSONResponse({"error": "Event not found"}, status_code=404)
        return JSONResponse({"deleted": event_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/events")
async def delete_all_events():
    """Archive all events."""
    try:
        count = _db.delete_all_events(env.get_db_dsn())
        return JSONResponse({"deleted": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
