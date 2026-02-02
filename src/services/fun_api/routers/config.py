"""Config router — environment switching, app config display."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.env import env, ENV_CONFIGS

router = APIRouter(prefix="/api/config")


@router.get("")
async def get_config():
    """Return current app configuration."""
    cfg = env.config
    return JSONResponse({
        "environment": env.mode,
        "orchestrator": cfg.orchestrator,
        "memory": cfg.memory,
        "salience": cfg.salience,
        "executive": cfg.executive,
        "db_port": cfg.db_port,
    })


@router.get("/environment")
async def get_environment():
    """Return current environment mode."""
    return JSONResponse({"mode": env.mode})


@router.put("/environment")
async def set_environment(request: Request):
    """Switch environment (local/docker)."""
    body = await request.json()
    mode = body.get("mode", "")

    if mode not in ENV_CONFIGS:
        return JSONResponse({"error": f"Unknown mode: {mode}. Use 'local' or 'docker'."}, status_code=400)

    await env.switch(mode)
    return JSONResponse({"mode": env.mode, "success": True})
