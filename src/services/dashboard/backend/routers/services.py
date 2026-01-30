"""Services router — health checks, start/stop/restart.

Imports LocalBackend/DockerBackend directly instead of shelling out.
"""

import asyncio
import io
import sys
from contextlib import redirect_stdout

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT, env

# Import admin script modules directly (scripts/ is on sys.path via env.py)
from _local_backend import LocalBackend
from _docker_backend import DockerBackend
from _gladys import is_port_open

router = APIRouter(prefix="/api/services")

FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))

# Map dashboard service names to backend service names
DASHBOARD_TO_BACKEND = {
    "orchestrator": ["orchestrator"],
    "memory": ["memory-python"],
    "salience": ["memory-rust"],
    "executive": ["executive-stub"],
    "all": ["orchestrator", "memory-python", "memory-rust", "executive-stub"],
}


def _get_backend():
    """Return the right backend for the current environment."""
    if env.mode == "docker":
        return DockerBackend()
    return LocalBackend()


def _resolve_names(name: str) -> list[str]:
    """Map dashboard name to backend service name(s)."""
    return DASHBOARD_TO_BACKEND.get(name, [name])


def _check_health_one(service: dict) -> str:
    """Check one service's health. Returns color string."""
    backend = _get_backend()
    # Map dashboard name to backend name
    backend_names = _resolve_names(service["name"])
    backend_name = backend_names[0]

    # Quick port check first
    if not is_port_open(service["host"], service["port"]):
        return "gray"

    try:
        health = backend.get_service_health(backend_name, detailed=False)
        status = health.get("status", "UNKNOWN")
        return {"HEALTHY": "green", "DEGRADED": "yellow", "UNHEALTHY": "red"}.get(status, "gray")
    except Exception:
        return "gray"


@router.get("/health")
async def get_health(request: Request):
    """Check all service health, return sidebar partial."""
    services = env.services_list()

    loop = asyncio.get_event_loop()
    checks = [loop.run_in_executor(None, _check_health_one, s) for s in services]
    colors = await asyncio.gather(*checks)

    for s, color in zip(services, colors):
        s["status"] = color

    all_status = "green"
    for s in services:
        if s["status"] == "red":
            all_status = "red"
            break
        if s["status"] in ("gray", "yellow"):
            all_status = "yellow"

    return templates.TemplateResponse("components/sidebar.html", {
        "request": request,
        "services": services,
        "all_status": all_status,
    })


def _do_service_action(action: str, name: str) -> tuple[bool, str]:
    """Execute a service action, capturing stdout."""
    backend = _get_backend()
    backend_names = _resolve_names(name)

    # Capture print output from backend methods
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            if action == "start":
                success = backend.start_service(backend_names, wait=True)
            elif action == "stop":
                success = backend.stop_service(backend_names)
            elif action == "restart":
                success = backend.restart_service(backend_names)
            else:
                return False, f"Unknown action: {action}"
        return success, buf.getvalue().strip()
    except Exception as e:
        return False, f"{buf.getvalue().strip()}\nError: {e}"


@router.post("/{name}/start")
async def start_service(name: str):
    success, output = await asyncio.get_event_loop().run_in_executor(
        None, _do_service_action, "start", name
    )
    return JSONResponse({"success": success, "output": output})


@router.post("/{name}/stop")
async def stop_service(name: str):
    success, output = await asyncio.get_event_loop().run_in_executor(
        None, _do_service_action, "stop", name
    )
    return JSONResponse({"success": success, "output": output})


@router.post("/{name}/restart")
async def restart_service(name: str):
    success, output = await asyncio.get_event_loop().run_in_executor(
        None, _do_service_action, "restart", name
    )
    return JSONResponse({"success": success, "output": output})
