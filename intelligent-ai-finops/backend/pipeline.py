"""Tab 2 - the context-routing stage engine (§6.2), rebuilt from the v1 flow
stages plus the full Unity AI Gateway feature set.

Stages are NOT decorative: each mutates a shared request context and the outcome
genuinely changes (serving before classification defaults to frontier and costs
more - the teaching moment). Many stages are Unity AI Gateway features the field
can open and configure/inspect, so this doubles as a Gateway demo.

Routing is interactive: the caller passes which model represents each tier
(frontier / large-oss / small-oss); model-serving invokes the selected model, so
the "landed on" result reflects what the presenter chose.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import models
from .appconfig import load_config

# The demo question bank (id, text, complexity 0-100). A refined spread of real
# enterprise asks, from trivial lookups (a small model wins) up to strategy and
# architecture questions where the judge gap earns a frontier model.
# Natural, complete questions a real user would type - spread across the
# complexity range so the routing spread is visible. `t` is used verbatim as the
# prompt when a pill is picked, so it must read like a genuine ask, not a label.
QUESTIONS = [
    {"id": "q1", "t": "How do I reset a locked user account? Walk me through the steps.", "cx": 8},
    {"id": "q2", "t": "Can you summarize our PTO and parental-leave policy for a new hire in a short paragraph?", "cx": 18},
    {"id": "q3", "t": "Draft a short customer-facing note that summarizes this outage ticket and what we're doing about it.", "cx": 34},
    {"id": "q4", "t": "Compare our three product lines by gross margin and tell me which one is the outlier and why.", "cx": 52},
    {"id": "q5", "t": "Write a recursive SQL CTE that rolls our org hierarchy up to total headcount per manager, and explain how it works.", "cx": 63},
    {"id": "q6", "t": "We have three conflicting incident timelines from different teams - can you reconcile them into one and justify each inference?", "cx": 74},
    {"id": "q7", "t": "How would you migrate a 2TB Postgres monolith to a sharded database with zero downtime and no data loss? Walk through the plan and the failure modes.", "cx": 95},
    {"id": "q8", "t": "We're weighing a $400M acquisition financed with cash, debt, and stock - can you build the full valuation (DCF, comps, accretion/dilution, downside cases) and give me a go/no-go recommendation?", "cx": 96},
    {"id": "q9", "t": "Help me design a five-year capital-allocation strategy across three macro scenarios (soft landing, recession, stagflation) - where should free cash flow go, and what triggers a shift?", "cx": 92},
    {"id": "q10", "t": "We're moving from seat-based to usage-based pricing - how should we repackage it, model the revenue impact, and migrate existing customers safely?", "cx": 88},
]

# Stage catalogue. `feature` names the Unity AI Gateway (or platform) capability a
# dropped node can open and configure/inspect; None = not separately configurable.
#   (name, category, cfg, feature)
STAGES = {
    "service-principal": ("Service principal", "guard", "scope = finops", None),
    "rate-limits": ("Rate limits", "guard", "120 / min / user", "rate-limits"),
    "guardrails": ("AI guardrails", "guard", "PII + safety, pre-egress", "guardrails"),
    "semantic-cache": ("Semantic cache", "guard", "0.94 similarity", "semantic-cache"),
    "complexity-score": ("Complexity score", "route", "0 – 100", None),
    "routing-policy": ("Routing / traffic policy", "route", "tier → model", "routing-policy"),
    "budget-check": ("Budget check", "route", "$12k / month cap", "budgets"),
    "fallback-chain": ("Fallback chain", "serve", "on 429 / 5xx", "fallback"),
    "model-serving": ("Model serving", "serve", "invoke endpoint", None),
    "inference-tables": ("Inference tables", "observe", "payload logging", "inference-tables"),
    "usage-metrics": ("Usage & metrics", "observe", "system.ai_gateway.usage", "usage-metrics"),
    "traces": ("Traces (MLflow)", "observe", "spans + latency", "traces"),
    "uc-lineage": ("UC lineage", "observe", "column-level", None),
}

# v1-style end-to-end reference flow.
REFERENCE = [
    "service-principal", "rate-limits", "guardrails", "semantic-cache",
    "complexity-score", "routing-policy", "budget-check", "fallback-chain",
    "model-serving", "inference-tables", "usage-metrics", "traces", "uc-lineage",
]

_TIER_DOWN = {"frontier": "large-oss", "large-oss": "small-oss", "small-oss": "small-oss"}


@dataclass
class Ctx:
    cx: int
    tier_models: dict  # tier -> model id chosen by the presenter
    lat: int = 0
    cost: float = 0.0
    tier: str = "frontier"
    classified: bool = False
    cache_hit: bool = False
    in_tok: int = 640
    out_tok: int = 190
    model_short: str | None = None


def _model_for_tier(c: Ctx):
    """The presenter-selected model for a tier, else the cheapest in that tier."""
    mid = c.tier_models.get(c.tier)
    if mid:
        try:
            return models.by_id(mid)
        except KeyError:
            pass
    return models.cheapest_of_tier(c.tier)


def _run_stage(stage_id: str, c: Ctx) -> dict:
    th = load_config()["policy"]["thresholds"]

    def ev(outcome: str, message: str, dlat: int = 0) -> dict:
        return {"stage": stage_id, "outcome": outcome, "message": message, "latencyDeltaMs": dlat}

    if stage_id == "service-principal":
        return ev("ok", "identity resolved · sp-finops-prod")
    if stage_id == "rate-limits":
        return ev("ok", "quota 41 of 120 this minute · pass")
    if stage_id == "guardrails":
        c.lat += 40
        return ev("ok", "2 PII entities masked · safety pass · +40ms", 40)
    if stage_id == "semantic-cache":
        if c.cx < 20 and random.random() < 0.6:
            c.cache_hit = True
            return ev("hit", "CACHE HIT · cost 0, 12ms")
        return ev("ok", "cache miss · continue")
    if stage_id == "complexity-score":
        c.classified = True
        return ev("hit", f"complexity scored {c.cx}")
    if stage_id == "routing-policy":
        if not c.classified:
            c.tier = "frontier"
            return ev("warn", "no score available · defaulting to FRONTIER")
        c.tier = "small-oss" if c.cx < th["small_max"] else "large-oss" if c.cx < th["large_max"] else "frontier"
        return ev("hit", f"matched → {c.tier} ({_model_for_tier(c).short})")
    if stage_id == "budget-check":
        if c.tier == "frontier" and c.cx < 80:
            c.tier = "large-oss"
            return ev("warn", "61% of cap used · downgraded one tier")
        return ev("ok", "61% of cap used · no action")
    if stage_id == "fallback-chain":
        if random.random() < 0.25:
            c.tier = _TIER_DOWN[c.tier]
            return ev("warn", "primary returned 429 · failed over")
        return ev("ok", "primary healthy · no failover")
    if stage_id == "model-serving":
        m = _model_for_tier(c)
        c.model_short = m.short
        dlat = models.demo_latency_ms(m)
        c.lat += dlat
        c.cost = m.cost_usd(c.in_tok, c.out_tok)
        return ev("hit", f"invoked {m.short}", dlat)
    if stage_id == "inference-tables":
        return ev("ok", "payload + usage written to UC")
    if stage_id == "usage-metrics":
        return ev("ok", "tokens, cost, latency → system.ai_gateway.usage")
    if stage_id == "traces":
        return ev("ok", "spans logged to MLflow")
    if stage_id == "uc-lineage":
        return ev("ok", "answer linked to source tables")
    return ev("ok", stage_id)


def _advisory(stages: list[str], c: Ctx) -> dict:
    frontier = models.frontier_model()
    fcost = frontier.cost_usd(c.in_tok, c.out_tok)
    if "complexity-score" not in stages:
        return {"kind": "warn", "text": "No complexity score in the track, so the routing policy has nothing to match on and everything defaults to frontier. This is the most expensive stage to leave out."}
    if "model-serving" not in stages:
        return {"kind": "warn", "text": "No serving stage, so the request never reaches a model."}
    if "budget-check" not in stages:
        return {"kind": "warn", "text": "No budget check, so nothing stops a spike from burning the monthly cap in a week."}
    if "fallback-chain" not in stages:
        return {"kind": "warn", "text": "No fallback chain, so a provider 429 becomes a user-visible error instead of a cheaper answer."}
    if "guardrails" not in stages:
        return {"kind": "warn", "text": "No AI guardrail, so raw prompts reach the provider unmasked."}
    return {"kind": "ok", "text": f"Complete pipeline. This request cost ${c.cost:.4f} against ${fcost:.4f} for an all-frontier path, and every hop is queryable in Unity Catalog."}


def run(complexity: int, stages: list[str], tier_models: dict | None = None) -> dict:
    """Run the ordered pipeline. `tier_models` maps tier → chosen model id."""
    c = Ctx(cx=complexity, tier_models=tier_models or {})
    trace: list[dict] = []

    for stage_id in stages:
        if c.cache_hit and stage_id not in ("model-serving", "inference-tables", "usage-metrics"):
            trace.append({"stage": stage_id, "outcome": "skip", "message": "skipped (cache hit)", "latencyDeltaMs": 0, "skipped": True})
            continue
        if c.cache_hit and stage_id == "model-serving":
            c.model_short = "semantic cache"
            c.cost = 0.0
            c.lat = 12
            trace.append({"stage": stage_id, "outcome": "hit", "message": "served from cache", "latencyDeltaMs": 0, "skipped": True})
            continue
        trace.append({**_run_stage(stage_id, c), "skipped": False})

    if c.model_short is None:
        trace.append({"stage": "model-serving", "outcome": "warn", "message": "no serving stage · request never left the gateway", "latencyDeltaMs": 0, "skipped": False})

    frontier = models.frontier_model()
    return {
        "trace": trace,
        "landed": {"short": c.model_short, "tier": c.tier, "costUsd": c.cost, "latencyMs": c.lat},
        "costUsd": c.cost,
        "frontierCostUsd": frontier.cost_usd(c.in_tok, c.out_tok),
        "advisory": _advisory(stages, c),
        "servedAModel": c.model_short is not None and c.cost > 0,
    }
