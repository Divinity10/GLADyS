"""Services REST API — start/stop/restart."""

import asyncio
import io
from contextlib import redirect_stdout

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.env import env

from _local_backend import LocalBackend
from _docker_backend import DockerBackend

router = APIRouter(prefix="/api/services")

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


def _do_service_action(action: str, name: str) -> tuple[bool, str]:
    """Execute a service action, capturing stdout."""
    backend = _get_backend()
    backend_names = _resolve_names(name)

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
