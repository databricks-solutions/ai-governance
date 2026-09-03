"""FastAPI app for Intelligent AI FinOps.

Serves the built React frontend (./dist) as static files and exposes /api.
Demo mode synthesises realistic numbers so the app runs offline; live mode
(FINOPS_DEMO_MODE=false) has Compare call real Model Serving (FMAPI). The
engines live in the sibling modules: compare, gateway, judge, models, pipeline.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import compare, gateway, judge, models, optimize, pipeline
from .appconfig import load_config

app = FastAPI(title="Intelligent AI FinOps")


class GatewayIn(BaseModel):
    models: list[str]  # 2-3 candidate model ids the customer picked
    features: list[str] = []  # enabled governance features
    complexity: int | None = None  # predefined question complexity
    prompt: str | None = None  # or a free-text question to classify
    budget: dict | None = None  # optional {applied, consumedPct, capUsd, downgradeAction, openOnlyAction}
    bands: list[dict] | None = None  # user-defined complexity bands [{label, min, max, tier}]
    policy: dict | None = None  # routing policy mode + free text {mode: "bands"|"criteria", text}


class JudgeIn(BaseModel):
    prompt: str
    answer: str


class OptimizeIn(BaseModel):
    prompt: str
    model: str | None = None  # optional optimizer model; defaults to a frontier model

# SSE responses must not be buffered by any proxy in front of the app.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_DIST = Path(__file__).resolve().parent.parent / "dist"


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    """Curated model registry (with real DBU-derived prices), policy, flags (§4)."""
    cfg = load_config()
    return JSONResponse({**cfg, "models": models.registry_dicts()})


@app.get("/api/compare/lane")
def compare_lane(prompt: str, modelId: str, judgeModel: str | None = None):  # noqa: N803 - query param names match client
    """Stream one Compare lane as SSE (§6.1). The client opens one per lane."""
    demo = load_config()["demoMode"]
    return StreamingResponse(
        compare.stream_lane(modelId, prompt, demo=demo, judge_model=judgeModel),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/api/pipeline/meta")
def pipeline_meta():
    """Question bank + Gateway feature list for the Context-routing tab."""
    return JSONResponse({"questions": pipeline.QUESTIONS, "features": gateway.FEATURES})


@app.post("/api/gateway/run")
def gateway_run(body: GatewayIn):
    """Route a question over the customer's selected models (the Gateway box).
    Live mode calls the chosen model for a real answer + judge score; demo mode
    synthesises so it runs offline."""
    return JSONResponse(gateway.run(body.models, body.features, complexity=body.complexity,
                                    prompt=body.prompt, budget=body.budget,
                                    bands=body.bands, policy=body.policy,
                                    demo=load_config()["demoMode"]))


@app.post("/api/optimize")
def optimize_prompt(body: OptimizeIn):
    """Rewrite a prompt into a sharper one before the three lanes run on it.
    Demo mode rewrites deterministically (offline); live mode uses a real model."""
    demo = load_config()["demoMode"]
    return JSONResponse(optimize.optimize_prompt(body.prompt, demo=demo, model_id=body.model))


@app.post("/api/judge")
def judge_answer(body: JudgeIn):
    """Score one answer 0–10 (live mode); logs the run to MLflow (§7). In demo
    mode per-lane scores are synthesised, so the client only calls this live."""
    if load_config()["demoMode"]:
        return JSONResponse({"score": None, "note": "judging synthesised in demo mode"})
    return JSONResponse({"score": judge.score(body.prompt, body.answer)})


# Static frontend last so /api/* takes precedence. Guard so `uvicorn` still
# boots before the first `npm run build` (dist may not exist yet in dev).
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
