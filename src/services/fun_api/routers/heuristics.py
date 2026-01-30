"""Heuristics router — CRUD via Memory Storage gRPC."""

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.env import env, PROTOS_AVAILABLE

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api/heuristics")


def _heuristic_to_dict(h) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "condition_text": h.condition_text,
        "effects_json": h.effects_json,
        "confidence": h.confidence,
        "origin": h.origin,
        "active": h.active if hasattr(h, "active") else True,
    }


@router.get("")
async def list_heuristics(sort: str = "confidence", order: str = "desc"):
    """List all heuristics from memory storage."""
    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)
    try:
        resp = stub.ListHeuristics(memory_pb2.ListHeuristicsRequest())
        items = [_heuristic_to_dict(h) for h in resp.heuristics]

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
        )
        resp = stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
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
        )
        resp = stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
            heuristic=h,
            generate_embedding=True,
        ))
        return JSONResponse({"id": resp.heuristic_id, "success": True})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.delete("/{heuristic_id}")
async def delete_heuristic(heuristic_id: str):
    """Delete a heuristic."""
    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        stub.DeleteHeuristic(memory_pb2.DeleteHeuristicRequest(heuristic_id=heuristic_id))
        return JSONResponse({"success": True})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.delete("")
async def bulk_delete_heuristics(request: Request):
    """Bulk delete heuristics."""
    body = await request.json()
    ids = body.get("ids", [])

    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    deleted = []
    errors = []
    for hid in ids:
        try:
            stub.DeleteHeuristic(memory_pb2.DeleteHeuristicRequest(heuristic_id=hid))
            deleted.append(hid)
        except grpc.RpcError as e:
            errors.append({"id": hid, "error": e.code().name})

    return JSONResponse({"deleted": deleted, "errors": errors})
