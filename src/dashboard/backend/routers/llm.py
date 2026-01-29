"""LLM/Ollama router — status, test prompt, warm model."""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.env import PROJECT_ROOT

router = APIRouter(prefix="/api/llm")


def _get_ollama_config() -> dict:
    """Read Ollama config from .env (same logic as _gladys.py)."""
    env_path = PROJECT_ROOT / ".env"
    env_vars = {}

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()

    # Resolve named endpoint
    endpoint_name = os.environ.get("OLLAMA_ENDPOINT", env_vars.get("OLLAMA_ENDPOINT", "")).strip().upper()

    if endpoint_name:
        url = os.environ.get(f"OLLAMA_ENDPOINT_{endpoint_name}",
                             env_vars.get(f"OLLAMA_ENDPOINT_{endpoint_name}", ""))
        model = os.environ.get(f"OLLAMA_ENDPOINT_{endpoint_name}_MODEL",
                               env_vars.get(f"OLLAMA_ENDPOINT_{endpoint_name}_MODEL", ""))
    else:
        url = os.environ.get("OLLAMA_URL", env_vars.get("OLLAMA_URL", ""))
        model = os.environ.get("OLLAMA_MODEL", env_vars.get("OLLAMA_MODEL", ""))

    return {"endpoint": endpoint_name.lower() if endpoint_name else None, "url": url, "model": model}


def _ollama_request(url: str, path: str, data: dict = None, timeout: int = 10) -> tuple[int, dict]:
    """Make an HTTP request to Ollama. Returns (status_code, json_body)."""
    full_url = f"{url.rstrip('/')}{path}"
    try:
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(full_url, data=body,
                                        headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(full_url)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)}
    except urllib.error.URLError as e:
        return 0, {"error": f"unreachable: {e.reason}"}
    except Exception as e:
        return 0, {"error": str(e)}


@router.get("/status")
async def llm_status():
    """Get Ollama connection status, loaded models."""
    config = _get_ollama_config()
    if not config["url"]:
        return JSONResponse({
            "status": "not_configured",
            "endpoint": None, "url": None, "model": None,
            "loaded_models": [],
        })

    # Check connectivity + list models
    status_code, tags = _ollama_request(config["url"], "/api/tags")
    if status_code != 200:
        return JSONResponse({
            "status": "unreachable",
            **config,
            "loaded_models": [],
            "error": tags.get("error", ""),
        })

    available_models = [m.get("name", "") for m in tags.get("models", [])]

    # Check which model is currently loaded
    ps_code, ps_data = _ollama_request(config["url"], "/api/ps")
    loaded = []
    if ps_code == 200:
        loaded = [m.get("name", "") for m in ps_data.get("models", [])]

    return JSONResponse({
        "status": "connected",
        **config,
        "available_models": available_models,
        "loaded_models": loaded,
    })


@router.post("/test")
async def llm_test(request: Request):
    """Send a test prompt to Ollama."""
    body = await request.json()
    prompt = body.get("prompt", "Say hello in one sentence.")

    config = _get_ollama_config()
    if not config["url"] or not config["model"]:
        return JSONResponse({"error": "Ollama not configured"}, status_code=503)

    status_code, result = _ollama_request(
        config["url"], "/api/generate",
        data={"model": config["model"], "prompt": prompt, "stream": False},
        timeout=60,
    )

    if status_code == 200:
        return JSONResponse({
            "response": result.get("response", ""),
            "model": config["model"],
            "total_duration_ms": result.get("total_duration", 0) / 1_000_000,
        })
    return JSONResponse({"error": result.get("error", "Request failed")}, status_code=502)


@router.post("/warm")
async def llm_warm():
    """Keep the model loaded by sending a minimal request with keep_alive."""
    config = _get_ollama_config()
    if not config["url"] or not config["model"]:
        return JSONResponse({"error": "Ollama not configured"}, status_code=503)

    status_code, result = _ollama_request(
        config["url"], "/api/generate",
        data={
            "model": config["model"],
            "prompt": "",
            "stream": False,
            "keep_alive": "10m",
        },
        timeout=30,
    )

    return JSONResponse({
        "success": status_code == 200,
        "model": config["model"],
    })
