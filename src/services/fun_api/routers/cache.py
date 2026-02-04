"""Cache router — stats, list, flush, evict via Salience Gateway gRPC."""

import grpc
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.env import env, PROTOS_AVAILABLE

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api/cache")


@router.get("/stats")
async def cache_stats():
    stub = env.salience_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)
    try:
        resp = await stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
        return JSONResponse({
            "current_size": resp.current_size,
            "max_capacity": resp.max_capacity,
            "total_hits": resp.total_hits,
            "total_misses": resp.total_misses,
            "hit_rate": round(resp.total_hits / max(resp.total_hits + resp.total_misses, 1) * 100, 1),
        })
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.get("/entries")
async def cache_entries():
    stub = env.salience_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)
    try:
        resp = await stub.ListCachedHeuristics(memory_pb2.ListCachedHeuristicsRequest())
        entries = []
        for h in resp.heuristics:
            entries.append({
                "heuristic_id": h.heuristic_id,
                "name": h.name,
                "hit_count": h.hit_count,
                "cached_at_unix": h.cached_at_unix,
                "last_hit_unix": h.last_hit_unix,
            })
        return JSONResponse({"entries": entries, "count": len(entries)})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)


@router.post("/flush")
async def cache_flush():
    stub = env.salience_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)
    try:
        resp = await stub.FlushCache(memory_pb2.FlushCacheRequest())
        return JSONResponse({"flushed": resp.entries_flushed})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)
