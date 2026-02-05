"""Responses router — view event decision chains (HTMX/HTML endpoints)."""

from datetime import datetime, timezone
from typing import Optional, List

import grpc
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import structlog

from backend.env import PROJECT_ROOT, env, PROTOS_AVAILABLE
from backend.utils import format_relative_time

logger = structlog.get_logger()

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import (
        memory_pb2,
    )

router = APIRouter(prefix="/api")

FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


def _proto_summary_to_dict(s) -> dict:
    """Convert a memory_pb2.ResponseSummary proto to template-ready dict."""
    ts = datetime.fromtimestamp(s.timestamp_ms / 1000, tz=timezone.utc) if s.timestamp_ms else None
    
    # Logic for badges and display
    path_display = s.decision_path.upper() if s.decision_path else ""
    if not path_display and not s.response_text:
         # "No Response" implied if no path and no text, 
         # but actually "No Response" filter maps to decision_path IS NULL
         pass

    return {
        "event_id": s.event_id,
        "timestamp": ts,
        "time_relative": format_relative_time(ts),
        "source": s.source,
        "raw_text": s.raw_text,
        "decision_path": path_display,
        "matched_heuristic_id": s.matched_heuristic_id,
        "matched_heuristic_condition": s.matched_heuristic_condition,
        "response_text": s.response_text,
    }


def _proto_detail_to_dict(d) -> dict:
    """Convert a memory_pb2.ResponseDetail proto to template-ready dict."""
    ts = datetime.fromtimestamp(d.timestamp_ms / 1000, tz=timezone.utc) if d.timestamp_ms else None
    
    return {
        "event_id": d.event_id,
        "timestamp": ts,
        "time_relative": format_relative_time(ts),
        "source": d.source,
        "raw_text": d.raw_text,
        "decision_path": d.decision_path.upper() if d.decision_path else "",
        "matched_heuristic_id": d.matched_heuristic_id,
        "matched_heuristic_condition": d.matched_heuristic_condition,
        "matched_heuristic_confidence": f"{d.matched_heuristic_confidence:.2f}" if d.matched_heuristic_confidence else "",
        "llm_prompt_text": d.llm_prompt_text,
        "response_text": d.response_text,
        "fire_id": d.fire_id,
        "feedback_source": d.feedback_source,
        "outcome": d.outcome,
    }


@router.get("/responses")
async def list_responses(
    request: Request, 
    decision_path: Optional[str] = None, 
    source: Optional[str] = None, 
    search: Optional[str] = None,
    limit: int = 50, 
    offset: int = 0
):
    """List event responses for the Response tab."""
    stub = env.memory_stub()
    if not stub:
        # Return empty list or error indicator in template if no stub
        return templates.TemplateResponse(request, "components/response.html", {
            "responses": [], 
            "error": "Proto stubs not available"
        })

    try:
        # Map frontend filter values to what gRPC expects if needed
        # Frontend passes "heuristic", "llm", "heuristic_fallback" directly
        # "timed_out" and "no_response" are handled by specific combinations in backend/DB logic
        # but the prompt says "Timed Out filter maps to: WHERE decision_path = 'llm' AND response_text IS NULL"
        # The prompt says: "Dashboard route calls ListResponses gRPC."
        # The gRPC request has `decision_path` string field.
        # If the frontend passes specialized filters like "timed_out", the gRPC service (Stream A) 
        # must handle them, or the dashboard needs to translate. 
        # "Stream A handles this" implies the gRPC service might handle the filtering logic 
        # or expects specific values.
        # However, looking at the proto definition in prompt: `string decision_path = 1;`
        # It's safest to pass the parameter through and let Memory service handle it, 
        # matching "Stream A handles this".
        
        req_kwargs = {
            "limit": limit,
            "offset": offset,
            "decision_path": decision_path or "",
            "source": source or "",
            "search": search or "",
        }
        
        resp = await stub.ListResponses(memory_pb2.ListResponsesRequest(**req_kwargs))
        
        if resp.error:
            logger.error("ListResponses gRPC error", error=resp.error)
            return templates.TemplateResponse(request, "components/response.html", {
                "responses": [],
                "error": resp.error
            })

        responses = [_proto_summary_to_dict(s) for s in resp.responses]
        
        # If HTMX request for just rows (e.g. search/filter), return rows only?
        # The prompt says "Returns HTMX-compatible HTML (template response), same pattern as events.py list_events()"
        # list_events returns components/lab.html (full tab).
        # But for updates/filters, we might want just rows.
        # events.py has `list_event_rows`.
        # I'll stick to returning the full component for the main route, 
        # and maybe add a rows-only route if needed, or handle it via header check.
        # For now, following `list_events`, I return `components/response.html`.
        
        if request.headers.get("HX-Request"):
            # Check if we are targeting the list container specifically
            # Actually `events.py` separates `list_events` (full tab) and `list_event_rows` (rows).
            # I should probably do the same if I want efficient filtering updates without reloading the toolbar.
            # But the prompt says "New router ... GET /api/responses ... Returns HTMX-compatible HTML ... same pattern as events.py list_events()".
            # This implies the main route returns the full component structure (with data).
            pass

        return templates.TemplateResponse(request, "components/response.html", {
            "responses": responses,
            "filters": {
                "decision_path": decision_path,
                "source": source,
                "search": search
            }
        })

    except grpc.RpcError as e:
        logger.error("ListResponses gRPC call failed", error=str(e))
        return templates.TemplateResponse(request, "components/response.html", {
            "responses": [],
            "error": f"gRPC error: {e.code().name}"
        })


@router.get("/responses/rows")
async def list_response_rows(
    request: Request,
    decision_path: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Return just the response table rows (for htmx filtering/pagination)."""
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        req_kwargs = {
            "limit": limit,
            "offset": offset,
            "decision_path": decision_path or "",
            "source": source or "",
            "search": search or "",
        }
        resp = await stub.ListResponses(memory_pb2.ListResponsesRequest(**req_kwargs))
        
        if resp.error:
            return HTMLResponse(f'<div class="p-4 text-red-500">Error: {resp.error}</div>')

        responses = [_proto_summary_to_dict(s) for s in resp.responses]
        
        # We need a partial template for rows. 
        # I'll assume I can define a macro or a sub-template.
        # For now, I'll render the loop in `components/response_rows.html`.
        return templates.TemplateResponse(request, "components/response_rows.html", {"responses": responses})

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')


@router.get("/responses/{event_id}")
async def get_response_detail(request: Request, event_id: str):
    """Get full drill-down detail for an event."""
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        resp = await stub.GetResponseDetail(memory_pb2.GetResponseDetailRequest(event_id=event_id))
        
        if resp.error:
             return HTMLResponse(f'<div class="p-4 text-red-500">Error: {resp.error}</div>')

        detail = _proto_detail_to_dict(resp.detail)
        return templates.TemplateResponse(request, "components/response_detail.html", {"detail": detail})

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')


class BulkDeleteRequest(BaseModel):
    event_ids: List[str]


@router.delete("/responses")
async def bulk_delete_responses(request: Request, body: BulkDeleteRequest):
    """Bulk delete responses by event_id."""
    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"detail": "Proto stubs not available"}, status_code=500)

    try:
        resp = await stub.DeleteResponses(memory_pb2.DeleteResponsesRequest(event_ids=body.event_ids))
        if resp.error:
            logger.error("DeleteResponses gRPC error", error=resp.error)
            return JSONResponse({"detail": resp.error}, status_code=400)
        logger.info("bulk_delete_responses success", deleted=resp.deleted_count, requested=len(body.event_ids))
        return JSONResponse({"deleted": resp.deleted_count})
    except grpc.RpcError as e:
        logger.error("DeleteResponses gRPC call failed", error=str(e))
        return JSONResponse({"detail": f"gRPC error: {e.code().name}"}, status_code=500)
