"""The router: classify → policy → budget → serve, returning a full
RoutingReceipt (§4, §7). The frontend never computes cost - this module (or the
live serving path) is the single source of the numbers.

Demo mode synthesises complexity, latency and judge scores; live mode calls a
small classifier endpoint and the chosen serving endpoint. Either way the shape
returned is identical, so the UI is oblivious to which mode produced it.
"""
from __future__ import annotations

import re
import uuid

from . import models
from .appconfig import load_config

# Words that mark genuinely hard, open-ended work - nudges complexity up.
_HARD = re.compile(r"why|prove|reconcile|design|architect|debug|justify|strategy|root.?cause", re.I)


def classify(prompt: str) -> int:
    """Score prompt complexity 0–100. Demo heuristic mirrors the prototype; the
    live path would call a small serving endpoint instead of this regex."""
    score = 12 + len(prompt) * 0.55 + (30 if _HARD.search(prompt) else 0)
    return int(min(99, max(1, round(score))))


def tier_for(complexity: int) -> str:
    th = load_config()["policy"]["thresholds"]
    if complexity < th["small_max"]:
        return "small-oss"
    if complexity < th["large_max"]:
        return "large-oss"
    return "frontier"


def route(prompt: str, force_tier: str | None = None, demo: bool = True,
          budget_pct: float = 61.0, days_left: int = 9) -> dict:
    """Return a full RoutingReceipt for a single prompt."""
    complexity = classify(prompt)
    forced = force_tier is not None
    tier = force_tier if forced else tier_for(complexity)
    chosen = models.cheapest_of_tier(tier)
    frontier = models.frontier_model()

    # Budget escalation: over the downgrade threshold, a frontier route drops a
    # tier (your policy, layered on the native budget signal).
    budget = load_config()["policy"]["budget"]
    escalated = False
    if not forced and tier == "frontier" and budget_pct >= budget["downgrade_at_pct"] and complexity < 80:
        tier = "large-oss"
        chosen = models.cheapest_of_tier(tier)
        escalated = True

    in_tok = 400 + len(prompt) * 2
    out_tok = 190

    if demo:
        cost = chosen.cost_usd(in_tok, out_tok)
        latency = models.demo_latency_ms(chosen)
        judge = models.demo_judge(chosen)
    else:
        live = models.live_query(chosen, prompt)
        cost, latency = live["cost_usd"], live["latency_ms"]
        in_tok, out_tok = live["input_tokens"], live["output_tokens"]
        judge = models.demo_judge(chosen)  # replaced by judge.py in live judging

    frontier_cost = frontier.cost_usd(in_tok, out_tok)

    policy_matched = (
        f"forced → {tier}" if forced else f"complexity {complexity} → {tier}"
    )

    return {
        "requestId": uuid.uuid4().hex[:12],
        "model": {"id": chosen.id, "short": chosen.short, "tier": chosen.tier},
        "costUsd": cost,
        "latencyMs": latency,
        "judgeScore": judge,
        "complexity": complexity,
        "policyMatched": policy_matched,
        "budgetState": {"spentPct": budget_pct, "daysLeft": days_left, "escalated": escalated},
        "counterfactual": {
            "model": frontier.short,
            "costUsd": frontier_cost,
            "judgeScore": 9.0,
        },
        "forced": forced,
        "trace": [],
    }
