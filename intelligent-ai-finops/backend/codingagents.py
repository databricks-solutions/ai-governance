"""Coding-agent cost tracker - per-harness + per-developer spend from real gateway usage.

The #1 Unity AI Gateway adoption motion is governing coding-agent spend (Claude
Code, Codex, Cursor, ...). system.ai_gateway.usage carries a `user_agent` per
request, so we classify each request to a harness and roll up REAL spend (real
tokens x the published DBU rate card, same basis as the rest of the app) by
harness and by developer - the coding-agent analog of the Cost tab's model/tier
breakdown. All data is real; only the harness label is derived (from user_agent).

In-process cached (5 min) so the tab is snappy; degrades to {"source":"unavailable"}
if the warehouse/grants are missing so the app never hard-fails.
"""
from __future__ import annotations

import os
import re
import time

from . import datasource, models

_DBU_TO_USD_DEFAULT = 0.07

# Ordered user_agent -> harness classification (first match wins). Patterns tuned to
# the real agents seen in system.ai_gateway.usage on this workspace:
#   claude-cli/2.1.x (...)              -> Claude Code
#   ucode/0.1.0 codex/0.146.0           -> Codex (via the Smart Routing ucode CLI)
#   ucode/0.1.0.post4 claude/2.1.163    -> Claude Code (via ucode)
#   OpenAI/Python, Anthropic/JS, ...    -> vendor SDKs
#   Mozilla/... Chrome/...              -> browser / playground
#   python-requests, python-httpx, node -> generic HTTP clients
_HARNESS: list[tuple[str, bool, re.Pattern]] = [
    ("Claude Code", True, re.compile(r"claude-cli|ucode/\S+\s+claude/", re.I)),
    ("Codex", True, re.compile(r"codex/", re.I)),
    ("Cursor", True, re.compile(r"cursor", re.I)),
    ("Windsurf", True, re.compile(r"windsurf|codeium", re.I)),
    ("OpenAI SDK", False, re.compile(r"openai/(python|js)|asyncopenai", re.I)),
    ("Anthropic SDK", False, re.compile(r"anthropic/(js|python|sdk)", re.I)),
    ("Agents SDK", False, re.compile(r"agents/(python|js)", re.I)),
    ("Databricks SDK", False, re.compile(r"databricks-sdk|databricks/", re.I)),
    ("Browser / Playground", False, re.compile(r"mozilla|applewebkit|chrome/|safari/", re.I)),
    ("Generic HTTP", False, re.compile(r"python-requests|python-httpx|(^|\s)node($|\s)|curl|axios|go-http", re.I)),
]
_UNKNOWN = ("Unknown / unlabeled", False)


def classify_harness(ua: str) -> tuple[str, bool]:
    """Map a user_agent string to (harness_label, is_coding_agent)."""
    ua = (ua or "").strip()
    if not ua:
        return _UNKNOWN
    for label, coding, pat in _HARNESS:
        if pat.search(ua):
            return label, coding
    return "Other", False


# 5-minute in-process cache keyed by window days.
_CACHE: dict[int, tuple[float, dict]] = {}
_TTL_S = 300


def overview(days: int = 30, dbu_to_usd: float | None = None) -> dict:
    """Per-harness + per-developer coding-agent spend for the last `days`. Cached."""
    now = time.time()
    hit = _CACHE.get(days)
    if hit and now - hit[0] < _TTL_S:
        return hit[1]
    warehouse_id = os.environ.get("FINOPS_WAREHOUSE_ID")
    if not warehouse_id:
        return {"source": "unavailable", "reason": "no warehouse configured"}
    try:
        data = _compute(warehouse_id, days, dbu_to_usd)
    except Exception as e:  # noqa: BLE001 - never hard-fail the tab
        return {"source": "unavailable", "reason": str(e)[:160]}
    _CACHE[days] = (now, data)
    return data


def _compute(warehouse_id: str, days: int, dbu_to_usd: float | None) -> dict:
    d2u = dbu_to_usd if dbu_to_usd is not None else float(os.environ.get("FINOPS_DBU_TO_USD", _DBU_TO_USD_DEFAULT))
    win = f"event_time >= now() - INTERVAL {int(days)} DAYS AND status_code < 300"
    # One grouped scan: user_agent x model x requester. Bounded to the top combos by
    # request volume (captures the bulk of spend); rolled up two ways in Python.
    q = f"""
        SELECT coalesce(user_agent,'') AS user_agent,
               destination_model AS model,
               requester,
               count(*) AS requests,
               sum(coalesce(input_tokens,0)) AS in_tok,
               sum(coalesce(output_tokens,0)) AS out_tok,
               avg(latency_ms) AS avg_latency_ms
        FROM system.ai_gateway.usage
        WHERE {win} AND destination_model IS NOT NULL
        GROUP BY 1,2,3
        ORDER BY requests DESC
        LIMIT 5000
    """
    rows = datasource._run(warehouse_id, q)

    harnesses: dict[str, dict] = {}
    devs: dict[str, dict] = {}
    total_cost = total_req = coding_cost = coding_req = 0.0

    for r in rows:
        ua = r.get("user_agent") or ""
        model = r.get("model") or ""
        user = r.get("requester") or "unknown"
        req = int(r.get("requests") or 0)
        it = int(r.get("in_tok") or 0)
        ot = int(r.get("out_tok") or 0)
        lat = float(r.get("avg_latency_ms") or 0)
        cost = datasource._cost_usd(model, it, ot, d2u)
        label, coding = classify_harness(ua)

        h = harnesses.setdefault(label, {"harness": label, "coding": coding, "requests": 0,
                                         "costUsd": 0.0, "inTok": 0, "outTok": 0,
                                         "_latWeighted": 0.0, "_devs": set()})
        h["requests"] += req
        h["costUsd"] += cost
        h["inTok"] += it
        h["outTok"] += ot
        h["_latWeighted"] += lat * req
        h["_devs"].add(user)

        total_cost += cost
        total_req += req
        if coding:
            coding_cost += cost
            coding_req += req
            # Per-developer rollup is scoped to coding-agent traffic (the governance focus).
            d = devs.setdefault(user, {"user": user, "requests": 0, "costUsd": 0.0, "_harness": {}})
            d["requests"] += req
            d["costUsd"] += cost
            d["_harness"][label] = d["_harness"].get(label, 0) + req

    by_harness = []
    for h in harnesses.values():
        reqs = h["requests"] or 1
        by_harness.append({
            "harness": h["harness"], "coding": h["coding"], "requests": h["requests"],
            "costUsd": h["costUsd"], "inTok": h["inTok"], "outTok": h["outTok"],
            "avgLatencyMs": round(h["_latWeighted"] / reqs), "developers": len(h["_devs"]),
        })
    by_harness.sort(key=lambda x: -x["costUsd"])

    by_developer = []
    for d in devs.values():
        top = max(d["_harness"].items(), key=lambda kv: kv[1])[0] if d["_harness"] else "-"
        by_developer.append({"user": d["user"], "harness": top,
                             "requests": d["requests"], "costUsd": d["costUsd"]})
    by_developer.sort(key=lambda x: -x["costUsd"])

    return {
        "source": "system_tables",
        "windowDays": days,
        "totals": {
            "requests": int(total_req), "costUsd": total_cost,
            "codingRequests": int(coding_req), "codingCostUsd": coding_cost,
            "codingDevelopers": len(devs),
            "codingSharePct": round(coding_cost / total_cost * 100, 1) if total_cost else 0.0,
        },
        "byHarness": by_harness,
        "byDeveloper": by_developer[:12],
    }
