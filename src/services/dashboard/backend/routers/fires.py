"""Fires router — HTMX/HTML endpoints for Pattern A rendering.

Uses gRPC to Memory service (NOT direct DB access).
"""

from datetime import datetime, timezone
from typing import Optional

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT, env, PROTOS_AVAILABLE

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api")
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


def _fire_to_dict(fire) -> dict:
    """Convert HeuristicFire proto to template-ready dict."""
    fired_at = None
    if fire.fired_at_ms:
        fired_at = datetime.fromtimestamp(fire.fired_at_ms / 1000, tz=timezone.utc).isoformat()

    return {
        "id": fire.id,
        "heuristic_id": fire.heuristic_id,
        "heuristic_name": fire.heuristic_name or (fire.heuristic_id[:8] if fire.heuristic_id else ""),
        "event_id": fire.event_id,
        "condition_text": fire.condition_text,
        "outcome": fire.outcome or "unknown",
        "feedback_source": fire.feedback_source or "",
        "confidence": fire.confidence,
        "fired_at": fired_at,
    }


@router.get("/fires/rows")
async def list_fires_rows(
    request: Request,
    outcome: Optional[str] = None,  # all, success, failure, pending
    search: Optional[str] = None,
):
    """Return rendered fire rows for htmx."""
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Memory service not available</div>')

    try:
        # Map "all" to no filter
        outcome_filter = outcome if outcome and outcome != "all" else ""

        resp = await stub.ListFires(memory_pb2.ListFiresRequest(
            outcome=outcome_filter,
            limit=100,
        ))

        fires = [_fire_to_dict(f) for f in resp.fires]

        # Server-side search filtering (client convenience)
        if search:
            q = search.lower()
            fires = [f for f in fires if
                q in (f.get("heuristic_name") or "").lower() or
                q in (f.get("condition_text") or "").lower() or
                q in (f.get("event_id") or "").lower()]

        return templates.TemplateResponse(request, "components/learning_rows.html", {
            "fires": fires
        })

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')
