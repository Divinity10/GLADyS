"""Heuristics router — HTMX/HTML endpoints for Pattern A rendering.

This router returns server-rendered HTML for htmx to swap into the DOM.
The JSON API for programmatic access remains in fun_api/routers/heuristics.py.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import grpc
import structlog
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT, env, PROTOS_AVAILABLE

logger = structlog.get_logger()

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api")
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


def _ms_to_iso(ms: int) -> str | None:
    """Convert epoch milliseconds to ISO 8601 string, or None if 0."""
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _heuristic_match_to_dict(match) -> dict:
    """Convert HeuristicMatch proto to template-ready dict.

    IMPORTANT: QueryHeuristics returns HeuristicMatch wrappers, not raw Heuristic.
    Access the heuristic via match.heuristic.
    """
    h = match.heuristic
    return {
        "id": h.id,
        "name": h.name,
        "condition_text": h.condition_text,
        "effects_json": h.effects_json,
        "confidence": h.confidence,
        "origin": h.origin,
        "origin_id": h.origin_id,
        # Proto doesn't have 'active' field — DB has 'frozen' (inverted).
        # Use fallback until proto exposes it.
        "active": getattr(h, "active", True) if hasattr(h, "active") else True,
        "fire_count": h.fire_count,
        "success_count": h.success_count,
        # Convert timestamps to ISO strings
        "created_at": _ms_to_iso(h.created_at_ms),
        "updated_at": _ms_to_iso(h.updated_at_ms),
    }


@router.get("/heuristics/rows")
async def list_heuristics_rows(
    request: Request,
    origin: Optional[str] = None,
    active: Optional[str] = None,  # "all", "active", "inactive"
    search: Optional[str] = None,
):
    """Return rendered heuristic rows for htmx."""
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        # Use QueryHeuristics with permissive params to list all
        # NOTE: There is no ListHeuristics RPC — this is the workaround
        resp = await stub.QueryHeuristics(memory_pb2.QueryHeuristicsRequest(
            min_confidence=0.0,
            limit=200,
        ))

        # resp.matches contains HeuristicMatch wrappers with .heuristic field
        heuristics = [_heuristic_match_to_dict(m) for m in resp.matches]

        # Server-side filtering
        if origin:
            heuristics = [h for h in heuristics if h["origin"] == origin]
        if active == "active":
            heuristics = [h for h in heuristics if h["active"]]
        elif active == "inactive":
            heuristics = [h for h in heuristics if not h["active"]]
        if search:
            q = search.lower()
            heuristics = [h for h in heuristics if
                q in (h["condition_text"] or "").lower() or
                q in (h["id"] or "").lower()]

        return templates.TemplateResponse(request, "components/heuristics_rows.html", {
            "heuristics": heuristics
        })

    except grpc.RpcError as e:
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')


@router.post("/heuristics/create")
async def create_heuristic(
    request: Request,
    condition_text: str = Form(...),
    response_text: str = Form(...),
    confidence: int = Form(80),  # Percentage 0-100
):
    """Create a new heuristic via gRPC StoreHeuristic.

    Returns updated heuristics list HTML (for htmx swap).
    """
    stub = env.memory_stub()
    if not stub:
        return HTMLResponse('<div class="p-4 text-red-500">Proto stubs not available</div>')

    try:
        # Generate new UUID for the heuristic
        heuristic_id = str(uuid.uuid4())

        # Build the effects_json with 'message' field (canonical format per grpc_server.py)
        effects_json = json.dumps({"message": response_text})

        # Convert percentage to 0.0-1.0 confidence
        confidence_float = max(0.0, min(1.0, confidence / 100.0))

        # Create the heuristic proto
        heuristic = memory_pb2.Heuristic(
            id=heuristic_id,
            name=f"user-{heuristic_id[:8]}",  # Auto-generated name
            condition_text=condition_text,
            effects_json=effects_json,
            confidence=confidence_float,
            origin="user",
        )

        resp = await stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
            heuristic=heuristic,
            generate_embedding=True,
        ))

        if not resp.success:
            logger.error("create_heuristic failed", error=resp.error)
            return HTMLResponse(f'<div class="p-4 text-red-500">Error: {resp.error}</div>')

        logger.info("create_heuristic success", heuristic_id=heuristic_id)

        # Return refreshed heuristics list
        return await list_heuristics_rows(request)

    except grpc.RpcError as e:
        logger.error("create_heuristic gRPC error", error=str(e))
        return HTMLResponse(f'<div class="p-4 text-red-500">gRPC Error: {e.code().name}</div>')
