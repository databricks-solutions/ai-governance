"""V2 cost datasource - REAL spend/usage from Unity Catalog system tables.

The demo/AE app synthesises the Cost tab from an in-memory session. V2 instead
reads the actual gateway/serving telemetry the workspace already collects:

  - system.ai_gateway.usage        requests, tokens, latency, requester, model
  - system.serving.endpoint_usage  (alternative request/latency source)
  - system.billing.usage           actual billed DBUs (for true $, see note below)

Cost here is derived as REAL token usage x the published DBU rate card (the same
rates in config/models.yaml) - i.e. real usage priced with the known rate card,
consistent with the rest of the app. For contract-accurate billed dollars, swap
the per-model cost to a join against system.billing.usage x system.billing
list_prices; the query shape is the same.

Runs the queries through a SQL warehouse using the Databricks App's service
principal (the SDK picks up the app's ambient credentials). The App SP must have
SELECT on the system schemas and USE on the warehouse - see V2_SETUP.md. If the
warehouse or grants are missing, the caller falls back to demo mode so the app
never hard-fails.
"""
from __future__ import annotations

import os

from . import models

_DBU_TO_USD_DEFAULT = 0.07


def _tier_for(model_name: str) -> str:
    """Resolve a serving/gateway model name to a registry tier, by id/short match
    then a name heuristic for anything not in the curated registry."""
    name = (model_name or "").lower()
    for m in models.registry():
        if m.id.lower() == name or m.short.lower() == name or m.short.lower() in name:
            return m.tier
    if any(k in name for k in ("claude", "gpt-5", "gemini", "opus", "sonnet")):
        return "frontier"
    if any(k in name for k in ("120b", "70b", "maverick", "qwen3-next", "glm", "deepseek-v4-pro")):
        return "large-oss"
    return "small-oss"


def _cost_usd(model_name: str, in_tok: int, out_tok: int, dbu_to_usd: float) -> float:
    """Real tokens x published DBU rate card. Falls back to the tier's cheapest
    registry model when the exact model isn't in the registry."""
    name = (model_name or "").lower()
    m = next((x for x in models.registry() if x.id.lower() == name or x.short.lower() == name), None)
    if m is None:
        tier = _tier_for(model_name)
        cands = [x for x in models.registry() if x.tier == tier]
        m = min(cands, key=lambda x: x.dbu_out_per_1m) if cands else None
    if m is None:
        return 0.0
    return (in_tok / 1e6) * m.dbu_in_per_1m * dbu_to_usd + (out_tok / 1e6) * m.dbu_out_per_1m * dbu_to_usd


def _run(warehouse_id: str, sql: str) -> list[dict]:
    """Execute one SQL statement on the warehouse as the app's SP; return rows as dicts."""
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="50s",
    )
    result = resp.result
    if result is None or not result.data_array:
        return []
    cols = [c.name for c in resp.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in result.data_array]


def system_tables_overview(warehouse_id: str, days: int = 30, dbu_to_usd: float | None = None) -> dict:
    """Real cost/usage overview for the Cost tab, shaped like the demo aggregates:
    totals, byModel, byTier, byUser, byGroup, daily. Raises on any failure so the
    caller can fall back to demo."""
    d2u = dbu_to_usd if dbu_to_usd is not None else float(os.environ.get("FINOPS_DBU_TO_USD", _DBU_TO_USD_DEFAULT))
    win = f"event_time >= now() - INTERVAL {int(days)} DAYS AND status_code < 300"

    # The four aggregates are independent full scans of system.ai_gateway.usage, so
    # run them CONCURRENTLY (one warehouse, four parallel statements) instead of
    # sequentially - this is the dominant latency of the Cost tab, and on a cold
    # serverless warehouse they now share one start-up wait instead of four.
    from concurrent.futures import ThreadPoolExecutor
    q_by_model = f"""
        SELECT destination_model AS model,
               count(*) AS requests,
               sum(coalesce(input_tokens,0)) AS in_tok,
               sum(coalesce(output_tokens,0)) AS out_tok,
               avg(latency_ms) AS avg_latency_ms,
               percentile(latency_ms, 0.5) AS p50_latency_ms,
               percentile(latency_ms, 0.95) AS p95_latency_ms
        FROM system.ai_gateway.usage
        WHERE {win} AND destination_model IS NOT NULL
        GROUP BY 1 ORDER BY requests DESC LIMIT 50
    """
    q_by_user = f"""
        SELECT requester AS user, requester_type AS kind,
               count(*) AS requests,
               sum(coalesce(input_tokens,0)) AS in_tok,
               sum(coalesce(output_tokens,0)) AS out_tok
        FROM system.ai_gateway.usage
        WHERE {win} AND requester IS NOT NULL
        GROUP BY 1,2 ORDER BY requests DESC LIMIT 25
    """
    q_daily = f"""
        SELECT date(event_time) AS d,
               count(*) AS requests,
               count(DISTINCT requester) AS users
        FROM system.ai_gateway.usage
        WHERE {win}
        GROUP BY 1 ORDER BY 1
    """
    q_recent = f"""
        SELECT event_time, requester, destination_model,
               coalesce(input_tokens,0) AS in_tok, coalesce(output_tokens,0) AS out_tok, latency_ms
        FROM system.ai_gateway.usage
        WHERE {win} AND destination_model IS NOT NULL
        ORDER BY event_time DESC LIMIT 25
    """
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_model = ex.submit(_run, warehouse_id, q_by_model)
        f_user = ex.submit(_run, warehouse_id, q_by_user)
        f_daily = ex.submit(_run, warehouse_id, q_daily)
        f_recent = ex.submit(_run, warehouse_id, q_recent)
        by_model_rows = f_model.result()
        by_user_rows = f_user.result()
        daily_rows = f_daily.result()
        recent_rows = f_recent.result()

    # Price each model's real tokens with the rate card; roll up to tiers + totals.
    # Reference models for the savings math: cheapest frontier (the "route
    # everything to a frontier model" baseline), cheapest large/small OSS (what the
    # frontier traffic WOULD cost if it had been routed down).
    fm = models.cheapest_of_tier("frontier")
    lg = min((m for m in models.registry() if m.tier == "large-oss"), key=lambda m: m.dbu_out_per_1m, default=fm)
    sm = min((m for m in models.registry() if m.tier == "small-oss"), key=lambda m: 800 * m.dbu_in_per_1m + 400 * m.dbu_out_per_1m, default=fm)

    by_model = []
    by_tier = {t: {"cost": 0.0, "count": 0, "in_tok": 0, "out_tok": 0} for t in ("small-oss", "large-oss", "frontier")}
    total_cost = total_req = 0
    for r in by_model_rows:
        it, ot, req = int(r["in_tok"] or 0), int(r["out_tok"] or 0), int(r["requests"] or 0)
        tier = _tier_for(r["model"])
        cost = _cost_usd(r["model"], it, ot, d2u)
        by_model.append({"model": r["model"], "tier": tier, "cost": cost, "count": req,
                         "avgLatencyMs": float(r["avg_latency_ms"] or 0),
                         "p50LatencyMs": float(r.get("p50_latency_ms") or 0),
                         "p95LatencyMs": float(r.get("p95_latency_ms") or 0)})
        by_tier[tier]["cost"] += cost
        by_tier[tier]["count"] += req
        by_tier[tier]["in_tok"] += it
        by_tier[tier]["out_tok"] += ot
        total_cost += cost
        total_req += req
    frontier_in = by_tier["frontier"]["in_tok"]
    frontier_out = by_tier["frontier"]["out_tok"]
    _ = fm  # fm reserved as the frontier reference; opportunity math uses downroute below

    def _group_of(user: str) -> str:
        # First-cut group attribution from the requester's email domain; true group
        # membership would join system.access / SCIM identity data.
        return user.split("@")[-1] if user and "@" in user else "service-principal"

    by_user = [{"user": r["user"], "group": _group_of(r["user"]), "kind": r["kind"],
                "cost": _cost_usd_from_row(r, d2u), "count": int(r["requests"] or 0)} for r in by_user_rows]
    groups: dict[str, dict] = {}
    for u in by_user:
        g = groups.setdefault(u["group"], {"group": u["group"], "cost": 0.0, "count": 0})
        g["cost"] += u["cost"]; g["count"] += u["count"]
    by_group = sorted(groups.values(), key=lambda x: -x["cost"])

    # What the frontier traffic would have cost on OSS (same tokens, cheaper rate) -
    # the "routine asks over-used the frontier" retrospective.
    frontier_spend = by_tier["frontier"]["cost"]
    if_large = (frontier_in / 1e6) * lg.dbu_in_per_1m * d2u + (frontier_out / 1e6) * lg.dbu_out_per_1m * d2u
    if_small = (frontier_in / 1e6) * sm.dbu_in_per_1m * d2u + (frontier_out / 1e6) * sm.dbu_out_per_1m * d2u

    # Recent requests for the activity log (fetched concurrently above).
    recent = [{"ts": str(r["event_time"]), "user": r["requester"], "model": r["destination_model"],
               "tier": _tier_for(r["destination_model"]),
               "costUsd": _cost_usd(r["destination_model"], int(r["in_tok"] or 0), int(r["out_tok"] or 0), d2u),
               "latencyMs": float(r["latency_ms"] or 0)} for r in recent_rows]

    # ---- Counterfactual: replay THIS real traffic through the router ----------
    # For each tier, reprice the tier's REAL tokens at (a) the cheapest model IN
    # that tier (a provable floor - "you paid for the priciest model in a tier a
    # cheaper one in the SAME tier would have cleared") and (b) the cheapest model
    # in the tier BELOW (the routed-down projection). The frontend blends these by
    # a user-set downgrade fraction, so the savings number is computed on the
    # customer's OWN bill, not a synthetic session.
    def _cheapest_in_tier(tier: str, it: int, ot: int):
        cands = [m for m in models.registry() if m.tier == tier]
        if not cands:
            return None, None
        m = min(cands, key=lambda x: (it / 1e6) * x.dbu_in_per_1m + (ot / 1e6) * x.dbu_out_per_1m)
        return (it / 1e6) * m.dbu_in_per_1m * d2u + (ot / 1e6) * m.dbu_out_per_1m * d2u, m.short

    _tier_below = {"frontier": "large-oss", "large-oss": "small-oss", "small-oss": None}
    cf_tiers = []
    for tier in ("frontier", "large-oss", "small-oss"):
        tk = by_tier[tier]
        it, ot = tk["in_tok"], tk["out_tok"]
        cheap_cost, cheap_model = _cheapest_in_tier(tier, it, ot)
        below = _tier_below[tier]
        below_cost, below_model = _cheapest_in_tier(below, it, ot) if below else (None, None)
        cf_tiers.append({
            "tier": tier, "requests": tk["count"], "actualCost": tk["cost"],
            "inTok": it, "outTok": ot,
            "cheapestInTierCost": cheap_cost or 0.0, "cheapestInTierModel": cheap_model,
            "tierBelowCost": below_cost, "tierBelowModel": below_model,
        })

    frontier_req = by_tier["frontier"]["count"]
    smaller_req = total_req - frontier_req
    return {
        "source": "system_tables",
        "windowDays": days,
        "totals": {"spendUsd": total_cost, "requests": total_req},
        "byModel": sorted(by_model, key=lambda x: -x["cost"]),
        "byTier": [{"tier": t, **v} for t, v in by_tier.items()],
        "byUser": by_user,
        "byGroup": by_group,
        "daily": [{"date": str(r["d"]), "requests": int(r["requests"] or 0), "users": int(r["users"] or 0)} for r in daily_rows],
        "recent": recent,
        "frontierShare": {"frontier": frontier_req, "smaller": smaller_req,
                          "smallerPct": round(smaller_req / total_req * 100) if total_req else 0},
        "frontierDownroute": {
            "requests": frontier_req,
            "frontierSpendUsd": frontier_spend,
            "ifLargeUsd": if_large, "ifSmallUsd": if_small,
            "savedLargePct": round((1 - if_large / frontier_spend) * 100) if frontier_spend else 0,
            "savedSmallPct": round((1 - if_small / frontier_spend) * 100) if frontier_spend else 0,
        },
        "counterfactual": {
            "dbuToUsd": d2u,
            "windowDays": days,
            "actualTotalUsd": total_cost,
            "tiers": cf_tiers,
            # Default downgrade fractions per tier - the share of that tier's traffic
            # a model one tier down clears at equal quality (the "~90% clear the bar"
            # thesis, applied conservatively). User-adjustable in the UI.
            "defaults": {"frontier": 0.7, "large-oss": 0.6, "small-oss": 0.0},
        },
    }


def _cost_usd_from_row(r: dict, d2u: float) -> float:
    return _cost_usd(r.get("model") or "", int(r.get("in_tok") or 0), int(r.get("out_tok") or 0), d2u)
