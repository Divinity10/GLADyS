"""Logs router — service log file retrieval."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(prefix="/api/logs")

LOG_DIR = Path.home() / ".gladys" / "logs"


@router.get("/{service}")
async def get_logs(service: str, tail: int = 100):
    """Read tail of a service's log file."""
    log_file = LOG_DIR / f"{service}.log"

    if not log_file.exists():
        return JSONResponse({
            "service": service,
            "lines": [],
            "error": "No log file found. Service may not have started yet.",
        })

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if tail > 0:
            lines = lines[-tail:]

        return JSONResponse({
            "service": service,
            "lines": [line.rstrip() for line in lines],
            "total_lines": len(lines),
        })
    except Exception as e:
        return JSONResponse({"service": service, "lines": [], "error": str(e)})
