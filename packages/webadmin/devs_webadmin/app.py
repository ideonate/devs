"""FastAPI application for devs web admin."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api.routes import router as api_router

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Devs Web Admin",
    description="Web UI for managing devcontainers on a server",
    version="0.1.0",
)

app.include_router(api_router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
