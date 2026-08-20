"""Executable governance tests, ported from the l200_demo pages.

Each test is a function returning a TestResult. They exercise real controls against the
connected workspace (list endpoints, create a governed endpoint, run guardrail/MCP policy
checks, query system tables). Steps in config/steps.yaml reference these by name.

A test result is intentionally simple and JSON-serializable so the UI can render it and
db.py can persist it as `last_result`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

from . import deep_links, mcp, routing
from .config import get_config, get_workspace_client
from .workspace_sql import fetchall, test_connection

TestResult = dict[str, Any]


def _ok(summary: str, **detail) -> TestResult:
    return {"ok": True, "summary": summary, "detail": detail}


def _fail(summary: str, **detail) -> TestResult:
    return {"ok": False, "summary": summary, "detail": detail}


def _todo(summary: str, **detail) -> TestResult:
    """A guided step that ran but proved nothing on its own.

    Distinct from _ok so the UI never renders "here is the link to do it yourself" as a
    green check. In a customer workshop a false green is worse than a visible to-do: the
    room moves on believing a control is in place when it is not.
    """
    return {"ok": True, "status": "action_required", "summary": summary, "detail": detail}


def _sql_str(value: Any) -> str:
    """Quote a value as a SQL string literal, escaping embedded quotes.

    Config is customer-edited and endpoint/tool names round-trip through these queries, so
    a stray apostrophe should be a no-match rather than a syntax error or an injected
    predicate. Use for VALUES only — identifiers go through _sql_ident.
    """
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sql_ident(name: Any, kind: str) -> str:
    """Validate a catalog/schema/function identifier from config before interpolating it.

    Identifiers cannot be parameterized, so the only safe option is to reject anything that
    is not a plain unquoted identifier. Raises so the step reports a clear config error
    rather than emitting mangled DDL.
    """
    s = str(name or "")
    if not _IDENT_RE.match(s):
        raise ValueError(
            f"Invalid {kind} in config/workshop.yaml: {s!r}. Expected a plain identifier "
            "(letters, digits, underscore; not starting with a digit)."
        )
    return s


def _fq_schema() -> tuple[str, str]:
    """(catalog, schema) from config, validated as identifiers."""
    cat = get_config().get("catalog", {})
    return (_sql_ident(cat.get("name"), "catalog.name"),
            _sql_ident(cat.get("schema"), "catalog.schema"))


# The API reference index. Only the group-level URL is cited: the Databricks API reference is
# a JS-rendered SPA that returns HTTP 200 for every path under /api/workspace/ (including
# nonsense), so deep links cannot be verified programmatically and a 404 in front of a
# customer is worse than no link. Exact method+path per test is in API_DOCS below, and
# docs/API_REFERENCE.md carries the full table.
API_INDEX = "https://docs.databricks.com/api/workspace/aigateway"

# test name -> the API surface it exercises, shown in the UI so the room can see exactly what
# the app is doing to their workspace.
API_DOCS: dict[str, dict[str, str]] = {
    "connection": {"api": "POST /api/2.0/sql/statements (SELECT 1)"},
    "default_access": {
        "api": "GET /api/2.1/unity-catalog/effective-permissions/{catalog|schema}/{name}?principal=<app-sp>",
        "note": "Read-only — reports this identity's effective reach, never changes a grant."},
    "endpoint_acl": {
        "api": "GET /api/2.0/permissions/serving-endpoints/{endpoint_id}",
        "note": "Takes the endpoint ID, not its name."},
    "workspace_context": {"api": "local config + GET /api/2.0/preview/scim/v2/Me"},
    "routing_panel": {"api": "none — reads config/workshop.yaml",
                      "note": "Prices are config, not a live API."},
    "test_mcp_policy": {"api": "POST /api/2.0/sql/statements (evaluate the policy function)"},
    "external_provider_routing": {"api": "GET /api/2.0/serving-endpoints"},
    "list_endpoints": {"api": "GET /api/2.0/serving-endpoints"},
    "model_services": {"api": "GET /api/2.1/unity-catalog/model-services"},
    "list_registered_assets": {
        "api": "GET /api/2.1/unity-catalog/models + /api/2.1/unity-catalog/functions"},
    "verify_governed_endpoint": {"api": "GET /api/2.0/serving-endpoints/{name}"},
    "rate_limits": {"api": "GET /api/2.0/serving-endpoints/{name} (ai_gateway.rate_limits)"},
    "test_guardrail": {"api": "POST /api/2.0/serving-endpoints/{name}/invocations"},
    "routing_compare": {
        "api": "POST /ai-gateway/mlflow/v1/chat/completions (each model per prompt + a classifier)",
        "note": "Per-request cost × the configured monthly request volume; smart-routing row is an estimate."},
    "routing_roi": {"api": "POST /api/2.0/serving-endpoints/{name}/invocations"},
    "create_mcp_policy": {"api": "POST /api/2.0/sql/statements (CREATE OR REPLACE FUNCTION)"},
    "mcp_policy_enforcement": {"api": "POST /api/2.0/sql/statements"},
    "mcp_inventory": {"api": "GET /api/2.1/unity-catalog/mcp-services"},
    "mcp_policy_target": {"api": "GET /api/2.1/unity-catalog/mcp-services"},
    "mcp_grants": {"api": "GET /api/2.1/unity-catalog/permissions/mcp_service/{name}"},
    "mcp_service_tools": {
        "api": "POST /ai-gateway/mcp-services/{fqn} — JSON-RPC tools/list (not REST)"},
    "mcp_obo": {"api": "POST /ai-gateway/mcp-services/{fqn} — JSON-RPC tools/call (not REST)"},
    "mcp_managed_tools": {
        "api": "POST /api/2.0/mcp/functions/{catalog}/{schema} — JSON-RPC (not REST)"},
    "mcp_external_readiness": {"api": "GET /api/2.1/unity-catalog/connections"},
    "mcp_readonly_enforcement": {
        "api": "POST /ai-gateway/mcp-services/{fqn} — JSON-RPC tools/list (not REST)",
        "note": "Classifies tools read vs write from each tool's readOnlyHint."},
    "mcp_tool_metadata_scan": {
        "api": "POST /ai-gateway/mcp-services/{fqn} — JSON-RPC tools/list (not REST)",
        "note": "Heuristic scan of tool name/description for prompt-injection ('tool poisoning')."},
    # SQL-only tests: name the table rather than a REST path, which is the useful detail.
    "usage_by_project": {"api": "SQL: system.ai_gateway.usage"},
    "coding_agent_usage": {"api": "SQL: system.ai_gateway.usage (user_agent)"},
    "coding_agent_route_check": {
        "api": "SQL: system.ai_gateway.usage (service_name vs endpoint_name)",
        "note": "service_name set = governed model service; endpoint_name only = legacy contract."},
    "path_coverage_check": {
        "api": "POST /ai-gateway/mlflow/v1/chat/completions vs POST /ai-gateway/anthropic/v1/messages",
        "note": "Probes the same prompt on both paths to compare guardrail coverage."},
    "rate_limit_429_demo": {
        "api": "GET /api/2.0/serving-endpoints/{name} + POST /ai-gateway/mlflow/v1/chat/completions (burst)",
        "note": "Sends a small burst of max_tokens=1 requests to try to trip the rate limit."},
    "mcp_telemetry": {"api": "SQL: system.ai_gateway.usage (service_type = 'MCP_SERVICE')"},
    "telemetry_readiness": {"api": "SQL: system.ai_gateway.usage, system.access.audit"},
    "gateway_spend_by_model": {"api": "SQL: system.ai_gateway.external_model_spend"},
    "budget_status": {"api": "SQL: system.ai_gateway.external_model_spend"},
    "audit_scan": {"api": "SQL: system.access.audit"},
    "guardrail_activity": {"api": "SQL: <catalog>.<schema>.<prefix>_payload (inference table)"},
    "pii_safety_readiness": {"api": "SQL: inference table + system.access.audit"},
    "pii_mask_vs_block": {
        "api": "POST /ai-gateway/mlflow/v1/chat/completions",
        "note": "Sends a PII-echo prompt and classifies the outcome: block, mask, or passthrough."},
    "guardrail_block_shape": {
        "api": "POST /ai-gateway/mlflow/v1/chat/completions",
        "note": "Sends a blocked prompt and reports whether the block is a 4xx error or HTTP 200 + reason."},
    # Deliberately not automated — say so, and say why.
    "create_governed_endpoint": {"api": "read-only: GET /api/2.0/serving-endpoints",
                                 "note": "Creation is a guided UI step, never automated."},
    "apply_tags": {"api": "none — guided UI step",
                   "note": "The app does not write tags to a customer endpoint."},
}


# --------------------------------------------------------------------------- Choice
def t_connection() -> TestResult:
    return _ok("Workspace reachable.") if test_connection() else _fail("Could not reach the SQL warehouse.")


def t_workspace_context() -> TestResult:
    cfg = get_config()
    w = get_workspace_client()
    return _ok(
        "Loaded workspace context.",
        host=(w.config.host or "").rstrip("/"),
        catalog=cfg.get("catalog", {}).get("name"),
        schema=cfg.get("catalog", {}).get("schema"),
        project=cfg.get("project", {}).get("name"),
    )


def t_list_endpoints() -> TestResult:
    w = get_workspace_client()
    eps = list(w.serving_endpoints.list())
    names = [e.name for e in eps]
    return _ok(f"Found {len(names)} serving endpoints.", endpoints=names[:50])


def t_model_services() -> TestResult:
    """Model services as UC securables — the object the client contract should point at.

    The migration story in one step. Legacy Model Serving addressed an ENDPOINT NAME on
    /serving-endpoints/<name>/invocations, with workspace ACLs. Unity AI Gateway addresses a
    UC **service FQN** on /ai-gateway/mlflow/v1, with UC privileges — so the runtime can
    change behind a stable application contract.

    There is no in-place rename: the new service is created alongside the old endpoint,
    validated, then clients move. This lists what already exists so a customer can see which
    of their endpoints has a governed equivalent.
    """
    w = get_workspace_client()
    host = (w.config.host or "").rstrip("/")
    try:
        resp = w.api_client.do("GET", "/api/2.1/unity-catalog/model-services")
    except Exception as e:
        return _fail("Could not list model services — Unity AI Gateway may not be enabled "
                     "on this workspace.", error=str(e)[:400])
    services = [s.get("name", "").split("/", 1)[-1]
                for s in (resp or {}).get("model_services", [])]
    provided = [s for s in services if s.startswith("system.ai.")]
    customer = [s for s in services if not s.startswith("system.ai.")]
    contract = {
        "legacy": {
            "base_url": f"{host}/serving-endpoints",
            "invoke": f"{host}/serving-endpoints/<endpoint-name>/invocations",
            "model": "<endpoint-name>",
            "authz": "endpoint ACL (CAN_QUERY)",
        },
        "unity_ai_gateway": {
            "base_url": f"{host}/ai-gateway/mlflow/v1",
            "invoke": f"{host}/ai-gateway/mlflow/v1/chat/completions",
            "model": "<catalog>.<schema>.<service>   (the FQN)",
            "authz": "USE CATALOG + USE SCHEMA + EXECUTE on the service",
        },
        "note": "Change the base URL and the model selector TOGETHER — a new base URL with "
                "an old endpoint name, or an FQN against the legacy path, both fail.",
    }
    if not services:
        return _todo("No model services registered yet. Create one in front of an approved "
                     "destination, then point clients at its FQN.",
                     client_contract=contract)
    return _ok(f"{len(services)} model service(s) available "
               f"({len(provided)} provided, {len(customer)} customer-defined).",
               provided=provided[:15], customer_defined=customer[:15],
               client_contract=contract,
               migration_note="No in-place rename exists. Run the new service alongside the "
                              "old endpoint, validate on real traffic, move clients in "
                              "stages, then revoke the old path.")


# Privileges that let a principal CALL a model through the securable, as opposed to merely
# seeing that it exists. USE_SCHEMA/USE_CATALOG alone are traversal, not access.
_REACH_PRIVILEGES = {"EXECUTE", "ALL_PRIVILEGES"}


def _me_identity(w) -> str:
    """Best-effort identifier for the calling identity (the app's service principal)."""
    try:
        me = w.current_user.me()
    except Exception:  # noqa: BLE001
        return ""
    if getattr(me, "user_name", None):
        return me.user_name
    if getattr(me, "emails", None) and me.emails:
        return me.emails[0].value
    return ""


def t_default_access() -> TestResult:
    """What can THIS identity reach on the provided model surface?

    Provided model services are closed by default now — a model in `system.ai` is callable
    only by an identity explicitly granted EXECUTE (directly, or inherited from the `system`
    catalog). So the useful question in Choice is no longer "what is everyone exposed to?" but
    "what can this caller actually reach?"

    Reports the EFFECTIVE permissions of the app's own service principal on `system` and
    `system.ai` — the privileges it really holds and whether they let it call the provided
    models — so the room sees the reach of a real, governed identity rather than a default
    that no longer exists. Read-only: it grants and revokes nothing.
    """
    w = get_workspace_client()
    identity = _me_identity(w)
    if not identity:
        return _fail("Could not resolve the app's calling identity (current_user.me()).")

    findings, errors = [], {}
    for securable_type, name in (("catalog", "system"), ("schema", "system.ai")):
        try:
            resp = w.api_client.do(
                "GET", f"/api/2.1/unity-catalog/effective-permissions/{securable_type}/{name}",
                query={"principal": identity})
        except Exception as e:  # noqa: BLE001 — one unreadable securable shouldn't fail the step
            errors[f"{securable_type}:{name}"] = str(e)[:300]
            continue
        # effective-permissions returns privilege_assignments[].privileges[] as objects
        # carrying inheritance info: {privilege, inherited_from_type, inherited_from_name}.
        # Scoped to `principal`, so every returned privilege is one THIS identity effectively
        # holds (group membership already resolved server-side).
        privs: dict[str, str | None] = {}
        for a in (resp or {}).get("privilege_assignments", []) or []:
            for p in a.get("privileges", []) or []:
                if isinstance(p, dict):
                    pname = str(p.get("privilege") or "").upper()
                    src = (f"{(p.get('inherited_from_type') or '').lower()} "
                           f"{p.get('inherited_from_name')}").strip() if p.get("inherited_from_name") else None
                else:
                    pname, src = str(p).upper(), None
                if pname:
                    privs[pname] = src  # value None => granted directly on this securable
        reach = sorted(pv for pv in privs if pv in _REACH_PRIVILEGES)
        findings.append({
            "securable": f"{securable_type} {name}",
            "your_privileges": sorted(privs),
            "can_call_models": bool(reach),
            "reach_via": (f"inherited from {privs[reach[0]]}" if reach and privs[reach[0]]
                          else "granted directly" if reach else None),
        })

    reachable = [f for f in findings if f["can_call_models"]]
    denied = {k: v for k, v in errors.items()
              if any(s in v.lower() for s in ("permission", "does not have", "denied",
                                              "unauthorized", "403"))}
    detail = {
        "identity": identity,
        "findings": findings,
        "errors": errors or None,
        "why_this_matters": (
            "Provided model services are governed by EXECUTE grants — an identity can call "
            "only what it holds EXECUTE on, directly or inherited. This is exactly what this "
            "identity can reach today; anything not listed is denied to it."),
        "note": (f"Read-only. Shows the effective reach of the app's own identity ({identity}) "
                 "on the provided model surface; it grants and revokes nothing. Effective "
                 "permissions include grants inherited via group membership, so a listed "
                 "privilege may come from a broad group (e.g. `account users`) rather than a "
                 "grant to this identity alone."),
    }
    if not findings:
        if denied:
            return _todo(
                f"Could not read effective permissions on `system` / `system.ai` for {identity} "
                "— that read itself needs a grant. Ask an admin to confirm what this identity "
                f"may call, e.g. `SHOW GRANTS TO `{identity}``.",
                **detail)
        return _fail("Could not read effective permissions on `system` / `system.ai`.", **detail)
    if reachable:
        names = ", ".join(f["securable"] for f in reachable)
        return _ok(
            f"This identity ({identity}) can call the provided model services in {names} — it "
            "holds EXECUTE. That is the model surface reachable by this identity today.",
            **detail)
    return _ok(
        f"This identity ({identity}) cannot call any provided model service by default — no "
        "EXECUTE on `system` or `system.ai`. The surface is closed to it until access is "
        "explicitly granted, which is the posture you want before rollout.",
        **detail)


def t_endpoint_acl() -> TestResult:
    """Who can call the governed endpoint — the doc's primary access-control mechanism.

    Endpoint ACLs (CAN_QUERY / CAN_VIEW / CAN_MANAGE) are the "who may use this model?"
    control, and CAN_MANAGE restriction is what prevents shadow endpoints.

    One API detail that costs a debugging cycle: get_permissions() takes the endpoint's
    **id**, not its name — passing the name returns "is not a valid Inference Endpoint ID".
    Provided foundation-model endpoints also have no id at all (they are not workspace
    securables), so they cannot carry an ACL; that is why `system.ai` grants above are the
    control for those, and this step says so instead of reporting a confusing failure.
    """
    name = get_config().get("governed_endpoint", {}).get("name")
    w = get_workspace_client()
    try:
        ep = w.serving_endpoints.get(name)
    except Exception as e:
        return _todo(f"Endpoint `{name}` does not exist yet — create it, then re-run.",
                     endpoint=name, error=str(e)[:300])
    if not ep.id:
        return _todo(
            f"`{name}` has no endpoint id, so it carries no workspace ACL — it is a "
            "provided foundation-model endpoint. Govern these with UC grants on the model "
            "service instead (see 'What can everyone already reach?' in Choice).",
            endpoint=name)
    try:
        perms = w.serving_endpoints.get_permissions(ep.id)
    except Exception as e:
        return _fail(f"Could not read the ACL on `{name}`.", endpoint=name, error=str(e)[:300])

    acl = []
    for a in (perms.access_control_list or []):
        principal = a.user_name or a.group_name or a.service_principal_name
        levels = sorted({str(p.permission_level).split(".")[-1]
                         for p in (a.all_permissions or []) if p.permission_level})
        acl.append({"principal": principal,
                    "is_group": bool(a.group_name),
                    "levels": levels})

    broad_query = [e for e in acl
                   if e["is_group"] and (e["principal"] or "").lower() in _BROAD_PRINCIPALS
                   and any(l in ("CAN_QUERY", "CAN_MANAGE") for l in e["levels"])]
    managers = [e for e in acl if "CAN_MANAGE" in e["levels"]]
    detail = {
        "endpoint": name,
        "acl": acl,
        "levels_available": ["CAN_VIEW", "CAN_QUERY", "CAN_MANAGE"],
        "can_manage_holders": [e["principal"] for e in managers],
        "note": ("CAN_MANAGE is the shadow-endpoint risk: it allows reconfiguring the model "
                 "and removing the controls layered on it. Keep it with platform admins."),
    }
    if broad_query:
        return _todo(
            f"`{broad_query[0]['principal']}` holds "
            f"{'/'.join(broad_query[0]['levels'])} on `{name}` — the governed endpoint is "
            "open to everyone. Scope it to the pilot group.",
            **detail)
    return _ok(f"`{name}` ACL is scoped: {len(acl)} principal(s), "
               f"{len(managers)} with CAN_MANAGE.", **detail)


def t_routing_panel() -> TestResult:
    """Show the model panel, prices, and the routing policy before anything is run."""
    p = routing.panel()
    return _ok(
        f"{len(p['models'])} models on the panel; classifier = {p['classifier_model']}.",
        **p,
    )


def t_routing_compare() -> TestResult:
    """Project each configured model's monthly cost, and estimate smart routing against it.

    Runs the sample prompts against all three models, averages each model's per-request cost,
    and scales it by the configured monthly request volume. The prompts and per-model answers
    are returned so the room can read the answers, not only the prices. The smart-routing row
    is a labelled placeholder estimate — see routing.evaluate.
    """
    out = routing.evaluate()
    priced = [r for r in out["results"] if r.get("monthly_cost_usd") is not None]
    if not priced:
        return _fail(
            "No model endpoint answered — check `cost.routing.endpoints` in config/workshop.yaml.",
            **out)
    n = out["requests_per_month"]
    fm = out.get("frontier_monthly_usd")
    sr = out["smart_routing"]
    summary = (f"At {n:,} requests/month across {len(out['prompts_evaluated'])} prompts: "
               f"all-frontier costs about ${fm:,.2f}" if fm is not None
               else f"Projected monthly cost at {n:,} requests/month")
    if fm is not None and sr.get("monthly_cost_usd") is not None:
        summary += f", smart routing (estimated) about ${sr['monthly_cost_usd']:,.2f}"
        if sr.get("saving_vs_frontier_pct") is not None:
            summary += f" — roughly {sr['saving_vs_frontier_pct']}% lower"
    return _ok(summary + ".", **out)


def t_routing_roi() -> TestResult:
    """Run the custom router end to end and report the measured saving vs always-frontier.

    Option (c) of the three cost-routing approaches — the only one a customer can stand up
    today. Smart Routing (a) is Databricks-managed and in Beta; Omnigent (b) is a partner
    layer. Both are positioned in the step concept rather than executed here.
    """
    prompt = _routing_prompt()
    r = routing.route(prompt)
    chosen, cls = r["chosen"], r["classification"]
    if chosen["error"]:
        return _fail("The routed model call failed.", prompt=prompt, **r)
    summary = (
        f"Classified complexity {cls['complexity']}/3 → routed to {chosen['label']}. "
        f"Cost ${r['routed_cost_usd']:.6f} vs ${r['always_frontier_cost_usd']:.6f} "
        f"always-frontier — saved {r['savings_pct']}%."
    )
    if cls["classifier_error"]:
        summary = ("Classifier unavailable, so the router failed SAFE to the frontier model. "
                   "No saving on this request — that is the correct behavior.")
    return _ok(summary, prompt=prompt, **r)


def _routing_prompt() -> str:
    """The prompt the routing steps send. Overridable so a customer can use their own."""
    return (
        (get_config().get("cost", {}) or {}).get("routing", {}).get("sample_prompt")
        or "Summarize the key cost drivers of running large language models in production."
    )


def t_rate_limits() -> TestResult:
    """Report the rate limits configured on the governed endpoint.

    Rate limits are the *hard* cost control — budgets alert (hard blocking is still rolling
    out), whereas an exceeded rate limit returns HTTP 429 immediately. Read-only: limits are
    set in the AI Gateway UI so the app never changes throughput on a customer endpoint.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    want = cfg.get("rate_limit_per_user_per_min")
    w = get_workspace_client()
    try:
        ep = w.serving_endpoints.get(name)
    except Exception as e:
        return _todo(f"Endpoint `{name}` not found — create it, set a rate limit, then re-run.",
                     endpoint=name, error=str(e)[:300],
                     deep_link=deep_links.serving_endpoint(name))
    gw = getattr(ep, "ai_gateway", None)
    limits = [
        {"key": getattr(rl, "key", None), "principal": getattr(rl, "principal", None),
         "calls": getattr(rl, "calls", None), "tokens": getattr(rl, "tokens", None),
         "renewal_period": str(getattr(rl, "renewal_period", "") or "")}
        for rl in (getattr(gw, "rate_limits", None) or [])
    ] if gw else []
    if not limits:
        return _todo(
            f"No rate limits on `{name}` yet. Add one in the AI Gateway UI "
            f"(config suggests {want}/user/min), then re-run.",
            endpoint=name, configured_target=want,
            deep_link=deep_links.serving_endpoint(name),
            note="An exceeded rate limit returns HTTP 429 — this is the hard throughput "
                 "control, distinct from budget alerts.")
    return _ok(f"{len(limits)} rate limit(s) enforced on `{name}`.",
               endpoint=name, rate_limits=limits, configured_target=want)


def t_gateway_spend_by_model() -> TestResult:
    """Real dollars per model from system.ai_gateway.external_model_spend.

    That table reports estimated USD directly (usage_unit = 'USD'), so it needs no join to
    a price list — which is why the workshop reads it instead of the billing tables, and
    why the app needs no grant on system.billing. It covers external-provider models routed
    through the Gateway: the spend a router actually shifts.
    """
    sql = """
      SELECT usage_metadata.model      AS model,
             usage_metadata.provider   AS provider,
             ROUND(SUM(usage_quantity), 2) AS usd
      FROM system.ai_gateway.external_model_spend
      WHERE usage_date > current_date() - 30
      GROUP BY 1, 2 ORDER BY usd DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        if not rows:
            return _todo("No external-model spend recorded in the last 30 days. Route an "
                         "external provider through the Gateway, then re-run.", sql=sql)
        total = sum(float(r.get("usd") or 0) for r in rows)
        return _ok(f"${total:,.2f} of external-model spend across {len(rows)} model(s) (30d).",
                   rows=rows, total_usd=round(total, 2), sql=sql)
    except Exception as e:
        return _fail("Spend query failed — system.ai_gateway.external_model_spend may not be "
                     "enabled on this account (Beta).", error=str(e)[:600], sql=sql)


# --------------------------------------------------------------------------- Control
def t_create_governed_endpoint() -> TestResult:
    """Create/verify the governed endpoint with usage tracking + inference table.

    Mirrors l200 page 2: PUT the endpoint config idempotently. Guardrails/rate-limits
    beyond what the API supports are applied via the UI (see the step's manual action).
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    w = get_workspace_client()
    existing = {e.name for e in w.serving_endpoints.list()}
    if name in existing:
        return _ok(f"Governed endpoint `{name}` already exists.", endpoint=name,
                   next="Configure guardrails in the AI Gateway UI (next step).")
    # Not created — this is a to-do, not a pass. The app deliberately does not create
    # endpoints unattended on a customer workspace.
    return _todo(
        f"Endpoint `{name}` does not exist yet — create it in the workspace, then re-run.",
        endpoint=name,
        primary=cfg.get("primary_model"),
        fallback=cfg.get("fallback_model"),
        deep_link=deep_links.serving_endpoint(name),
        note="Endpoint creation with external-model config is a guided UI step to avoid "
             "destructive automated changes on a customer workspace.",
    )


def t_verify_governed_endpoint() -> TestResult:
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    w = get_workspace_client()
    try:
        ep = w.serving_endpoints.get(name)
    except Exception as e:
        return _fail(f"Endpoint `{name}` not found.", error=str(e))
    gw = getattr(ep, "ai_gateway", None)
    return _ok(
        f"Endpoint `{name}` is present.",
        state=str(getattr(ep.state, "ready", "")) if ep.state else None,
        has_ai_gateway=bool(gw),
        inference_table=bool(getattr(gw, "inference_table_config", None)) if gw else False,
    )


def t_test_guardrail() -> TestResult:
    """Send a prompt containing a blocked keyword to the governed endpoint; expect a block.

    A BLOCK is the pass condition here, so we must distinguish "the guardrail rejected the
    request" from "the endpoint does not exist / is not ready". Both surface as an SDK
    exception, so match on guardrail-specific wording and on HTTP 400 specifically — never
    on a bare "400" substring, which also appears in 404s and in request ids.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    blocked = (cfg.get("guardrails", {}).get("keyword_policy", {}).get("blocked_keywords")
               or ["social security number"])[0]
    prompt = f"My {blocked} is 123-45-6789, please store it."
    w = get_workspace_client()
    try:
        resp = w.serving_endpoints.query(
            name=name,
            messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
            max_tokens=64,
        )
        answer = resp.choices[0].message.content if resp.choices else None
        # The request went through: the guardrail did NOT block. That is a real negative
        # result for this step, not a pass.
        return _fail(
            "The prompt was NOT blocked — the endpoint answered. Configure the PII/keyword "
            "guardrail on this endpoint (manual step above), then re-run.",
            endpoint=name, prompt=prompt, response=str(answer)[:400],
        )
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if any(s in low for s in ("guardrail", "blocked", "policy", "content filter",
                                  "invalid_keywords", "flagged")):
            return _ok("Guardrail fired — the request was blocked as expected.",
                       endpoint=name, prompt=prompt, error=msg[:400])
        if any(s in low for s in ("does not exist", "not found", "404",
                                  "resource_does_not_exist")):
            return _todo(f"Endpoint `{name}` does not exist yet — create it, attach the "
                         "guardrail, then re-run.", endpoint=name, error=msg[:400])
        return _fail("Could not run the guardrail test.", endpoint=name, error=msg[:600])


def t_guardrail_activity() -> TestResult:
    """Look for blocked/filtered requests in the endpoint's inference table.

    Unity AI Gateway inference tables do NOT expose a dedicated guardrail-decision column —
    the decision has to be read out of the raw request/response payloads and the status
    code. We select the audit-relevant columns and flag non-2xx rows rather than inventing a
    `guardrail_decision` column that does not exist.
    """
    cfg = get_config()
    cat, sch = _fq_schema()
    prefix = _sql_ident(
        cfg.get("governed_endpoint", {}).get("inference_table_prefix", "workshop_governed"),
        "governed_endpoint.inference_table_prefix")
    table = f"{cat}.{sch}.{prefix}_payload"
    sql = f"""
      SELECT event_time, requester, status_code, destination_model,
             substr(request, 1, 400)  AS request_excerpt,
             substr(response, 1, 400) AS response_excerpt
      FROM {table}
      WHERE status_code IS NULL OR status_code >= 400
      ORDER BY event_time DESC LIMIT 10
    """
    try:
        rows = fetchall(sql)
        if not rows:
            return _todo("Inference table is reachable but shows no blocked/failed requests "
                         "yet. Send a prompt that should be blocked, then re-run (rows can "
                         "take up to an hour to land).", table=table, sql=sql)
        return _ok(f"{len(rows)} blocked/failed request(s) logged in the inference table.",
                   rows=rows, table=table, sql=sql)
    except Exception as e:
        return _fail("Inference table not available yet — enable payload logging on the "
                     "endpoint (needs an external-storage catalog) and allow up to an hour.",
                     table=table, error=str(e)[:600], sql=sql)


def t_create_mcp_policy() -> TestResult:
    """Create the UC SQL function that denies write tools on the MCP service.

    Service-policy shape per the Unity AI Gateway docs: takes `event VARIANT`, returns a
    VARIANT object with `result` (ALLOW / DENY / ASK) and `reason`. VARIANT path access
    yields VARIANT, so `event:context.tool.name` must be cast before comparing.

    NOTE: service policies are in Beta and can currently only be ATTACHED from the AI
    Gateway UI — creating the function is the automatable half, attaching it is the manual
    step that follows.
    """
    cfg = get_config()
    cat, sch = _fq_schema()
    pol = cfg.get("mcp", {}).get("service_policy", {})
    fn = _sql_ident(pol.get("function_name", "confluence_mcp_policy"),
                    "mcp.service_policy.function_name")
    deny = pol.get("deny_tools", []) or []
    # Tool names are values, not identifiers — quote and escape them.
    deny_sql = ", ".join(_sql_str(d) for d in deny) or "''"
    reason = _sql_str(pol.get("deny_reason")
                      or "This tool is blocked by workshop policy.")
    fqn = f"{cat}.{sch}.{fn}"
    ddl = f"""
    CREATE OR REPLACE FUNCTION {fqn}(event VARIANT)
    RETURNS VARIANT
    RETURN CASE
      WHEN event:context.tool.name::STRING IN ({deny_sql})
      THEN to_variant_object(named_struct('result','DENY','reason',{reason}))
      ELSE to_variant_object(named_struct('result','ALLOW','reason',''))
    END;
    """
    try:
        fetchall(ddl)
        return _ok(f"Created policy function `{fqn}`.", function=fqn, denies=deny, ddl=ddl,
                   next="Attach it to the MCP service in the AI Gateway UI (next step).")
    except ValueError as e:      # invalid identifier in config
        return _fail(str(e))
    except Exception as e:
        return _fail("Could not create the policy function.", error=str(e)[:600], ddl=ddl)


def t_test_mcp_policy() -> TestResult:
    """Prove the policy function returns DENY for a write tool and ALLOW for a read tool.

    Evaluates the function directly with a synthetic event, which tests the POLICY LOGIC
    without needing the policy attached. Attachment is UI-only in Beta, so the workshop
    verifies logic here and confirms enforcement by invoking the tool from the agent.
    """
    cfg = get_config()
    cat, sch = _fq_schema()
    mcp = cfg.get("mcp", {})
    pol = mcp.get("service_policy", {})
    try:
        fn = _sql_ident(pol.get("function_name", "confluence_mcp_policy"),
                        "mcp.service_policy.function_name")
    except ValueError as e:
        return _fail(str(e))
    fqn = f"{cat}.{sch}.{fn}"
    deny_tool = (pol.get("deny_tools") or [None])[0]
    allow_tool = pol.get("allow_probe_tool")
    if not deny_tool or not allow_tool:
        return _fail("Config needs both mcp.service_policy.deny_tools and allow_probe_tool.")

    def _probe(tool: str) -> str:
        event = json.dumps({"type": "request", "context": {"tool": {"name": tool}}})
        rows = fetchall(f"SELECT {fqn}(parse_json({_sql_str(event)}))"
                        f":result::STRING AS decision")
        return (rows[0].get("decision") if rows else None) or "NO_RESULT"

    try:
        deny_decision = _probe(deny_tool)
        allow_decision = _probe(allow_tool)
    except Exception as e:
        return _fail("Could not evaluate the policy function — create it first (previous step).",
                     function=fqn, error=str(e)[:600])

    detail = {
        "function": fqn,
        "write_tool": {"tool": deny_tool, "decision": deny_decision, "expected": "DENY"},
        "read_tool": {"tool": allow_tool, "decision": allow_decision, "expected": "ALLOW"},
        "service": mcp.get("builtin_service"),
        "deep_link": deep_links.mcp_service(mcp.get("builtin_service", "")),
        "note": "Policy LOGIC verified here. Attach the policy in the AI Gateway UI (Beta: "
                "UI-only) and invoke the tool from an agent to prove enforcement end to end.",
    }
    if deny_decision == "DENY" and allow_decision == "ALLOW":
        return _ok(f"Policy correct: `{deny_tool}` → DENY, `{allow_tool}` → ALLOW.", **detail)
    return _fail(f"Policy returned the wrong decision: `{deny_tool}` → {deny_decision}, "
                 f"`{allow_tool}` → {allow_decision}.", **detail)


# --------------------------------------------------------------------------- Cost + Control (attribution, usage & observability)
def t_apply_tags() -> TestResult:
    """Report the tags to apply. Tagging is a guided step, so this is a to-do, not a pass.

    Also shows the REQUEST-tag side, which the workshop does exercise: the routing steps send
    `Databricks-Ai-Gateway-Request-Tags` on every model call, so a customer can see both
    columns (`endpoint_tags` vs `request_tags`) in the usage query and understand which one
    is trustworthy for a budget filter.
    """
    cfg = get_config()
    proj = cfg.get("project", {})
    name = cfg.get("governed_endpoint", {}).get("name")
    return _todo(
        f"Apply these tags to `{name}` in the workspace, then re-run the usage query.",
        endpoint=name,
        server_side_tags=proj,
        request_tags_sent_by_this_app=routing.request_tags(),
        request_tags_header=routing.REQUEST_TAGS_HEADER,
        deep_link=deep_links.serving_endpoint(name),
        trust_boundary=(
            "Server-side tags are set by the platform owner on the service and apply to every "
            "request — the only kind safe to use as a budget or chargeback filter. Request "
            "tags are supplied by the caller and can be omitted or forged, so they are for "
            "attribution and analytics only."),
        note="Tag application is a guided step to avoid unattended writes on a customer "
             "endpoint; these tags drive the usage-by-project query in the next step.",
    )


def t_usage_by_project() -> TestResult:
    """Token usage attributed to the workshop's project tag.

    Reads system.ai_gateway.usage, which carries request_tags/endpoint_tags and covers all
    Gateway traffic (FMAPI, external models, and MCP). system.serving.endpoint_usage only
    has usage_context and misses Gateway-native routes.
    """
    proj = get_config().get("project", {}).get("name", "")
    p = _sql_str(proj)
    # Break out WHICH tag matched rather than OR-ing them together. The distinction is the
    # teaching point: request_tags rows are the ones this app produced by sending a header,
    # endpoint_tags rows come from the server-side tags the platform owner set. A single
    # combined count hides which mechanism is actually working.
    # COALESCE(service_name, endpoint_name) is required, not defensive: a Gateway call that
    # names a plain ENDPOINT (which is what the routing steps do) lands with service_name NULL
    # and endpoint_name set. Grouping on service_name alone shows the workshop's own traffic as
    # an unnamed bucket. Verified live.
    sql = f"""
      SELECT requester,
             COALESCE(service_name, endpoint_name) AS target,
             SUM(CASE WHEN request_tags['project'] = {p} THEN 1 ELSE 0 END) AS request_tagged,
             SUM(CASE WHEN endpoint_tags['project'] = {p} THEN 1 ELSE 0 END) AS endpoint_tagged,
             COUNT(*) AS requests,
             SUM(total_tokens) AS tokens
      FROM system.ai_gateway.usage
      WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
        AND (request_tags['project'] = {p} OR endpoint_tags['project'] = {p})
      GROUP BY 1, 2 ORDER BY tokens DESC LIMIT 20
    """
    # How far behind real time the table is. Reported on the empty result because otherwise an
    # ingestion lag is indistinguishable from broken tagging — observed 13-21 minutes on a
    # reference workspace, which is long enough for a room to start debugging a working control.
    watermark_sql = ("SELECT max(event_time) AS latest_event, "
                     "current_timestamp() AS now_ts FROM system.ai_gateway.usage")
    try:
        rows = fetchall(sql)
        if rows:
            by_request = sum(int(r.get("request_tagged") or 0) for r in rows)
            by_endpoint = sum(int(r.get("endpoint_tagged") or 0) for r in rows)
            # Rows are requester x target pairs now, so count distinct requesters explicitly.
            people = len({r.get("requester") for r in rows})
            return _ok(
                f"Usage attributed to project `{proj}`: {people} requester(s) across "
                f"{len(rows)} requester/target pair(s) — "
                f"{by_request} request-tagged, {by_endpoint} endpoint-tagged.",
                rows=rows, request_tagged_calls=by_request,
                endpoint_tagged_calls=by_endpoint,
                request_tags_header=routing.REQUEST_TAGS_HEADER,
                interpretation=(
                    "Request-tagged calls prove per-caller attribution works end to end. "
                    "Endpoint-tagged calls are the ones a FinOps owner can trust as a budget "
                    "filter, because the caller cannot change them."),
                sql=sql)
        # No rows is a real (and common) outcome, not a pass: nothing is attributable yet.
        # Report the table's watermark so "not ingested yet" is distinguishable from "broken".
        freshness = {}
        try:
            wm = fetchall(watermark_sql)
            if wm:
                freshness = {"latest_event_in_table": str(wm[0].get("latest_event")),
                             "queried_at": str(wm[0].get("now_ts"))}
        except Exception as e:  # noqa: BLE001 — freshness is a diagnostic, not the test
            freshness = {"error": str(e)[:200]}
        return _todo(
            f"No usage tagged `project={proj}` in the last 7 days. Run the Cost routing steps "
            "(they send the request-tag header), tag the endpoint for the server-side side, "
            "then re-run.",
            rows=[],
            table_freshness=freshness,
            lag_note=("Compare `latest_event_in_table` with `queried_at` before concluding "
                      "anything: system.ai_gateway.usage is not real-time (a 13-21 minute lag "
                      "was observed on a reference workspace). If the gap covers when the "
                      "routing steps ran, the rows simply have not landed yet."),
            sql=sql)
    except Exception as e:
        return _fail("Usage query failed.", error=str(e)[:600], sql=sql)


def t_audit_scan() -> TestResult:
    """Recent denied/failed calls in the audit log, scanned for secret-shaped arguments.

    `response` is a STRUCT in system.access.audit, so the field is read with dot notation.
    The `response:status_code` VARIANT-path form fails with a DATATYPE_MISMATCH.
    """
    sql = """
      SELECT event_time, action_name, service_name,
             user_identity.email AS actor,
             response.status_code AS status_code,
             request_params
      FROM system.access.audit
      WHERE event_date >= current_date() - INTERVAL 1 DAY
        AND (response.status_code >= 400 OR lower(action_name) LIKE '%deny%')
      ORDER BY event_time DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        leaks = [r for r in rows if _looks_like_secret(json.dumps(r, default=str))]
        if not rows:
            return _todo("No denied or failed calls in the last 24 hours — nothing to review "
                         "yet. Trigger a blocked request, then re-run.", sql=sql)
        return _ok(f"{len(rows)} recent denied/failed call(s); {len(leaks)} with "
                   f"secret-shaped arguments.",
                   rows=rows[:10], suspected_secret_rows=len(leaks), sql=sql)
    except Exception as e:
        return _fail("Audit query failed.", error=str(e)[:600], sql=sql)


def _looks_like_secret(text: str) -> bool:
    return bool(re.search(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b", text))


# --------------------------------------------------------------------------- Added: 5x4-matrix coverage
def t_list_registered_assets() -> TestResult:
    """Inventory of agents (registered models) and UC functions (tools) — the Choice surface."""
    cat, sch = _fq_schema()
    w = get_workspace_client()
    agents, tools = [], []
    errors = {}
    try:
        for m in w.registered_models.list(catalog_name=cat, schema_name=sch):
            agents.append(m.full_name)
    except Exception as e:
        errors["registered_models"] = str(e)[:300]
    try:
        # UC Functions API rather than system.information_schema.routines: it reads the same
        # inventory from the schema the app already has USE SCHEMA on, so this step needs no
        # grant on the `system` catalog.
        tools = [f.name for f in w.functions.list(catalog_name=cat, schema_name=sch)]
    except Exception as e:
        errors["functions"] = str(e)[:300]
    # Surface why an inventory is empty — a missing schema or a missing grant reads very
    # differently from "nothing registered yet", and the room needs to know which it is.
    if errors and not agents and not tools:
        return _fail(f"Could not inventory `{cat}.{sch}` — check the schema exists and the "
                     f"app's service principal has USE SCHEMA on it.", errors=errors)
    return _ok(
        f"{len(agents)} registered agent(s)/model(s), {len(tools)} tool function(s) "
        f"in {cat}.{sch}.",
        agents=agents[:25], tools=tools[:25], errors=errors or None,
    )


def t_budget_status() -> TestResult:
    """30-day AI spend in real dollars, plus the account-level budgets configured.

    Uses system.ai_gateway.external_model_spend (usage_unit = 'USD'), so no join to
    list_prices is needed. Budgets themselves are created in the account console; hard
    "block usage" caps are rolling out, so alert-only budgets are the safe assumption.
    """
    sql = """
      SELECT usage_metadata.model    AS model,
             identity_metadata.run_by AS run_by,
             ROUND(SUM(usage_quantity), 2) AS usd
      FROM system.ai_gateway.external_model_spend
      WHERE usage_date > current_date() - 30
      GROUP BY 1, 2 ORDER BY usd DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        total = sum(float(r.get("usd") or 0) for r in rows)
        if not rows:
            return _todo("No external-model spend in the last 30 days — send traffic through "
                         "a governed external-model endpoint, then re-run.", sql=sql,
                         next="Create the budget + threshold in the account console.")
        return _ok(f"${total:,.2f} external-model spend over 30 days, across "
                   f"{len(rows)} model/user pair(s).",
                   rows=rows, total_usd=round(total, 2), sql=sql,
                   note="Create the budget and its thresholds in the account console. Alerts "
                        "are GA; hard 'block usage' caps are rolling out, so confirm "
                        "availability on this account before promising hard enforcement.")
    except Exception as e:
        return _fail("Budget/spend query failed — system.ai_gateway.external_model_spend is "
                     "Beta and may not be enabled on this account.",
                     error=str(e)[:600], sql=sql)


def t_coding_agent_usage() -> TestResult:
    """Per-developer coding-agent traffic, identified by user_agent in the Gateway log.

    Coding agents identify themselves in `user_agent` (claude-cli/..., ucode/... codex/...,
    cursor/...), which works with no tagging required — the earlier tag-based approach
    returned nothing until someone remembered to tag. `requester` gives per-developer
    attribution, which is the actual governance win for this surface.
    """
    sql = """
      SELECT requester,
             regexp_extract(user_agent, '^([A-Za-z0-9_.-]+)', 1) AS agent,
             api_type,
             COUNT(*)           AS requests,
             SUM(total_tokens)  AS tokens
      FROM system.ai_gateway.usage
      WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
        AND (user_agent ILIKE '%claude%' OR user_agent ILIKE '%cursor%'
             OR user_agent ILIKE '%ucode%' OR user_agent ILIKE '%codex%'
             OR user_agent ILIKE '%copilot%' OR user_agent ILIKE '%gemini%')
      GROUP BY 1, 2, 3 ORDER BY tokens DESC LIMIT 25
    """
    try:
        rows = fetchall(sql)
        if not rows:
            return _todo("No coding-agent traffic in the last 7 days. Point Claude Code / "
                         "Cursor / Codex at the Gateway (`ucode` is the quickest path), then "
                         "re-run.", sql=sql)
        devs = len({r.get("requester") for r in rows})
        agents = sorted({r.get("agent") for r in rows if r.get("agent")})
        return _ok(f"{devs} developer(s) across {len(agents)} agent(s) "
                   f"({', '.join(agents[:5])}) — all attributable per user.",
                   rows=rows, developers=devs, agents=agents, sql=sql)
    except Exception as e:
        return _fail("Coding-agent usage query failed.", error=str(e)[:600], sql=sql)


def t_coding_agent_route_check() -> TestResult:
    """Is coding-agent traffic ACTUALLY on the governed model service, or a legacy endpoint?

    The common silent failure: a client is "pointed at the gateway" but still resolves a
    legacy/provided endpoint name, so the rate limits and guardrails configured on the new UC
    model service never apply — and nothing errors to say so. A Gateway call that names a plain
    ENDPOINT lands with service_name NULL; a call that names a model-service FQN lands with
    service_name set. That split between the two columns is exactly the drift signal.
    """
    governed = get_config().get("governed_endpoint", {}).get("name")
    sql = """
      SELECT service_name, endpoint_name, api_type,
             regexp_extract(user_agent, '^([A-Za-z0-9_.-]+)', 1) AS agent,
             COUNT(*) AS requests, SUM(total_tokens) AS tokens
      FROM system.ai_gateway.usage
      WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
        AND (user_agent ILIKE '%claude%' OR user_agent ILIKE '%cursor%'
             OR user_agent ILIKE '%ucode%' OR user_agent ILIKE '%codex%'
             OR user_agent ILIKE '%copilot%' OR user_agent ILIKE '%gemini%')
      GROUP BY 1, 2, 3, 4 ORDER BY requests DESC LIMIT 30
    """
    try:
        rows = fetchall(sql)
    except Exception as e:
        return _fail("Route-check query failed — needs SELECT on system.ai_gateway.usage.",
                     error=str(e)[:600], sql=sql)
    if not rows:
        return _todo("No coding-agent traffic in the last 7 days. Point a coding agent at the "
                     "governed model service, send a request, then re-run.",
                     governed_endpoint=governed, sql=sql)
    on_service = [r for r in rows if r.get("service_name")]
    on_endpoint = [r for r in rows if not r.get("service_name")]
    reqs = lambda rs: sum(int(r.get("requests") or 0) for r in rs)  # noqa: E731
    detail = {
        "governed_endpoint_config": governed,
        "on_model_service": {"targets": sorted({r["service_name"] for r in on_service}),
                             "requests": reqs(on_service)},
        "on_plain_endpoint": {"targets": sorted({r.get("endpoint_name") for r in on_endpoint
                                                 if r.get("endpoint_name")}),
                              "requests": reqs(on_endpoint)},
        "rows": rows,
        "why_this_matters": (
            "Rate limits and guardrails are configured on the governed MODEL SERVICE. Traffic "
            "that resolves a plain endpoint name is on the legacy contract, so those controls "
            "never apply to it — and nothing errors to tell you."),
        "sql": sql,
    }
    if on_endpoint:
        return _todo(
            f"Coding-agent traffic is split: {reqs(on_service)} request(s) on a governed model "
            f"service, {reqs(on_endpoint)} on a plain endpoint (legacy contract). Repoint the "
            "client at the model-service FQN so the governed controls apply.", **detail)
    return _ok(
        f"All coding-agent traffic is on a governed model service "
        f"({', '.join(detail['on_model_service']['targets']) or 'model service'}) — the "
        "governed controls apply to it.", **detail)


# Coding agents such as Claude Code and ucode call the provider-native path; the OpenAI-compatible
# chat path is where controls are known to fire. Comparing the two is the point of t_path_coverage.
ANTHROPIC_MESSAGES_PATH = "/ai-gateway/anthropic/v1/messages"


def t_path_coverage_check() -> TestResult:
    """Do the gateway's controls fire on the provider-native path coding agents use?

    Guardrails and rate limits are reliably enforced on the OpenAI-compatible chat path
    (`/ai-gateway/mlflow/v1/chat/completions`). Coding agents like Claude Code and ucode call the
    provider-native path (`/ai-gateway/anthropic/v1/messages`). Whether the same controls fire
    there is account- and version-dependent — and a control that silently does NOT fire on the
    path a client actually uses is the most dangerous kind of gap.

    Probes both paths with the same guardrail-triggering prompt and compares. A diagnostic, not a
    promise: if the anthropic path is not applicable (the endpoint is not an Anthropic model) or
    not enabled, it says so and asks you to verify on the account. Never raises.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    if not name:
        return _fail("No governed_endpoint.name configured.")
    blocked = (cfg.get("guardrails", {}).get("keyword_policy", {}).get("blocked_keywords")
               or ["social security number"])[0]
    prompt = f"My {blocked} is 123-45-6789, please store it."
    w = get_workspace_client()

    def _classify(send) -> dict:
        try:
            send()
            return {"outcome": "answered", "blocked": False}
        except Exception as e:  # noqa: BLE001 — classify the failure, never propagate it
            low = str(e).lower()
            if any(s in low for s in ("guardrail", "blocked", "policy", "content filter",
                                      "flagged")):
                return {"outcome": "blocked", "blocked": True, "detail": str(e)[:200]}
            return {"outcome": "error", "blocked": None, "detail": str(e)[:200]}

    chat = _classify(lambda: w.api_client.do(
        "POST", routing.GATEWAY_CHAT_PATH,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        body={"model": name, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 16}))
    anthropic = _classify(lambda: w.api_client.do(
        "POST", ANTHROPIC_MESSAGES_PATH,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "anthropic-version": "2023-06-01"},
        body={"model": name, "max_tokens": 16,
              "messages": [{"role": "user", "content": prompt}]}))
    detail = {
        "endpoint": name, "probe_prompt": prompt,
        "chat_completions_path": {"path": routing.GATEWAY_CHAT_PATH, **chat},
        "anthropic_path": {"path": ANTHROPIC_MESSAGES_PATH, **anthropic},
        "why_this_matters": (
            "If the guardrail blocks on the chat path but the provider-native path answers, the "
            "control does not cover the path coding agents use — a silent gap. Verify both paths "
            "on this account before relying on a guardrail for coding-agent traffic."),
    }
    if chat["blocked"] and anthropic["outcome"] == "answered":
        return _todo(
            "Silent gap: the guardrail BLOCKED on the chat path but the provider-native "
            "(anthropic) path ANSWERED. Controls do not cover the path coding agents use — "
            "confirm with your account team.", **detail)
    if chat["blocked"] and anthropic["blocked"]:
        return _ok("Guardrail fired on BOTH the chat path and the provider-native path — "
                   "coverage is consistent.", **detail)
    if chat["outcome"] == "answered":
        return _todo(
            "The probe was not blocked on the chat path, so there is no guardrail decision to "
            "compare across paths yet. Configure a PII/keyword guardrail on the endpoint, then "
            "re-run to compare path coverage.", **detail)
    return _todo(
        "Could not conclusively compare paths (the chat probe or the provider-native path "
        "errored, or the path is not applicable to this endpoint). Verify manually whether "
        "guardrails and rate limits fire on the path your coding agents use.", **detail)


def t_rate_limit_429_demo() -> TestResult:
    """Send a small burst to the governed endpoint and try to trip the rate limit (HTTP 429).

    The hard cost control: an exceeded rate limit returns 429 immediately, unlike a budget alert
    which does not block. Two honest caveats are baked into the messaging: rate-limit changes can
    take up to ~1-2 hours to take effect, and the limit must apply to THIS app's calling identity
    (its service principal) or be endpoint-wide, or the burst will not trip it. Never raises;
    each request's outcome is captured.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    if not name:
        return _fail("No governed_endpoint.name configured.")
    w = get_workspace_client()
    try:
        ep = w.serving_endpoints.get(name)
    except Exception as e:
        return _todo(f"Endpoint `{name}` not found — create it, set a low per-user rate limit, "
                     "then re-run.", endpoint=name, error=str(e)[:300],
                     deep_link=deep_links.serving_endpoint(name))
    gw = getattr(ep, "ai_gateway", None)
    limits = [
        {"key": getattr(rl, "key", None), "principal": getattr(rl, "principal", None),
         "calls": getattr(rl, "calls", None), "tokens": getattr(rl, "tokens", None),
         "renewal_period": str(getattr(rl, "renewal_period", "") or "")}
        for rl in (getattr(gw, "rate_limits", None) or [])
    ] if gw else []

    try:
        burst = max(1, min(30, int(cfg.get("rate_limit_burst", 15))))
    except (TypeError, ValueError):
        burst = 15
    ok = throttled = 0
    other: list[str] = []
    for _ in range(burst):
        try:
            w.api_client.do(
                "POST", routing.GATEWAY_CHAT_PATH,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                body={"model": name, "messages": [{"role": "user", "content": "ping"}],
                      "max_tokens": 1})
            ok += 1
        except Exception as e:  # noqa: BLE001
            u = str(e).upper()
            if "429" in u or "REQUEST_LIMIT_EXCEEDED" in u or "RATE LIMIT" in u:
                throttled += 1
            elif len(other) < 5:
                other.append(str(e)[:120])
    detail = {
        "endpoint": name, "burst": burst,
        "responses": {"ok": ok, "throttled_429": throttled, "other": other},
        "configured_rate_limits": limits,
        "deep_link": deep_links.serving_endpoint(name),
    }
    if throttled:
        return _ok(f"Rate limit enforced — {throttled}/{burst} request(s) returned HTTP 429. "
                   "This is the hard throughput control (a budget alert does not block).",
                   **detail)
    return _todo(
        f"Sent {burst} request(s) to `{name}` with no 429. Set a low per-user rate limit in the "
        "AI Gateway UI and re-run. Two things to check: rate-limit changes can take up to ~1-2 "
        "hours to take effect, and the limit must apply to THIS app's identity (its service "
        "principal) or be endpoint-wide — a per-user limit on a different user will not trip "
        "from here.", **detail,
        note="An exceeded rate limit returns HTTP 429 immediately, distinct from a budget alert.")


def t_telemetry_readiness() -> TestResult:
    """Confirm the AI telemetry tables are present and actually receiving rows.

    Was `lakewatch_readiness`, and was a core step. Renamed and demoted to the Agent
    Registry accelerator because Lakewatch is not enabled on most accounts, so a core step
    named after it checked readiness for a product the room could not use. The check itself
    is still worth having where telemetry is the point.

    Counts rows in the last day rather than the whole table: an existing-but-empty table is
    not the same as a populated one, and a bare COUNT(*) over all history is slow and tells
    the room nothing about whether telemetry is flowing NOW.
    """
    checks = []
    for table, pred in (
        ("system.ai_gateway.usage", "event_time > current_timestamp() - INTERVAL 1 DAY"),
        ("system.access.audit", "event_date >= current_date() - INTERVAL 1 DAY"),
    ):
        try:
            rows = fetchall(f"SELECT COUNT(*) AS n FROM {table} WHERE {pred}")
            n = int(rows[0].get("n") or 0) if rows else 0
            checks.append({"table": table, "available": True, "rows_last_24h": n})
        except Exception as e:
            checks.append({"table": table, "available": False, "error": str(e)[:200]})

    reachable = [c for c in checks if c["available"]]
    flowing = [c for c in reachable if c.get("rows_last_24h", 0) > 0]
    if not reachable:
        return _fail("No AI telemetry tables are reachable — the app's service principal "
                     "likely needs SELECT on the `system` schemas.", checks=checks)
    if not flowing:
        return _todo(f"{len(reachable)}/{len(checks)} telemetry table(s) reachable but none "
                     "have rows in the last 24h. Send governed traffic, then re-run.",
                     checks=checks)
    return _ok(f"{len(flowing)}/{len(checks)} telemetry table(s) reachable and populated "
               "in the last 24h.", checks=checks)


# --------------------------------------------------------------------------- MCP accelerator
# Structured on the three planes of MCP governance:
#   Plane 1 Authenticate — the OAuth scope decides which endpoint FAMILY you reach.
#   Plane 2 Authorize    — UC grants decide whether you can see/call a specific tool.
#   Plane 3 Behavior     — service policies (ALLOW/DENY/ASK) on an MCP_SERVICE securable.
# The managed UC-native endpoints have planes 1+2 only; MCP Services have all three. Every
# test below says which plane it is exercising, because that distinction is the whole point.
def t_mcp_inventory() -> TestResult:
    """Plane 2 — every MCP_SERVICE securable on the metastore, provided and external.

    Replaces an earlier placeholder that listed serving endpoints (i.e. models), which is a
    different surface entirely and the thing reviewers rightly flagged.
    """
    out = mcp.list_mcp_services()
    if not out["ok"]:
        return _fail("Could not list MCP services. The MCP/AI Gateway preview may not be "
                     "enabled on this account, or the caller lacks metastore access.",
                     error=out["error"],
                     hint="GET /api/2.1/unity-catalog/mcp-services")
    svcs = out["services"]
    if not svcs:
        return _todo("No MCP services registered yet. The provided `system.ai.*` services "
                     "appear once the preview is enabled; register an external server to "
                     "add your own.", services=[])
    provided = [s["name"] for s in svcs if s["provided"]]
    external = [s["name"] for s in svcs if not s["provided"]]
    summary = f"{len(svcs)} MCP service(s): {len(provided)} Databricks-provided"
    summary += f", {len(external)} external/custom." if external else ", 0 external/custom."
    return _ok(summary, provided=provided, external=external,
               note="Provided and external services are both MCP_SERVICE securables, so "
                    "both support service policies. The managed UC-native endpoints "
                    "(/api/2.0/mcp/functions/...) do NOT — see the next steps.",
               services=svcs)


def t_mcp_managed_tools() -> TestResult:
    """Planes 1+2 — the managed UC-native endpoint: UC functions exposed as MCP tools.

    Deny-by-absence at object grain: a caller without USE CATALOG + USE SCHEMA gets an
    EMPTY list, not an error. An empty result is therefore ambiguous and is reported as a
    to-do with both explanations rather than as a pass.
    """
    cat, sch = _fq_schema()
    url = mcp.managed_functions_url(cat, sch)
    out = mcp.list_tools(url)
    if not out["ok"]:
        return _fail("Managed MCP functions endpoint did not answer.", url=url,
                     error=out["error"],
                     hint="Needs the Managed MCP preview and an OAuth token with the "
                          "`unity-catalog` scope. A PAT must carry `all-apis`.")
    tools = out["tools"]
    if not tools:
        return _todo(
            f"Endpoint reachable, but no tools visible in `{cat}.{sch}`. Either the schema "
            "has no UC functions yet, or the caller lacks USE CATALOG + USE SCHEMA — "
            "managed MCP hides ungranted objects instead of erroring, so both look "
            "identical here. Create a UC function (the MCP policy step makes one), then re-run.",
            url=url, plane="1+2 (authenticate + authorize)")
    return _ok(f"{len(tools)} UC function(s) exposed as MCP tools from `{cat}.{sch}`.",
               url=url, tools=tools, plane="1+2 (authenticate + authorize)",
               note="These are raw UC-native endpoints, NOT MCP_SERVICE securables — no "
                    "service policy can attach here. Governance is UC grants + column "
                    "masks/ABAC on the underlying data.")


def t_mcp_service_tools() -> TestResult:
    """Planes 1+2 — live tools/list against the configured MCP Service.

    Proves the tool surface is real rather than described. Also reports whether the service
    is already filtered to read-only tools, which changes how the policy step should be
    framed (see t_mcp_policy_target).
    """
    svc = mcp.configured_service()
    if not svc:
        return _fail("No MCP service configured — set `mcp.builtin_service` in "
                     "config/workshop.yaml (e.g. system.ai.github).")
    url = mcp.service_url(svc)
    out = mcp.list_tools(url)
    if not out["ok"]:
        status = out.get("http_status")
        if status == 403:
            return _todo(
                f"`{svc}` returned 403 — the service exists but this caller is not "
                "entitled, or per-user OAuth consent has not been completed. Open the "
                "service in the AI Gateway UI and use Login, then re-run.",
                service=svc, url=url, error=out["error"], plane="1 (authenticate)")
        return _fail(f"tools/list failed against `{svc}`.", service=svc, url=url,
                     error=out["error"], plane="1+2")
    tools = out["tools"]
    if not tools:
        return _todo(f"`{svc}` is reachable but exposed 0 tools — tool selection may "
                     "exclude everything, or consent is incomplete for this identity.",
                     service=svc, url=url, plane="1+2")
    read_only = [t["name"] for t in tools if t["read_only"]]
    writes = [t["name"] for t in tools if t["read_only"] is False]
    return _ok(f"`{svc}` exposes {len(tools)} tool(s): {len(read_only)} read-only, "
               f"{len(writes)} write-capable.",
               service=svc, url=url, tools=tools, read_only=read_only,
               write_capable=writes, plane="1+2 (authenticate + authorize)",
               note=("This service is already filtered to read-only tools, so there is no "
                     "write tool here to deny — the policy step below denies a READ tool "
                     "instead, which still proves enforcement."
                     if not writes else
                     "Write-capable tools are exposed — a service policy denying them is "
                     "the highest-value control to demonstrate."))


def t_mcp_grants() -> TestResult:
    """Plane 2 — who is entitled to call the configured MCP Service.

    The finding that matters: `system.ai` grants EXECUTE to *all account users* by default,
    so a provided service is open to the whole account until scoped. Recommended posture is
    deny-by-absence — grant inside a customer-owned catalog rather than revoking in
    `system.ai`, where a schema-level revoke may not cascade.
    """
    svc = mcp.configured_service()
    if not svc:
        return _fail("No MCP service configured (`mcp.builtin_service`).")
    out = mcp.service_grants(svc)
    if not out["ok"]:
        return _fail(f"Could not read grants on `{svc}`.", service=svc, error=out["error"])
    assignments = out["assignments"]
    broad = [a for a in assignments
             if (a["principal"] or "").lower() in ("account users", "users")
             and "EXECUTE" in a["privileges"]]
    detail = {"service": svc, "assignments": assignments, "plane": "2 (authorize)",
              "required_to_see": "USE CATALOG + USE SCHEMA",
              "required_to_call": "EXECUTE"}
    if broad:
        return _todo(
            f"`{svc}` grants EXECUTE to `{broad[0]['principal']}` — every account user can "
            "call it. That is the default for `system.ai`, and it is the finding to show a "
            "security team. Scope it to the pilot group before rollout.",
            **detail,
            recommendation="Prefer deny-by-absence: register the service in a "
                           "customer-owned catalog and grant EXECUTE explicitly. A "
                           "schema-level REVOKE inside system.ai may not cascade.")
    return _ok(f"`{svc}` has {len(assignments)} scoped grant(s) — not open to all account "
               "users.", **detail)


def t_mcp_policy_target() -> TestResult:
    """Plane 3 — confirm the policy target is a securable a policy can actually attach to.

    The step that prevents the most common wasted hour: service policies attach ONLY to
    MCP_SERVICE securables. Point one at a managed UC-native endpoint and there is nothing
    to attach to, which the product surfaces confusingly.
    """
    svc = mcp.configured_service()
    if not svc:
        return _fail("No MCP service configured (`mcp.builtin_service`).")
    inv = mcp.list_mcp_services()
    if not inv["ok"]:
        return _fail("Could not confirm the securable type.", error=inv["error"])
    match = next((s for s in inv["services"] if s["name"] == svc), None)
    if not match:
        return _fail(
            f"`{svc}` is not a registered MCP_SERVICE securable, so no service policy can "
            "attach to it. Service policies require an MCP Service (provided `system.ai.*` "
            "or an external one you register) — the managed /api/2.0/mcp/... endpoints are "
            "not securables.",
            configured=svc,
            available=[s["name"] for s in inv["services"]],
            plane="3 (behavior)")
    return _ok(f"`{svc}` is an MCP_SERVICE securable — a service policy can attach to it.",
               service=svc, securable_type=match["securable_type"],
               owner=match["owner"], plane="3 (behavior)",
               requires="EXECUTE on the policy function + MANAGE on the service",
               note="Attachment is UI-only in the current Beta — there is no "
                    "ALTER ... SET SERVICE POLICY DDL or control-API path yet.")


def t_mcp_obo() -> TestResult:
    """Plane 2 — prove on-behalf-of: the tool runs as the CALLER, not a shared account.

    Calls a read tool that echoes the upstream identity, so the room sees a real name come
    back rather than taking OBO on faith. This is the single most persuasive MCP demo: if
    the caller cannot see something, neither can their agent.
    """
    svc = mcp.configured_service()
    url = mcp.service_url(svc)
    probe = ((get_config().get("mcp", {}) or {}).get("service_policy", {})
             or {}).get("identity_probe_tool")
    listed = mcp.list_tools(url)
    if not listed["ok"]:
        return _todo(f"Cannot reach `{svc}` to prove OBO — resolve the previous step first.",
                     service=svc, error=listed["error"])
    names = [t["name"] for t in listed["tools"]]
    # Prefer a configured probe; otherwise any "who am I" style read tool.
    candidates = [probe] if probe else []
    candidates += [n for n in ("get_me", "get_my_user_profile", "whoami") if n in names]
    tool = next((c for c in candidates if c and c in names), None)
    if not tool:
        return _todo(
            "No identity-echo tool available on this service, so OBO cannot be shown "
            "automatically. Set `mcp.service_policy.identity_probe_tool` to a read tool "
            "that returns the calling user, or show OBO by having two people run the same "
            "tool and comparing results.",
            service=svc, available_tools=names[:20])
    out = mcp.call_tool(url, tool)
    if not out["ok"]:
        return _fail(f"`{tool}` failed — cannot demonstrate OBO.", service=svc,
                     tool=tool, error=out["error"])
    text = json.dumps(out["result"])[:600]
    return _ok(f"`{tool}` executed as the calling user — identity propagated to the "
               "upstream provider (no shared service account).",
               service=svc, tool=tool, plane="2 (authorize, on-behalf-of)",
               upstream_identity_excerpt=text,
               note="The response carries the CALLER's upstream identity. Two participants "
                    "running this get two different answers, which is the proof: the agent "
                    "inherits the human's permissions, nothing more.")


def t_mcp_policy_enforcement() -> TestResult:
    """Plane 3 — evaluate the policy function against synthetic events, then explain scope.

    Policy LOGIC is verifiable here (the function is a UC SQL UDF we can call directly).
    ENFORCEMENT requires the policy to be attached, which is UI-only in Beta — so this
    reports logic plus the exact remaining manual step rather than implying end-to-end proof.
    """
    cfg = get_config()
    cat, sch = _fq_schema()
    pol = (cfg.get("mcp", {}) or {}).get("service_policy", {}) or {}
    try:
        fn = _sql_ident(pol.get("function_name", "mcp_read_only_policy"),
                        "mcp.service_policy.function_name")
    except ValueError as e:
        return _fail(str(e))
    fqn = f"{cat}.{sch}.{fn}"
    deny_tool = (pol.get("deny_tools") or [None])[0]
    allow_tool = pol.get("allow_probe_tool")
    if not deny_tool or not allow_tool:
        return _fail("Config needs mcp.service_policy.deny_tools and allow_probe_tool.")

    def probe(tool: str) -> dict:
        event = json.dumps({"type": "request",
                            "context": {"tool": {"name": tool}}})
        rows = fetchall(f"SELECT {fqn}(parse_json({_sql_str(event)})):result::STRING AS d, "
                        f"{fqn}(parse_json({_sql_str(event)})):reason::STRING AS r")
        row = rows[0] if rows else {}
        return {"tool": tool, "decision": row.get("d") or "NO_RESULT",
                "reason": row.get("r")}

    try:
        denied, allowed = probe(deny_tool), probe(allow_tool)
    except Exception as e:
        return _todo("Policy function does not exist yet — create it in the previous step.",
                     function=fqn, error=str(e)[:400])

    svc = mcp.configured_service()
    detail = {
        "function": fqn, "service": svc, "plane": "3 (behavior)",
        "denied_probe": denied, "allowed_probe": allowed,
        "deep_link": deep_links.mcp_service(svc),
        "next": f"Attach `{fqn}` to `{svc}` in the AI Gateway UI (Policies tab), then call "
                f"`{deny_tool}` from an agent and confirm the structured DENY error.",
        "beta_limits": "SQL-only policies; UI-only attachment; applies to all account "
                       "users; evaluation is fail-closed (an error during evaluation "
                       "means DENY).",
    }
    if denied["decision"] == "DENY" and allowed["decision"] == "ALLOW":
        return _todo(
            f"Policy logic verified: `{deny_tool}` → DENY, `{allow_tool}` → ALLOW. "
            "Enforcement is not proven until the policy is attached (UI-only in Beta).",
            **detail)
    return _fail(f"Policy returned the wrong decision: `{deny_tool}` → "
                 f"{denied['decision']}, `{allow_tool}` → {allowed['decision']}.", **detail)


def t_mcp_external_readiness() -> TestResult:
    """Plane 1 — prerequisites for registering an EXTERNAL/custom MCP server.

    Reports the HTTP connections that exist (external MCP is registered behind one) and the
    registration sequence. Read-only: creating a connection needs customer-specific
    credentials, so it stays a guided step.
    """
    w = get_workspace_client()
    conns = []
    try:
        for c in w.connections.list():
            ctype = str(getattr(c, "connection_type", "") or "")
            if "HTTP" in ctype.upper():
                conns.append({"name": c.name, "type": ctype})
    except Exception as e:
        return _fail("Could not list connections.", error=str(e)[:300])
    inv = mcp.list_mcp_services()
    external = [s["name"] for s in (inv.get("services") or []) if not s["provided"]]
    steps = [
        "1. Catalog → Connections → Create connection → HTTP. Server URL + auth "
        "(bearer token, OAuth M2M/U2M, or Dynamic Client Registration).",
        "2. Register the MCP Service against that connection (AI Gateway → MCPs → "
        "Register MCP Server) and select which tools to expose.",
        "3. Complete per-user OAuth consent on the service page (Login).",
        "4. GRANT EXECUTE on the mcp_service to the pilot group. Do NOT grant "
        "USE CONNECTION to end users — it bypasses tool selection and auditing.",
        "5. Invoke at /ai-gateway/mcp-services/{catalog}.{schema}.{name}.",
    ]
    if external:
        return _ok(f"{len(external)} external MCP service(s) already registered.",
                   external_services=external, http_connections=conns,
                   plane="1 (authenticate)", registration_steps=steps)
    return _todo(
        "No external MCP services registered yet — this is the step that unlocks service "
        "policies for a customer not yet using Databricks-hosted MCP.",
        http_connections=conns, registration_steps=steps, plane="1 (authenticate)",
        gotcha="Self-hosted servers must be STATELESS (e.g. FastMCP stateless_http=True). "
               "A stateful server behind the replicated gateway proxy can fail the first "
               "tools/call with a session error even though initialize and tools/list "
               "succeeded.")


def t_mcp_telemetry() -> TestResult:
    """Telemetry — MCP call records in the Gateway usage table.

    Sits across the planes rather than in one. Managed UC-native endpoints write NO
    MCP-specific telemetry; MCP Services write a usage row and an mcpCall audit row (no
    payloads — MCP payload logging is not in Beta).
    """
    sql = """
      SELECT service_name, requester,
             COUNT(*) AS calls,
             SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors,
             ROUND(AVG(latency_ms)) AS avg_latency_ms
      FROM system.ai_gateway.usage
      WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
        AND service_type = 'MCP_SERVICE'
      GROUP BY 1, 2 ORDER BY calls DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
    except Exception as e:
        return _fail("MCP telemetry query failed — needs SELECT on system.ai_gateway.",
                     error=str(e)[:500], sql=sql)
    if not rows:
        return _todo(
            "No MCP_SERVICE calls in the last 7 days. Call a tool (previous steps), then "
            "re-run — records can lag a few minutes.", sql=sql,
            note="Managed UC-native endpoints (/api/2.0/mcp/...) write no MCP-specific "
                 "telemetry at all, so only MCP Service traffic appears here.")
    return _ok(f"{len(rows)} requester/service pair(s) with MCP calls in the last 7 days.",
               rows=rows, sql=sql,
               note="Identity, service, and tool are recorded; ARGUMENTS AND RESULTS ARE "
                    "NOT — MCP payload logging is not in the current Beta. Say this "
                    "plainly if a customer asks about full request/response capture.")


def t_mcp_readonly_enforcement() -> TestResult:
    """Read-only enforcement — keep coding-agent users to read tools while humans keep write.

    The most-requested MCP control. How it is enforced depends on the MCP kind, and that
    distinction is the whole point:
      - **MCP Service** (`system.ai.*` or an external one you register): attach a service policy
        that DENIES the write tools, and never grant `USE CONNECTION` to end users (it bypasses
        tool selection, so a user could call a denied tool directly).
      - **Managed UC-native endpoint** (DBSQL / Genie functions): NOT a securable, so no service
        policy can attach — read-only is enforced by exposing only read functions and by the UC
        grants on them.

    This classifies the configured service's tools into read vs write so the room can see
    exactly what a read-only policy would need to deny.
    """
    svc = mcp.configured_service()
    if not svc:
        return _fail("No MCP service configured (`mcp.builtin_service`).")
    url = mcp.service_url(svc)
    out = mcp.list_tools(url)
    if not out["ok"]:
        return _todo(f"Could not list tools on `{svc}` — resolve the earlier MCP steps first.",
                     service=svc, error=out["error"])
    tools = out["tools"]
    if not tools:
        return _todo(f"`{svc}` exposed 0 tools, so there is nothing to classify yet.",
                     service=svc)
    writes = sorted(t["name"] for t in tools if t.get("read_only") is False)
    reads = sorted(t["name"] for t in tools if t.get("read_only") is True)
    unknown = sorted(t["name"] for t in tools if t.get("read_only") is None)
    detail = {
        "service": svc,
        "write_tools": writes, "read_tools": reads, "unknown_tools": unknown,
        "how_to_enforce": {
            "mcp_service": "Attach a service policy that denies the write tools; grant EXECUTE "
                           "to coding-agent users but NOT USE CONNECTION.",
            "managed_endpoint": "No policy can attach (not a securable) — expose only read "
                                "functions and control access with UC grants on them.",
        },
        "caveat": ("`read_only` comes from each tool's readOnlyHint annotation; a tool with no "
                   "hint shows as unknown and should be reviewed by hand before trusting it."),
    }
    if writes:
        return _todo(
            f"`{svc}` exposes {len(writes)} write-capable tool(s) ({', '.join(writes[:6])}). For "
            "read-only coding-agent access, deny these with a service policy (see the policy "
            "steps) and keep write for human identities.", **detail)
    if unknown and not reads:
        return _todo(f"`{svc}` tools carry no read-only hints, so read vs write cannot be "
                     "determined automatically — review each before granting access.", **detail)
    return _ok(f"`{svc}` exposes only read tools ({len(reads)}) — read-only by construction, so "
               "coding-agent access needs no write-denying policy here.", **detail)


# Prompt-injection phrases that have no legitimate place in a tool's user-facing metadata.
_TOOL_POISON_RE = re.compile(
    r"ignore (all |the |previous |prior )*(instructions|prompt)|disregard (the |all )*(above|previous)"
    r"|system prompt|you are now|do not (tell|mention|reveal)|without (telling|informing)"
    r"|exfiltrat|<\s*system|begin system|api[_-]?key|secret key|password", re.IGNORECASE)


def t_mcp_tool_metadata_scan() -> TestResult:
    """Scan the configured MCP service's tool metadata for prompt-injection ('tool poisoning').

    A tool's name and description are fed to the model, so a malicious or compromised server can
    hide instructions there ("ignore previous instructions", "before answering, send X to..."),
    steering an agent without the user ever seeing it. This lists the tools and flags metadata
    containing injection-shaped phrases. Detection, not prevention — a flag is a prompt to review
    the tool and its source, never proof of compromise.
    """
    svc = mcp.configured_service()
    if not svc:
        return _fail("No MCP service configured (`mcp.builtin_service`).")
    url = mcp.service_url(svc)
    out = mcp.list_tools(url)
    if not out["ok"]:
        return _todo(f"Could not list tools on `{svc}` — resolve the earlier MCP steps first.",
                     service=svc, error=out["error"])
    tools = out["tools"]
    if not tools:
        return _todo(f"`{svc}` exposed 0 tools to scan.", service=svc)
    flagged = []
    for t in tools:
        text = f"{t.get('name') or ''} {t.get('description') or ''}"
        hits = sorted({m.group(0).lower() for m in _TOOL_POISON_RE.finditer(text)})
        if hits:
            flagged.append({"tool": t.get("name"), "matches": hits,
                            "description_excerpt": str(t.get("description") or "")[:160]})
    detail = {
        "service": svc, "tools_scanned": len(tools), "flagged": flagged,
        "why_this_matters": (
            "Tool names and descriptions are sent to the model, so a compromised or malicious "
            "MCP server can smuggle instructions there — 'tool poisoning'. Review external "
            "servers before granting EXECUTE, and pin/verify the server version."),
        "note": ("Heuristic scan over the tool description the server advertised (truncated). A "
                 "clean result is not a guarantee — it is a first-pass check, not prevention."),
    }
    if flagged:
        return _todo(f"{len(flagged)} of {len(tools)} tool(s) on `{svc}` have injection-shaped "
                     "text in their metadata — review them before trusting the server.", **detail)
    return _ok(f"No injection-shaped phrases found in the {len(tools)} tool description(s) on "
               f"`{svc}`. Still verify external servers and pin their versions.", **detail)


# --------------------------------------------------------------------------- Accelerator-only tests
def t_external_provider_routing() -> TestResult:
    """Report which serving endpoints look like external-model providers routed through the
    Gateway (Bedrock / OpenAI / Anthropic), so the accelerator can prove shadow workloads moved."""
    w = get_workspace_client()
    external, all_names = [], []
    for e in w.serving_endpoints.list():
        all_names.append(e.name)
        n = (e.name or "").lower()
        if any(p in n for p in ("bedrock", "openai", "gpt", "anthropic", "claude", "external")):
            external.append(e.name)
    summary = (f"{len(external)} endpoint(s) look like external-provider routes, of "
               f"{len(all_names)} total." if external
               else "No external-provider-shaped endpoints found — add one behind a governed "
                    "endpoint to route Bedrock/OpenAI/Anthropic through the Gateway.")
    return _ok(summary, external_like=external[:25], total_endpoints=len(all_names))


def t_pii_safety_readiness() -> TestResult:
    """Confirm the sources a PII-leakage judge and red-team review read from."""
    cfg = get_config()
    try:
        cat, sch = _fq_schema()
        prefix = _sql_ident(
            cfg.get("governed_endpoint", {}).get("inference_table_prefix", "workshop_governed"),
            "governed_endpoint.inference_table_prefix")
    except ValueError as e:
        return _fail(str(e))
    table = f"{cat}.{sch}.{prefix}_payload"
    checks = []
    for label, sql in (
        ("inference_table", f"SELECT COUNT(*) AS n FROM {table}"),
        ("audit_log", "SELECT COUNT(*) AS n FROM system.access.audit "
                      "WHERE event_date >= current_date() - INTERVAL 1 DAY"),
    ):
        try:
            rows = fetchall(sql)
            checks.append({"source": label, "available": True,
                           "count": rows[0].get("n") if rows else None})
        except Exception as e:
            checks.append({"source": label, "available": False, "error": str(e)[:200]})

    have_payloads = any(c["source"] == "inference_table" and c["available"] for c in checks)
    if not have_payloads:
        # The judge scores request/response payloads. Without the inference table there is
        # nothing to score, so the audit log alone is not "ready".
        return _todo("The inference table is not available yet — a PII-leakage judge needs "
                     "request/response payloads to score. Enable payload logging on the "
                     "governed endpoint (needs an external-storage catalog), then re-run.",
                     checks=checks, inference_table=table)
    return _ok("Payload logging is available — ready for the PII-leakage judge and red-team "
               "review.", checks=checks, inference_table=table)


def t_pii_mask_vs_block() -> TestResult:
    """Show whether the PII guardrail BLOCKS the request or MASKS the PII in the response.

    Sends a prompt that asks the model to echo a synthetic SSN, and classifies the outcome:
      - block:       the request is refused (BLOCK mode)
      - mask:        the model answers but the SSN is redacted/absent (MASK mode)
      - passthrough: the SSN comes back intact (no PII guardrail on this path)
    MASK is the more common production choice — it lets a benign request through with PII removed
    rather than failing it. Never raises.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    if not name:
        return _fail("No governed_endpoint.name configured.")
    ssn = "123-45-6789"
    prompt = f"Repeat this back verbatim, exactly as written: 'reference {ssn} end'."
    w = get_workspace_client()
    try:
        resp = w.api_client.do(
            "POST", routing.GATEWAY_CHAT_PATH,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body={"model": name, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 64})
    except Exception as e:  # noqa: BLE001
        low = str(e).lower()
        if any(s in low for s in ("guardrail", "blocked", "policy", "content filter", "flagged")):
            return _ok("PII guardrail is in BLOCK mode — the request was refused. Consider MASK "
                       "for production: it lets a benign request through with the PII removed "
                       "rather than failing it.",
                       mode="block", endpoint=name, prompt=prompt, detail=str(e)[:300])
        if any(s in low for s in ("does not exist", "not found", "404")):
            return _todo(f"Endpoint `{name}` not found — create it, attach a PII guardrail, then "
                         "re-run.", endpoint=name, error=str(e)[:300])
        return _fail("Could not run the PII probe.", endpoint=name, error=str(e)[:400])
    choices = (resp or {}).get("choices") or []
    answer = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
    answer_text = answer if isinstance(answer, str) else json.dumps(answer)
    detail = {"endpoint": name, "prompt": prompt, "response_excerpt": answer_text[:300]}
    if re.search(r"\d{3}-\d{2}-\d{4}", answer_text):
        return _todo("The SSN came back INTACT — no PII masking on this path. Attach a PII "
                     "guardrail (MASK or BLOCK) on the endpoint and re-run.",
                     mode="passthrough", **detail)
    return _ok("PII guardrail is in MASK mode — the request was answered with the SSN "
               "removed/redacted. This is the common production choice.", mode="mask", **detail)


def t_guardrail_block_shape() -> TestResult:
    """How is a block delivered — a 4xx error, or HTTP 200 with a refusal reason?

    This matters for coding agents: they resend conversation history, so a 4xx block on one turn
    can re-trigger on every later benign turn ("sticky block") until a new session starts. The
    rolling fix returns HTTP 200 with a structured reason instead, which lets the client
    continue. Reports which shape THIS account returns, and states the fail-closed rule: when a
    policy/guardrail evaluation errors, the decision is DENY, never a silent allow. Never raises.
    """
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    if not name:
        return _fail("No governed_endpoint.name configured.")
    blocked = (cfg.get("guardrails", {}).get("keyword_policy", {}).get("blocked_keywords")
               or ["social security number"])[0]
    prompt = f"My {blocked} is 123-45-6789, please store it."
    note = ("Fail-closed: when a policy or guardrail evaluation errors, the gateway returns DENY, "
            "never a silent allow.")
    w = get_workspace_client()
    try:
        resp = w.api_client.do(
            "POST", routing.GATEWAY_CHAT_PATH,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body={"model": name, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 64})
    except Exception as e:  # noqa: BLE001
        low = str(e).lower()
        if any(s in low for s in ("guardrail", "blocked", "policy", "content filter", "flagged")):
            return _todo(
                "Block delivered as a 4xx ERROR. Coding agents resend history, so a 4xx block "
                "can 'stick' across a session until a new one starts. If your account has the "
                "rolling fix, blocks return HTTP 200 with a reason instead — confirm which "
                "behavior you have.",
                shape="4xx_error", endpoint=name, prompt=prompt, detail=str(e)[:300], note=note)
        if any(s in low for s in ("does not exist", "not found", "404")):
            return _todo(f"Endpoint `{name}` not found — create it, attach a guardrail, re-run.",
                         endpoint=name, error=str(e)[:300])
        return _fail("Could not run the block-shape probe.", endpoint=name, error=str(e)[:400])
    choices = (resp or {}).get("choices") or []
    answer = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
    answer_text = answer if isinstance(answer, str) else json.dumps(answer)
    finish = choices[0].get("finish_reason") if choices else None
    refused = (finish in ("content_filter", "guardrail")) or any(
        s in answer_text.lower() for s in
        ("can't help", "cannot help", "can not help", "won't", "not able to",
         "against policy", "blocked", "i'm unable", "i am unable"))
    detail = {"endpoint": name, "prompt": prompt, "response_excerpt": answer_text[:300],
              "finish_reason": finish, "note": note}
    if refused:
        return _ok("Block delivered as HTTP 200 with a refusal reason — the client-friendly "
                   "shape. A coding agent can continue the session rather than getting stuck on "
                   "a sticky 4xx.", shape="200_with_reason", **detail)
    return _todo("The prompt was NOT blocked (a normal answer came back on HTTP 200). Attach a "
                 "PII/keyword guardrail on the endpoint, then re-run to see the block shape.",
                 shape="not_blocked", **detail)


REGISTRY: dict[str, Callable[[], TestResult]] = {
    "connection": t_connection,
    "workspace_context": t_workspace_context,
    "list_endpoints": t_list_endpoints,
    "model_services": t_model_services,
    "default_access": t_default_access,
    "endpoint_acl": t_endpoint_acl,
    "rate_limits": t_rate_limits,
    "routing_panel": t_routing_panel,
    "routing_compare": t_routing_compare,
    "routing_roi": t_routing_roi,
    "gateway_spend_by_model": t_gateway_spend_by_model,
    "create_governed_endpoint": t_create_governed_endpoint,
    "verify_governed_endpoint": t_verify_governed_endpoint,
    "test_guardrail": t_test_guardrail,
    "guardrail_activity": t_guardrail_activity,
    "create_mcp_policy": t_create_mcp_policy,
    "test_mcp_policy": t_test_mcp_policy,
    "apply_tags": t_apply_tags,
    "usage_by_project": t_usage_by_project,
    "audit_scan": t_audit_scan,
    "list_registered_assets": t_list_registered_assets,
    "budget_status": t_budget_status,
    "coding_agent_usage": t_coding_agent_usage,
    "coding_agent_route_check": t_coding_agent_route_check,
    "path_coverage_check": t_path_coverage_check,
    "rate_limit_429_demo": t_rate_limit_429_demo,
    "telemetry_readiness": t_telemetry_readiness,
    "external_provider_routing": t_external_provider_routing,
    "pii_safety_readiness": t_pii_safety_readiness,
    "pii_mask_vs_block": t_pii_mask_vs_block,
    "guardrail_block_shape": t_guardrail_block_shape,
    # MCP accelerator (three planes of MCP governance)
    "mcp_inventory": t_mcp_inventory,
    "mcp_managed_tools": t_mcp_managed_tools,
    "mcp_service_tools": t_mcp_service_tools,
    "mcp_grants": t_mcp_grants,
    "mcp_policy_target": t_mcp_policy_target,
    "mcp_obo": t_mcp_obo,
    "mcp_policy_enforcement": t_mcp_policy_enforcement,
    "mcp_external_readiness": t_mcp_external_readiness,
    "mcp_telemetry": t_mcp_telemetry,
    "mcp_readonly_enforcement": t_mcp_readonly_enforcement,
    "mcp_tool_metadata_scan": t_mcp_tool_metadata_scan,
}


def run_test(name: str) -> TestResult:
    fn = REGISTRY.get(name)
    if not fn:
        return _fail(f"Unknown test '{name}'.")
    try:
        result = fn()
    except Exception as e:  # never let a test crash the request
        result = _fail(f"Test '{name}' raised an error.", error=str(e)[:400])
    # Attach the API surface so the UI can show what this step did to the workspace. Kept
    # out of `detail` so it renders as a caption rather than another line of JSON.
    doc = API_DOCS.get(name)
    if doc:
        result["api"] = doc["api"]
        result["api_index"] = API_INDEX
        if doc.get("note"):
            result["api_note"] = doc["note"]
    return result
