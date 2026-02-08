"""Heuristics router — CRUD via Memory Storage gRPC + direct DB delete."""

from datetime import datetime, timezone

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.env import env, PROTOS_AVAILABLE
from gladys_client import db as _db

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api/heuristics")


def _ms_to_iso(ms: int) -> str | None:
    """Convert epoch milliseconds to ISO 8601 string, or None if 0."""
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _heuristic_to_dict(h) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "condition_text": h.condition_text,
        "effects_json": h.effects_json,
        "confidence": h.confidence,
        "origin": h.origin,
        "source": getattr(h, "source", ""),
        "active": h.active if hasattr(h, "active") else True,
        "fire_count": getattr(h, "fire_count", 0),
        "success_count": getattr(h, "success_count", 0),
        "created_at": _ms_to_iso(getattr(h, "created_at_ms", 0)),
        "updated_at": _ms_to_iso(getattr(h, "updated_at_ms", 0)),
    }


@router.get("")
async def list_heuristics(sort: str = "confidence", order: str = "desc"):
    """List all heuristics from memory storage."""
    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)
    try:
        resp = await stub.QueryHeuristics(memory_pb2.QueryHeuristicsRequest(
            min_confidence=0.0, limit=200,
        ))
        items = [_heuristic_to_dict(m.heuristic) for m in resp.matches]

        reverse = order == "desc"
        if sort in ("confidence", "name", "origin"):
            items.sort(key=lambda x: x.get(sort, ""), reverse=reverse)

        return JSONResponse({"heuristics": items, "count": len(items)})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.post("")
async def create_heuristic(request: Request):
    """Create a new heuristic."""
    body = await request.json()

    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        h = memory_pb2.Heuristic(
            name=body.get("name", ""),
            condition_text=body.get("condition_text", ""),
            effects_json=body.get("effects_json", "{}"),
            confidence=body.get("confidence", 0.5),
            origin=body.get("origin", "manual"),
            source=body.get("source", ""),
        )
        resp = await stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
            heuristic=h,
            generate_embedding=True,
        ))
        return JSONResponse({"id": resp.heuristic_id, "success": True})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.put("/{heuristic_id}")
async def update_heuristic(heuristic_id: str, request: Request):
    """Update a heuristic."""
    body = await request.json()

    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        h = memory_pb2.Heuristic(
            id=heuristic_id,
            name=body.get("name", ""),
            condition_text=body.get("condition_text", ""),
            effects_json=body.get("effects_json", "{}"),
            confidence=body.get("confidence", 0.5),
            origin=body.get("origin", "manual"),
            source=body.get("source", ""),
        )
        resp = await stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
            heuristic=h,
            generate_embedding=True,
        ))
        return JSONResponse({"id": resp.heuristic_id, "success": True})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.delete("/{heuristic_id}")
async def delete_heuristic(heuristic_id: str):
    """Delete a heuristic via direct DB access (no gRPC DeleteHeuristic RPC exists)."""
    try:
        deleted = _db.delete_heuristic(env.get_db_dsn(), heuristic_id)
        if deleted:
            return JSONResponse({"success": True})
        return JSONResponse({"error": "Heuristic not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("")
async def bulk_delete_heuristics(request: Request):
    """Bulk delete heuristics."""
    body = await request.json()
    ids = body.get("ids", [])

    deleted = []
    errors = []
    for hid in ids:
        try:
            if _db.delete_heuristic(env.get_db_dsn(), hid):
                deleted.append(hid)
            else:
                errors.append({"id": hid, "error": "not found"})
        except Exception as e:
            errors.append({"id": hid, "error": str(e)})

    return JSONResponse({"deleted": deleted, "errors": errors})
