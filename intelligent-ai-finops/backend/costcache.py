"""Shared, cached access to the REAL cost/usage overview from system tables.

Extracted so both the Cost tab endpoint (main.py) and the router's live budget
enforcement (proxy.py) read the same cached aggregate instead of each paying the
multi-second system-table scan. Memory cache first (instant), then the Lakebase
durable cache (cross-replica), then a fresh compute that populates both. Any
failure returns a demo marker so callers degrade gracefully - never hard-fail.
"""
from __future__ import annotations

import time

from .appconfig import load_config

_OV_CACHE: dict[int, tuple[float, dict]] = {}  # keyed by window (days)
_OV_TTL = 300.0  # 5 min - the system-tables scan is the slow part


def overview(days: int) -> dict:
    """REAL cost/usage overview for a window, served from cache when warm."""
    cfg = load_config()
    if cfg.get("dataSource") != "system_tables" or not cfg.get("warehouseId"):
        return {"source": "demo"}
    from . import datasource, lakebase
    now = time.time()
    key = f"cost_overview_{days}"
    hit = _OV_CACHE.get(days)                             # 1) in-process cache (instant)
    if hit and now - hit[0] < _OV_TTL:
        return {**hit[1], "cached": "memory"}
    lb = lakebase.get(key, _OV_TTL)                       # 2) durable cache (cross-replica)
    if lb:
        _OV_CACHE[days] = (now, lb)
        return {**lb, "cached": "lakebase"}
    try:                                                  # 3) compute + populate both
        ov = datasource.system_tables_overview(cfg["warehouseId"], days=days, dbu_to_usd=cfg["dbuToUsd"])
        _OV_CACHE[days] = (now, ov)
        lakebase.put(key, ov)
        return {**ov, "cacheBackend": "lakebase" if lakebase.available() else "memory"}
    except Exception as e:  # noqa: BLE001 - never hard-fail; fall back to demo
        return {"source": "demo", "error": str(e)[:200]}


def spend_last_30d() -> float | None:
    """Real month-to-date-ish spend (last 30 days) for live budget enforcement, from
    the cached overview. None when system tables aren't the source (demo/unconfigured)."""
    ov = overview(30)
    if ov.get("source") != "system_tables":
        return None
    return float((ov.get("totals") or {}).get("spendUsd") or 0.0)
