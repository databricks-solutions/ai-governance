"""Deployment readiness + endpoint auto-discovery (customer-deployable checks).

`readiness()` verifies the things a customer needs wired up for V2 to run against
their own workspace - a SQL warehouse, system-table grants, Model Serving
endpoints, an embedding endpoint, and (optionally) Lakebase - and returns a
green/red checklist with the exact fix for anything missing, so the app is
self-diagnosing instead of relying on prose in a setup doc.

`discover()` lists the workspace's Model Serving endpoints and cross-references
them against the curated registry: which registry models are actually deployed
here (routable), which are missing, and which live endpoints are NOT in the
registry (unpriced - flagged, never given a fabricated price).
"""
from __future__ import annotations

from .appconfig import load_config


def discover() -> dict:
    """Cross-reference the curated registry against the workspace's live serving
    endpoints. Never fabricates a price for an endpoint we don't have a rate for."""
    from . import models as reg
    reg_ids = {m.id for m in reg.registry()}
    live: list[str] = []
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        for e in w.serving_endpoints.list():
            if getattr(e, "name", None):
                live.append(e.name)
    except Exception:  # noqa: BLE001 - discovery is best-effort
        pass
    live_set = set(live)
    present = sorted(reg_ids & live_set)         # registry models deployed here → routable
    missing = sorted(reg_ids - live_set)         # registry models NOT deployed here
    extra = sorted(live_set - reg_ids)           # live endpoints not priced in the registry
    return {
        "liveCount": len(live),
        "registryCount": len(reg_ids),
        "present": present,
        "missing": missing,
        "extra": extra[:25],  # unpriced: surface, don't price
        "extraCount": len(extra),
    }


def readiness() -> dict:
    """Green/red checklist for a customer standing V2 up in their workspace."""
    from . import costcache, lakebase, semcache
    from . import models as reg
    cfg = load_config()
    checks: list[dict] = []

    # Warehouse + system tables, derived from the cached overview (no cold scan).
    ov = costcache.overview(30)
    st_ok = ov.get("source") == "system_tables"
    checks.append({
        "id": "warehouse", "label": "SQL warehouse configured",
        "ok": bool(cfg.get("warehouseId")),
        "detail": cfg.get("warehouseId") or "FINOPS_WAREHOUSE_ID is not set",
        "fix": "Set FINOPS_WAREHOUSE_ID to a serverless SQL warehouse the app service principal can use.",
    })
    checks.append({
        "id": "system_tables", "label": "Unity Catalog system tables readable",
        "ok": st_ok,
        "detail": "reading system.ai_gateway.usage" if st_ok else (ov.get("error") or "not reachable (running in demo mode)"),
        "fix": "Grant the app service principal SELECT on system.ai_gateway / system.serving and USE on the warehouse.",
    })

    # Serving-endpoint discovery.
    disc = discover()
    checks.append({
        "id": "endpoints", "label": "Model Serving endpoints discovered",
        "ok": disc["liveCount"] > 0,
        "detail": f"{disc['liveCount']} endpoints live · {len(disc['present'])}/{disc['registryCount']} registry models routable"
                  + (f" · {disc['extraCount']} unpriced" if disc["extraCount"] else ""),
        "fix": "Deploy or grant CAN_QUERY on the pay-per-token / provisioned endpoints you want to route to.",
    })

    # Embedding endpoint (semantic cache).
    emb_ok = semcache.embed("readiness probe") is not None
    checks.append({
        "id": "embedding", "label": "Embedding endpoint (semantic cache)",
        "ok": emb_ok,
        "detail": semcache._EMBED_ENDPOINT + (" reachable" if emb_ok else " unreachable"),
        "fix": "Ensure the embedding endpoint exists and the app SP has CAN_QUERY (or set FINOPS_EMBED_ENDPOINT).",
    })

    # Lakebase durable cache (optional - the app degrades to in-process without it).
    lb = lakebase.available()
    checks.append({
        "id": "lakebase", "label": "Lakebase durable cache", "optional": True,
        "ok": lb,
        "detail": "connected" if lb else "unreachable - using in-process cache (fine for a demo)",
        "fix": "Optional: grant the app SP a login role + rights on finops.cache to persist caches across replicas.",
    })

    ready = all(c["ok"] for c in checks if not c.get("optional"))
    _ = reg  # registry already used via discover()
    return {
        "ready": ready,
        "checks": checks,
        "discovery": disc,
        "warehouseId": cfg.get("warehouseId"),
        "embedEndpoint": semcache._EMBED_ENDPOINT,
        "dataSource": cfg.get("dataSource"),
    }
