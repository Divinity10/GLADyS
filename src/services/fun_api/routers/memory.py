"""Memory probe router — similarity search."""

import grpc
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.env import env, PROTOS_AVAILABLE

if PROTOS_AVAILABLE:
    from gladys_orchestrator.generated import memory_pb2

router = APIRouter(prefix="/api/memory")


@router.post("/probe")
async def memory_probe(request: Request):
    """Run a similarity search against memory storage."""
    body = await request.json()
    query = body.get("query", "")
    limit = body.get("limit", 10)

    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)

    stub = env.memory_stub()
    if not stub:
        return JSONResponse({"error": "Proto stubs not available"}, status_code=503)

    try:
        resp = await stub.QuerySimilarHeuristics(memory_pb2.QuerySimilarHeuristicsRequest(
            query_text=query,
            limit=limit,
        ))
        results = []
        for match in resp.matches:
            results.append({
                "heuristic_id": match.heuristic.id,
                "name": match.heuristic.name,
                "condition_text": match.heuristic.condition_text,
                "confidence": match.heuristic.confidence,
                "similarity": match.similarity_score,
            })
        return JSONResponse({"results": results, "count": len(results)})
    except grpc.RpcError as e:
        return JSONResponse({"error": f"gRPC error: {e.code().name}"}, status_code=502)
