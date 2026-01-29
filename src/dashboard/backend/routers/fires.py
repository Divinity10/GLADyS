"""Flight recorder router — heuristic fire history from DB.

Schema (heuristic_fires):
  id, heuristic_id, event_id, fired_at, outcome,
  feedback_source, feedback_at, episodic_event_id

Schema (heuristics):
  id, name, condition (JSONB), action (JSONB), confidence, ...
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.env import env

import _db

router = APIRouter(prefix="/api/fires")


@router.get("")
async def list_fires(outcome: str = None, limit: int = 25):
    """List recent heuristic fires from the flight recorder."""
    try:
        rows = _db.list_fires(env.get_db_dsn(), limit=limit, outcome=outcome)

        fires = []
        for row in rows:
            fires.append({
                "id": str(row["id"]),
                "heuristic_id": str(row["heuristic_id"]) if row["heuristic_id"] else "",
                "event_id": row["event_id"] or "",
                "fired_at": row["fired_at"].isoformat() if row["fired_at"] else None,
                "outcome": row["outcome"] or "unknown",
                "feedback_source": row["feedback_source"] or "",
                "heuristic_name": row["heuristic_name"] or "",
                "condition_text": row["condition_text"] or "",
                "confidence": float(row["confidence"]) if row["confidence"] is not None else 0.0,
            })

        return JSONResponse({"fires": fires, "count": len(fires)})

    except Exception as e:
        return JSONResponse({"fires": [], "count": 0, "error": str(e)})
