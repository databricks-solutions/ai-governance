"""FastAPI entry point for the AI Governance Workshop app."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.db import init_schema, pool
from server.routes import workshop

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30.0)
    try:
        init_schema()
    except Exception as e:
        log.warning("Progress schema init skipped: %s", e)
    yield
    pool.close()


app = FastAPI(title="AI Governance Workshop", lifespan=lifespan)
app.include_router(workshop.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


_frontend = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(_frontend):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = os.path.join(_frontend, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_frontend, "index.html"))
