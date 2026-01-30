"""GLADyS Dashboard V2 — FastAPI backend."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.env import PROJECT_ROOT
from backend.routers import cache, config, events, fires, heuristics, llm, logs, memory, metrics, services

app = FastAPI(title="GLADyS Dashboard V2")

# Setup templates and static files
FRONTEND_DIR = PROJECT_ROOT / "src" / "services" / "dashboard" / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

# Register routers
app.include_router(services.router)
app.include_router(events.router)
app.include_router(metrics.router)
app.include_router(heuristics.router)
app.include_router(cache.router)
app.include_router(llm.router)
app.include_router(logs.router)
app.include_router(config.router)
app.include_router(memory.router)
app.include_router(fires.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/components/lab")
async def get_lab(request: Request):
    """Initial lab tab load — delegates to events list_events for real data."""
    return await events.list_events(request)


@app.get("/api/components/{name}")
async def get_component(name: str, request: Request):
    """Load a tab component partial."""
    return templates.TemplateResponse(f"components/{name}.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
