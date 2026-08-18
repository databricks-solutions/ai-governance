"""MCP client + discovery for the MCP accelerator.

Two DIFFERENT things are both called "MCP" on Databricks, they are governed differently,
and conflating them is the single biggest source of confusion in this space:

  1. MANAGED (UC-native) endpoints — /api/2.0/mcp/{functions,genie,sql,ai-search}/...
     These expose Unity Catalog objects as tools. They are governed by
     authentication (OAuth scope picks the endpoint FAMILY) and Unity Catalog grants
     (USE CATALOG + USE SCHEMA to SEE a tool, EXECUTE to CALL it). They are NOT
     MCP_SERVICE securables, so **service policies cannot attach to them**.

  2. MCP SERVICES — /ai-gateway/mcp-services/{catalog}.{schema}.{name}
     Real Unity Catalog MCP_SERVICE securables: the Databricks-provided `system.ai.*`
     ones plus any external/custom server you register behind an HTTP connection.
     These get all of the above PLUS service policies (ALLOW / DENY / ASK).

So "can I write a policy for this?" is answered by which of the two you are pointing at.
The accelerator walks both, in that order, and says which plane it is exercising.

Protocol notes learned the hard way against a live workspace:
  - JSON-RPC errors ride INSIDE HTTP 200 over Streamable HTTP. Never infer success from
    the status code — check for a `result` key.
  - `MCP-Protocol-Version` must be sent on every request after `initialize`.
  - The response may be SSE (`text/event-stream`), so Accept must allow both and the body
    may need unwrapping from `data:` lines.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import get_config, get_workspace_client

PROTOCOL_VERSION = "2025-11-25"
_TIMEOUT = 60

# The Databricks-provided MCP Services. Kept as a hint for the UI only — the live list
# comes from the control API, because availability differs per workspace (verified: one
# workspace exposed 6 of these and 403'd on atlassian).
KNOWN_PROVIDED = [
    "system.ai.github", "system.ai.slack", "system.ai.gmail",
    "system.ai.google_drive", "system.ai.google_calendar",
    "system.ai.microsoft_365", "system.ai.atlassian",
]


def _host() -> str:
    return (get_workspace_client().config.host or "").rstrip("/")


def _headers() -> dict:
    w = get_workspace_client()
    return {
        **w.config.authenticate(),
        "Content-Type": "application/json",
        # The gateway may answer with SSE; allow both so the call does not 406.
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }


def service_url(service: str) -> str:
    """Invocation URL for an MCP Service securable (catalog.schema.name)."""
    return f"{_host()}/ai-gateway/mcp-services/{service}"


def managed_functions_url(catalog: str, schema: str) -> str:
    """Managed UC-native endpoint exposing the schema's UC functions as tools."""
    return f"{_host()}/api/2.0/mcp/functions/{catalog}/{schema}"


def _unwrap_sse(body: str) -> str:
    """Streamable HTTP may return SSE; pull the JSON out of the first data: line."""
    if not body.lstrip().startswith("data:"):
        return body
    for line in body.splitlines():
        if line.startswith("data:"):
            return line[len("data:"):].strip()
    return body


def rpc(url: str, method: str, params: dict | None = None) -> dict:
    """One JSON-RPC call. Returns {ok, result|error, http_status}.

    Never raises: the accelerator reports transport, protocol, and permission failures as
    distinct outcomes rather than collapsing them into one red box.
    """
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params or {}}).encode()
    req = urllib.request.Request(url, data=payload, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            status = resp.status
            body = _unwrap_sse(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:  # noqa: BLE001 — best-effort error body
            pass
        return {"ok": False, "http_status": e.code,
                "error": f"HTTP {e.code}: {e.reason}. {detail}".strip()}
    except Exception as e:  # noqa: BLE001 — DNS/TLS/timeout
        return {"ok": False, "http_status": None, "error": str(e)[:300]}

    try:
        parsed = json.loads(body)
    except ValueError:
        return {"ok": False, "http_status": status,
                "error": f"non-JSON response: {body[:200]}"}

    # A JSON-RPC error arrives with HTTP 200 — this is the check people forget.
    if isinstance(parsed, dict) and parsed.get("error"):
        err = parsed["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"ok": False, "http_status": status, "error": f"JSON-RPC error: {msg}"}
    return {"ok": True, "http_status": status, "result": (parsed or {}).get("result", {})}


def list_tools(url: str) -> dict:
    """tools/list, normalized to {ok, tools:[{name, description, read_only}], error}."""
    out = rpc(url, "tools/list")
    if not out["ok"]:
        return {"ok": False, "tools": [], "error": out["error"],
                "http_status": out.get("http_status")}
    tools = []
    for t in (out["result"].get("tools") or []):
        ann = t.get("annotations") or {}
        tools.append({
            "name": t.get("name"),
            "title": ann.get("title"),
            "read_only": ann.get("readOnlyHint"),
            "description": (t.get("description") or "")[:160],
        })
    return {"ok": True, "tools": tools, "error": None}


def call_tool(url: str, name: str, arguments: dict | None = None) -> dict:
    return rpc(url, "tools/call", {"name": name, "arguments": arguments or {}})


# ------------------------------------------------------------------ UC control plane
def list_mcp_services() -> dict:
    """Every MCP_SERVICE securable on the metastore, via the UC control API.

    This is the real answer to "what MCP can I govern here?" — provided `system.ai.*`
    services and any external ones a customer registered. Listing serving endpoints (the
    old placeholder) answers a different question entirely.
    """
    w = get_workspace_client()
    try:
        resp = w.api_client.do("GET", "/api/2.1/unity-catalog/mcp-services")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "services": [], "error": str(e)[:300]}
    services = []
    for s in (resp or {}).get("mcp_services", []):
        # The API returns name as "mcp-services/system.ai.github".
        full = (s.get("name") or "").split("/", 1)[-1]
        services.append({
            "name": full,
            "securable_type": s.get("securable_type"),
            "owner": s.get("effective_owner"),
            "provided": full.startswith("system.ai."),
        })
    return {"ok": True, "services": sorted(services, key=lambda x: x["name"]), "error": None}


def service_grants(service: str) -> dict:
    """UC privilege assignments on an MCP Service — the Plane 2 answer for who can call it."""
    w = get_workspace_client()
    try:
        resp = w.api_client.do(
            "GET", f"/api/2.1/unity-catalog/permissions/mcp_service/{service}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "assignments": [], "error": str(e)[:300]}
    assignments = [
        {"principal": a.get("principal"), "privileges": a.get("privileges") or []}
        for a in (resp or {}).get("privilege_assignments", [])
    ]
    return {"ok": True, "assignments": assignments, "error": None}


def configured_service() -> str:
    return (get_config().get("mcp", {}) or {}).get("builtin_service", "") or ""
