"""Metrics router — aggregated numbers for the metrics strip."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT, env

import _db

router = APIRouter(prefix="/api")

FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


@router.get("/metrics")
async def get_metrics(request: Request):
    """Fetch aggregated metrics from DB + cache stats."""
    metrics = {
        "total_events": 0,
        "active_heuristics": 0,
        "llm_calls": 0,
        "fast_path_rate": 0,
        "cache_hit_rate": 0,
    }

    try:
        dsn = env.get_db_dsn()
        db_metrics = _db.get_metrics(dsn)
        metrics["total_events"] = db_metrics["total_events"]
        metrics["active_heuristics"] = db_metrics["active_heuristics"]
        metrics["llm_calls"] = db_metrics["queued_events"]

        total = metrics["total_events"]
        llm = metrics["llm_calls"]
        fast = total - llm
        metrics["fast_path_rate"] = round((fast / total * 100) if total > 0 else 0)
    except Exception:
        pass

    # Cache hit rate from salience gateway
    try:
        stub = env.salience_stub()
        if stub:
            from gladys_orchestrator.generated import memory_pb2
            resp = stub.GetCacheStats(memory_pb2.GetCacheStatsRequest())
            total_lookups = resp.total_hits + resp.total_misses
            if total_lookups > 0:
                metrics["cache_hit_rate"] = round(resp.total_hits / total_lookups * 100)
    except Exception:
        pass

    return templates.TemplateResponse("components/metrics.html", {
        "request": request,
        "metrics": metrics,
    })
