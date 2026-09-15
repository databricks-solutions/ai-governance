"""V2: read the LIVE AI Gateway config off each serving endpoint via the SDK.

The demo panels are illustrative; this returns the REAL per-endpoint `ai_gateway`
block the platform actually enforces - usage tracking, rate limits, guardrails,
inference tables, fallbacks. Cached in-process with a short TTL so the UI stays
snappy (config changes rarely; a fresh SDK round-trip per endpoint per render
would be wasteful). The Lakebase durable store could persist this cache across
restarts, but the payload is tiny and one SDK call is already fast, so an in-process
cache is the right tool here - see V2_SETUP.md.
"""
from __future__ import annotations

import os
import time

_TTL = 120.0
_cache: dict[str, tuple[float, dict]] = {}


def _summarize(ag) -> dict:
    """Normalise the SDK AiGatewayConfig object into UI-friendly flags/counts."""
    ut = getattr(ag, "usage_tracking_config", None) if ag else None
    rl = getattr(ag, "rate_limits", None) if ag else None
    gr = getattr(ag, "guardrails", None) if ag else None
    it = getattr(ag, "inference_table_config", None) if ag else None
    fb = getattr(ag, "fallback_config", None) if ag else None
    return {
        "usageTracking": bool(ut and getattr(ut, "enabled", False)),
        "rateLimits": len(rl) if rl else 0,
        "guardrails": gr is not None,
        "inferenceTable": bool(it and getattr(it, "enabled", False)),
        "fallback": bool(fb and getattr(fb, "enabled", False)),
    }


def endpoint_config(model_id: str) -> dict:
    now = time.time()
    hit = _cache.get(model_id)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        from databricks.sdk import WorkspaceClient
        ep = WorkspaceClient().serving_endpoints.get(model_id)
        summ = _summarize(getattr(ep, "ai_gateway", None))
        summ["ok"] = True
    except Exception as e:  # noqa: BLE001 - degrade to a visible flag, never hang
        summ = {"ok": False, "error": str(e)[:120]}
    _cache[model_id] = (now, summ)
    return summ


def configs(model_ids: list[str]) -> dict:
    return {mid: endpoint_config(mid) for mid in model_ids}


_AG_FIELDS = ("usage_tracking_config", "rate_limits", "guardrails",
              "inference_table_config", "fallback_config")


def _client(user_token: str | None = None):
    """A WorkspaceClient acting as the SIGNED-IN USER when a forwarded token is given
    (Databricks Apps on-behalf-of-user), else the app's service principal.

    System pay-per-token endpoints are platform-managed: the app SP can't be granted
    CAN_MANAGE on them, but a human admin CAN write their ai_gateway config. So writes
    run as the user (their token, from the X-Forwarded-Access-Token header) - the change
    lands on the real endpoint and is audited to that person."""
    from databricks.sdk import WorkspaceClient
    if user_token:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return WorkspaceClient(host=host or None, token=user_token, auth_type="pat")
    return WorkspaceClient()


def set_endpoint_gateway(model_id: str, patch: dict, user_token: str | None = None) -> dict:
    """Admin-style WRITE: merge `patch` into the endpoint's ai_gateway config and PUT
    it via the SDK. Runs AS THE SIGNED-IN USER when `user_token` is supplied (so a human
    admin can alter a platform-managed system endpoint that the app SP cannot). Reads the
    current config first so a partial patch (e.g. just rate_limits) doesn't clobber the
    other fields. Returns the refreshed summary and busts the read cache."""
    w = _client(user_token)
    cur = (w.serving_endpoints.get(model_id).as_dict().get("ai_gateway") or {})
    body = {k: v for k, v in cur.items() if k in _AG_FIELDS}
    body.update(patch)
    w.api_client.do("PUT", f"/api/2.0/serving-endpoints/{model_id}/ai-gateway", body=body)
    _cache.pop(model_id, None)  # force a fresh read next time
    return endpoint_config(model_id)
