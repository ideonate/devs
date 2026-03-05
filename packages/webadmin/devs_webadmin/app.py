"""FastAPI application for devs web admin."""

import hmac
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.requests import Request

from .api.routes import router as api_router

STATIC_DIR = Path(__file__).parent / "static"
ORIGIN_VERIFY_SECRET = os.environ.get("ORIGIN_VERIFY_SECRET", "")

app = FastAPI(
    title="Devs Web Admin",
    description="Web UI for managing devcontainers on a server",
    version="0.1.0",
)


@app.middleware("http")
async def verify_origin(request: Request, call_next):
    if ORIGIN_VERIFY_SECRET:
        header_value = request.headers.get("x-origin-verify", "")
        if not hmac.compare_digest(header_value, ORIGIN_VERIFY_SECRET):
            return PlainTextResponse(status_code=403, content="Forbidden")
    return await call_next(request)


app.include_router(api_router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
