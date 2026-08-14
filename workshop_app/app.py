"""FastAPI entry point for the AI Governance Workshop app."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import config_problems
from server.routes import workshop
from server import store

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Surface config gaps loudly at boot: a blank catalog or warehouse otherwise shows up
    # as a puzzling per-step SQL error in front of the customer.
    for problem in config_problems():
        log.error("CONFIG: %s", problem)

    # The volume-backed progress store backs progress tracking only — the guidebook and the
    # Try-It tests do not need it. load() is best-effort by design (an empty/missing file on a
    # fresh deploy is normal), so a workshop with no saved progress is recoverable, whereas a
    # workshop with no app is not.
    store.load()
    yield


app = FastAPI(title="AI Governance Workshop", lifespan=lifespan)
app.include_router(workshop.router, prefix="/api")


@app.get("/api/health")
def health():
    problems = config_problems()
    return {"status": "ok" if not problems else "misconfigured", "config_problems": problems}


_frontend = os.path.realpath(os.path.join(os.path.dirname(__file__), "frontend", "dist"))
if os.path.exists(_frontend):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # An unmatched /api/* path is a real 404 (a typo or a removed endpoint), not an SPA
        # route. Falling through to index.html would return HTML with status 200, which the
        # frontend's JSON parser chokes on with an opaque "Unexpected token <" — worst during
        # a live workshop. Answer it honestly instead.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        # Resolve and confine to the build directory before serving. Starlette normalizes a
        # literal `../` but NOT a percent-encoded one (`..%2f`), which arrives here decoded
        # and would otherwise escape the directory and serve app source or host files.
        candidate = os.path.realpath(os.path.join(_frontend, full_path))
        inside = candidate == _frontend or candidate.startswith(_frontend + os.sep)
        if full_path and inside and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_frontend, "index.html"))
