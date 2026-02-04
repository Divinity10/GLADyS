"""Logs router — HTMX/HTML endpoints for Pattern A rendering.

This router returns server-rendered HTML for htmx to swap into the DOM.
The JSON API for programmatic access remains in fun_api/routers/logs.py.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT

router = APIRouter(prefix="/api")
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))

LOG_DIR = Path.home() / ".gladys" / "logs"


def _classify_log_line(line: str) -> str:
    """Return CSS class based on log level."""
    if "ERROR" in line or "CRITICAL" in line:
        return "error"
    elif "WARN" in line:
        return "warn"
    elif "INFO" in line:
        return "info"
    else:
        return "debug"


def _fetch_log_lines(service: str, tail: int) -> tuple[list[str], str | None]:
    """Read tail of a service's log file.

    Returns (lines, error_message).
    """
    log_file = LOG_DIR / f"{service}.log"

    if not log_file.exists():
        return [], "No log file found. Service may not have started yet."

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if tail > 0:
            lines = lines[-tail:]

        return [line.rstrip() for line in lines], None
    except Exception as e:
        return [], str(e)


@router.get("/logs/{service}/lines")
async def get_log_lines(
    request: Request,
    service: str,
    tail: int = 100,
):
    """Return rendered log lines for htmx."""
    lines, error = _fetch_log_lines(service, tail)

    if error:
        return templates.TemplateResponse(request, "components/logs_lines.html", {
            "lines": [],
            "count": 0,
            "error": error,
        })

    # Classify each line for styling
    classified_lines = [
        {"text": line, "level": _classify_log_line(line)}
        for line in lines
    ]

    return templates.TemplateResponse(request, "components/logs_lines.html", {
        "lines": classified_lines,
        "count": len(lines),
        "error": None,
    })
