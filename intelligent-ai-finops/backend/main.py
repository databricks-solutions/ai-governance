"""FastAPI app for Intelligent AI FinOps.

Serves the built React frontend (./dist) as static files and exposes /api.
Demo mode synthesises realistic numbers so the app runs offline; live mode
(FINOPS_DEMO_MODE=false) has Compare call real Model Serving (FMAPI). The
engines live in the sibling modules: compare, gateway, judge, models, pipeline.
"""
import time
from pathlib import Path

from fastapi import FastAPI, Request
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
    routerModel: str | None = None  # routing LLM that classifies complexity (live mode)
    fallback: dict | None = None  # app-level fallback {enabled, order: [model_id,...]}
    guardrails: dict | None = None  # app-layer guardrails {enabled, pii, mode: "block"|"mask", keywords}
    rateLimit: dict | None = None  # app-layer rate limit {enabled, perMin}
    access: dict | None = None  # ABAC access control {enabled, group, allowedTiers:[tier,...]}


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


@app.get("/api/cost/overview")
def cost_overview(days: int = 30):
    """V2: REAL cost/usage from Unity Catalog system tables, read via the warehouse as
    the App's service principal (needs the grants in V2_SETUP.md). Cached 5 min so the
    tab is snappy; warmed at startup so the first view doesn't wait on a cold scan."""
    from . import costcache
    return JSONResponse(costcache.overview(days))


@app.on_event("startup")
def _warm_cost_cache():
    """Warm the default (30-day) cost overview in the background at boot, so the first
    Cost-tab load is served from cache instead of paying the cold serverless-warehouse
    start + four system-table scans. Best-effort: failures are swallowed (the endpoint
    recomputes / falls back to demo on demand)."""
    import threading
    from . import costcache
    threading.Thread(target=lambda: costcache.overview(30), daemon=True).start()


@app.get("/api/coding-agents")
def coding_agents(days: int = 30):
    """Coding-agent cost tracker: per-harness (Claude Code / Codex / Cursor / SDKs)
    and per-developer spend, classified from system.ai_gateway.usage.user_agent and
    priced with the published DBU rate card. Real data; cached 5 min. The #1 Unity AI
    Gateway adoption motion. Returns {"source":"unavailable"} if system tables can't be
    read (app never hard-fails)."""
    from . import codingagents
    return JSONResponse(codingagents.overview(days))


@app.get("/api/reliability")
def reliability(days: int = 30):
    """Reliability & fallback observability from system.ai_gateway.usage
    routing_information.attempts: fallback fire rate, initial error rate, status
    breakdown (429/4xx/5xx), top failing destinations. Real data; cached 5 min."""
    from . import reliability as _rel
    return JSONResponse(_rel.overview(days))


@app.get("/api/governance/config")
def governance_config(models: str = ""):
    """V2: the LIVE per-endpoint AI Gateway config (usage tracking, rate limits,
    guardrails, inference tables, fallbacks) read via the SDK + cached in-process."""
    from . import governance
    from . import models as model_registry
    ids = [m for m in models.split(",") if m] or [m.id for m in model_registry.registry()]
    return JSONResponse(governance.configs(ids))


class GatewayUpdateIn(BaseModel):
    model: str          # serving-endpoint id
    patch: dict         # ai_gateway fields to set, e.g. {"rate_limits": [...]} or {"usage_tracking_config": {"enabled": true}}


@app.post("/api/governance/update")
def governance_update(body: GatewayUpdateIn, request: Request):
    """V2: WRITE the endpoint's AI Gateway config AS THE SIGNED-IN USER (Databricks Apps
    on-behalf-of-user). System pay-per-token endpoints are platform-managed - the app SP
    can't manage them, but a human admin can, so we execute the write with the user's
    forwarded token. Returns the refreshed live config + whether it ran as the user."""
    from . import governance
    user_token = request.headers.get("x-forwarded-access-token")
    try:
        cfg = governance.set_endpoint_gateway(body.model, body.patch, user_token=user_token)
        return JSONResponse({"ok": True, "config": cfg, "asUser": bool(user_token)})
    except Exception as e:  # noqa: BLE001 - surface a visible error, never hang
        return JSONResponse({"ok": False, "error": str(e)[:200], "asUser": bool(user_token)})


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
def gateway_run(body: GatewayIn, request: Request):
    """Route a question over the customer's selected models (the Gateway box).
    Live mode calls the chosen model for a real answer + judge score; demo mode
    synthesises so it runs offline. App-layer guardrails + rate limits are enforced
    here per the signed-in user (from the forwarded identity header)."""
    who = request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-preferred-username") or "you"
    return JSONResponse(gateway.run(body.models, body.features, complexity=body.complexity,
                                    prompt=body.prompt, budget=body.budget,
                                    bands=body.bands, policy=body.policy,
                                    router_model=body.routerModel, fallback=body.fallback,
                                    guardrails=body.guardrails, rate_limit=body.rateLimit,
                                    access=body.access, user=who,
                                    demo=load_config()["demoMode"]))


class FallbackPolicyIn(BaseModel):
    enabled: bool = True
    order: list[str] = []  # ordered serving-endpoint ids: primary first, then fallbacks


@app.get("/api/governance/fallback")
def get_fallback_policy():
    """The saved app-level fallback policy (durable in Lakebase; falls back to empty)."""
    from . import lakebase
    saved = lakebase.get("fallback_policy", max_age_s=10**9)  # no expiry - it's config, not a cache
    return JSONResponse(saved or {"enabled": True, "order": []})


@app.post("/api/governance/fallback")
def save_fallback_policy(body: FallbackPolicyIn):
    """Persist the admin's fallback policy to Lakebase so it survives restarts/replicas.
    The gateway enforces it at serve time (app-level failover). Degrades to in-memory
    only (returns saved:false) if Lakebase is unreachable."""
    from . import lakebase
    payload = {"enabled": body.enabled, "order": body.order}
    saved = lakebase.put("fallback_policy", payload)  # True only if the write landed
    return JSONResponse({"ok": True, "saved": saved, "policy": payload})


# ---- Real inference proxy: the app IS the gateway --------------------------
# `POST /v1/chat/completions` is OpenAI-compatible, so a customer points their
# existing OpenAI SDK at this app and every call is routed to the cheapest
# sufficient model, guardrailed, rate-limited, compressed, and served with a
# fallback chain. The extra `x_finops` field (+ x-finops-* headers) reports the
# routing decision, cost, and savings. `finops-auto` lets the router pick;
# a real endpoint id governs + passes through to that one endpoint.
class RouterPolicyIn(BaseModel):
    models: list[str] | None = None      # candidate serving-endpoint ids
    bands: list[dict] | None = None      # complexity bands [{label,min,max,tier}]
    policy: dict | None = None           # {mode:"bands"|"criteria", text|rules}
    routerModel: str | None = None       # routing LLM that classifies complexity
    guardrails: dict | None = None       # {enabled, pii, mode, keywords}
    rateLimit: dict | None = None        # {enabled, perMin}
    fallback: dict | None = None         # {enabled, order:[id,...]}
    optimize: dict | None = None         # {enabled, targetWords} output-shaping


@app.get("/api/gateway/policy")
def get_router_policy():
    """The saved server-side router policy that `finops-auto` uses (durable in
    Lakebase). Defaults to the full curated registry as candidates when unset."""
    from . import lakebase
    from . import models as reg
    saved = lakebase.get("router_policy", max_age_s=10 ** 9)
    return JSONResponse(saved or {"models": [m.id for m in reg.registry()], "bands": None, "policy": None})


@app.post("/api/gateway/policy")
def save_router_policy(body: RouterPolicyIn):
    """Persist the admin's router policy so `finops-auto` behaves the same across
    restarts/replicas. Degrades to in-memory only (saved:false) if Lakebase is down."""
    from . import lakebase
    payload = {k: getattr(body, k) for k in ("models", "bands", "policy", "routerModel",
                                             "guardrails", "rateLimit", "fallback", "optimize")
               if getattr(body, k) is not None}
    saved = lakebase.put("router_policy", payload)  # True only if the write landed
    return JSONResponse({"ok": True, "saved": saved, "policy": payload})


# ---- Admin gateway config (Context-routing tab) --------------------------
# The full admin-configured state for the Context-routing tab (auto-classifier
# on/off, the 3 category model picks, keyword criteria, governance ticks, and the
# per-request option toggles). Persisted to Lakebase so the USER persona - which
# only types a question - inherits exactly what the admin set. Stored as an opaque
# blob (the frontend owns the shape); degrades to in-memory only if Lakebase is down.
@app.get("/api/gateway/appconfig")
def get_app_config():
    from . import lakebase
    saved = lakebase.get("app_admin_config", max_age_s=10 ** 9)
    return JSONResponse(saved or {})


@app.post("/api/gateway/appconfig")
async def save_app_config(request: Request):
    from . import lakebase
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "expected a JSON object"}, status_code=400)
    saved = lakebase.put("app_admin_config", body)
    return JSONResponse({"ok": True, "saved": saved})


@app.get("/api/setup/readiness")
def setup_readiness():
    """Deployment readiness: green/red checks (warehouse, system tables, serving
    endpoints, embedding, Lakebase) + serving-endpoint auto-discovery, so a customer
    can self-diagnose standing V2 up in their own workspace."""
    from . import setup as _setup
    return JSONResponse(_setup.readiness())


@app.get("/api/tools/discover")
def tools_discover():
    """The agent tools the router prunes over: REAL Unity Catalog functions when
    FINOPS_TOOLS_CATALOG/SCHEMA are configured and reachable, else the sample set.
    Returns the catalog (name + description + params) and the source."""
    from . import tools as tools_mod
    cat, source = tools_mod.catalog()
    return JSONResponse({"source": source, "count": len(cat),
                         "tools": [{"name": t["name"], "description": t.get("description", ""),
                                    "params": list((t.get("parameters", {}).get("properties") or {}).keys())}
                                   for t in cat]})


@app.get("/api/models/discover")
def models_discover():
    """Which registry models are actually deployed here (routable), which are missing,
    and which live endpoints are unpriced (flagged, never given a fabricated price)."""
    from . import setup as _setup
    return JSONResponse(_setup.discover())


@app.get("/api/gateway/cache/stats")
def gateway_cache_stats():
    """Semantic-cache stats for the Gateway API tab: hits, misses, hit-rate, $ saved."""
    from . import semcache
    return JSONResponse(semcache.stats())


@app.post("/api/gateway/cache/clear")
def gateway_cache_clear():
    """Reset the semantic cache + its stats (demo control, so a fresh run starts clean)."""
    from . import semcache
    semcache.clear()
    return JSONResponse({"ok": True, **semcache.stats()})



@app.post("/v1/chat/completions")
async def openai_chat(request: Request):
    """OpenAI-compatible chat completions, routed + governed by the FinOps gateway.
    Point any OpenAI client here (base_url = this app + /v1). `model` is a real
    endpoint id (governed passthrough) or 'finops-auto' (the router picks). The
    response carries an extra `x_finops` receipt and x-finops-* headers."""
    import json

    from . import proxy
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON body", "type": "finops_gateway"}})
    messages = body.get("messages") or []
    requested_model = body.get("model")
    stream = bool(body.get("stream"))
    max_tokens = body.get("max_tokens")
    temperature = body.get("temperature", 0.0)
    options = body.get("finops") or {}  # non-standard extension: per-request candidate/policy override
    who = (request.headers.get("x-forwarded-email")
           or request.headers.get("x-forwarded-preferred-username") or "proxy-user")
    try:
        resp, finops = proxy.serve(messages, requested_model=requested_model, options=options,
                                   user=who, max_tokens=max_tokens, temperature=temperature)
    except proxy.ProxyError as e:
        return JSONResponse(status_code=e.status,
                            content={"error": {"message": e.message, "type": "finops_gateway", "code": e.code},
                                     "x_finops": e.finops})
    except Exception as e:  # noqa: BLE001 - never hang the client
        return JSONResponse(status_code=500, content={"error": {"message": str(e)[:200], "type": "finops_gateway"}})

    resp["x_finops"] = finops
    headers = {
        "x-finops-served-by": str(finops.get("servedBy", {}).get("id", "")),
        "x-finops-cost-usd": f"{finops.get('costUsd', 0):.6f}",
        "x-finops-savings-pct": f"{finops.get('savingsPct', 0):.1f}",
    }
    if not stream:
        return JSONResponse(resp, headers=headers)

    # Streaming: we already served fully (so headers/finops are known); emit the
    # buffered answer as OpenAI SSE chunks so streaming clients work unchanged.
    content = resp["choices"][0]["message"]["content"]
    cid, created, model_id = resp["id"], resp["created"], resp["model"]

    def _gen():
        def chunk(delta, finish=None):
            o = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_id,
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(o)}\n\n"
        yield chunk({"role": "assistant"})
        buf = ""
        for ch in content:
            buf += ch
            if len(buf) >= 24 or ch == "\n":
                yield chunk({"content": buf}); buf = ""
        if buf:
            yield chunk({"content": buf})
        yield chunk({}, finish="stop")
        yield f"data: {json.dumps({'x_finops': finops})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={**SSE_HEADERS, **headers})


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
