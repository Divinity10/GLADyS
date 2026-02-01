"""GLADyS Dashboard V2 — FastAPI backend."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT

# Dashboard HTMX routers (return HTML partials)
from backend.routers import events, metrics, services

# FUN API REST/JSON routers
from fun_api.routers import (
    cache,
    config,
    fires,
    heuristics,
    llm,
    logs,
    memory,
)
from fun_api.routers import events as fun_events
from fun_api.routers import services as fun_services

app = FastAPI(title="GLADyS Dashboard V2")

# Setup templates and static files
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

# Register dashboard HTMX routers
app.include_router(services.router)
app.include_router(events.router)
app.include_router(metrics.router)

# Register FUN API REST/JSON routers
app.include_router(heuristics.router)
app.include_router(cache.router)
app.include_router(llm.router)
app.include_router(logs.router)
app.include_router(config.router)
app.include_router(memory.router)
app.include_router(fires.router)
app.include_router(fun_events.router)
app.include_router(fun_services.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/components/lab")
async def get_lab(request: Request):
    """Initial lab tab load — delegates to events list_events for real data."""
    return await events.list_events(request)


@app.get("/api/components/{name}")
async def get_component(name: str, request: Request):
    """Load a tab component partial."""
    return templates.TemplateResponse(request, f"components/{name}.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
