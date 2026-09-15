"""Reliability & fallback observability - REAL routing attempts from the gateway.

system.ai_gateway.usage carries a `routing_information.attempts` array per request:
each attempt's action (INITIAL_ATTEMPT / FALLBACK), destination, status_code,
error_code and latency. That's the gateway's real per-request routing chain, so we
can surface actual reliability: how often a request needed a fallback, the initial
error rate, the status breakdown (429 rate limits / 4xx / 5xx), and which
destinations fail most. Complements the app's own app-level fallback feature with
the gateway's native fallback telemetry.

In-process cached (5 min); degrades to {"source":"unavailable"} so the tab never
hard-fails.
"""
from __future__ import annotations

import os
import time

from . import datasource

_CACHE: dict[int, tuple[float, dict]] = {}
_TTL_S = 300


def overview(days: int = 30) -> dict:
    now = time.time()
    hit = _CACHE.get(days)
    if hit and now - hit[0] < _TTL_S:
        return hit[1]
    warehouse_id = os.environ.get("FINOPS_WAREHOUSE_ID")
    if not warehouse_id:
        return {"source": "unavailable", "reason": "no warehouse configured"}
    try:
        data = _compute(warehouse_id, days)
    except Exception as e:  # noqa: BLE001
        return {"source": "unavailable", "reason": str(e)[:160]}
    _CACHE[days] = (now, data)
    return data


def _compute(warehouse_id: str, days: int) -> dict:
    win = f"event_time >= now() - INTERVAL {int(days)} DAYS AND routing_information.attempts IS NOT NULL"
    # Attempt-level: action x status-class x destination (bounded).
    q_attempts = f"""
        SELECT a.action AS action,
               a.destination AS destination,
               CASE WHEN a.status_code < 300 THEN 'ok'
                    WHEN a.status_code = 429 THEN 'rate_limited'
                    WHEN a.status_code < 500 THEN 'client_error'
                    ELSE 'server_error' END AS cls,
               count(*) AS n
        FROM system.ai_gateway.usage LATERAL VIEW explode(routing_information.attempts) t AS a
        WHERE {win}
        GROUP BY 1,2,3
    """
    # Request-level: how many attempts each request took (>1 = a fallback fired).
    q_mult = f"""
        SELECT size(routing_information.attempts) AS attempts, count(*) AS n
        FROM system.ai_gateway.usage
        WHERE {win}
        GROUP BY 1 ORDER BY 1
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_att = ex.submit(datasource._run, warehouse_id, q_attempts)
        f_mult = ex.submit(datasource._run, warehouse_id, q_mult)
        att_rows = f_att.result()
        mult_rows = f_mult.result()

    by_action: dict[str, int] = {}
    status_class: dict[str, int] = {"ok": 0, "rate_limited": 0, "client_error": 0, "server_error": 0}
    initial_total = initial_ok = fallback_total = fallback_ok = 0
    failing: dict[str, dict] = {}
    for r in att_rows:
        action = r.get("action") or "?"
        cls = r.get("cls") or "ok"
        dest = r.get("destination") or "?"
        n = int(r.get("n") or 0)
        by_action[action] = by_action.get(action, 0) + n
        status_class[cls] = status_class.get(cls, 0) + n
        if action == "INITIAL_ATTEMPT":
            initial_total += n
            if cls == "ok":
                initial_ok += n
            else:
                f = failing.setdefault(dest, {"destination": dest, "failures": 0})
                f["failures"] += n
        elif action == "FALLBACK":
            fallback_total += n
            if cls == "ok":
                fallback_ok += n

    total_requests = sum(int(r.get("n") or 0) for r in mult_rows)
    fallback_fires = sum(int(r.get("n") or 0) for r in mult_rows if int(r.get("attempts") or 0) > 1)
    attempt_hist = [{"attempts": int(r.get("attempts") or 0), "requests": int(r.get("n") or 0)} for r in mult_rows]
    total_attempts = sum(by_action.values()) or 1

    return {
        "source": "system_tables",
        "windowDays": days,
        "totals": {
            "requests": total_requests,
            "attempts": sum(by_action.values()),
            "fallbackFires": fallback_fires,
            "fallbackRatePct": round(fallback_fires / total_requests * 100, 2) if total_requests else 0.0,
            "fallbackServedOk": fallback_ok,
            "initialErrorRatePct": round((initial_total - initial_ok) / initial_total * 100, 2) if initial_total else 0.0,
            "okRatePct": round(status_class["ok"] / total_attempts * 100, 2),
        },
        "byAction": [{"action": k, "count": v} for k, v in sorted(by_action.items(), key=lambda kv: -kv[1])],
        "statusClass": status_class,
        "attemptHist": attempt_hist,
        "topFailing": sorted(failing.values(), key=lambda x: -x["failures"])[:6],
    }
