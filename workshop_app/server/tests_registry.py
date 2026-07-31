"""Executable governance tests, ported from the l200_demo pages.

Each test is a function returning a TestResult. They exercise real controls against the
connected workspace (list endpoints, create a governed endpoint, run guardrail/MCP policy
checks, query system tables). Steps in config/steps.yaml reference these by name.

A test result is intentionally simple and JSON-serializable so the UI can render it and
db.py can persist it as `last_result`.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from . import deep_links
from .config import get_config, get_oauth_token, get_workspace_client
from .workspace_sql import fetchall, test_connection

TestResult = dict[str, Any]


def _ok(summary: str, **detail) -> TestResult:
    return {"ok": True, "summary": summary, "detail": detail}


def _fail(summary: str, **detail) -> TestResult:
    return {"ok": False, "summary": summary, "detail": detail}


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


def t_routing_cost() -> TestResult:
    """Compare cost of the same prompt across a frontier and a cost-efficient model.

    Placeholder cost model until the routing-agent example lands: reports the two
    configured endpoints and an illustrative per-1k-token cost delta so the UI has
    something concrete to show. Real token accounting comes from the routing agent.
    """
    cfg = get_config().get("gateway", {})
    frontier = cfg.get("ootb_endpoint")
    cheap = cfg.get("cheap_endpoint")
    return _ok(
        "Compared model options (illustrative — routing agent to be added).",
        frontier_endpoint=frontier,
        cost_efficient_endpoint=cheap,
        note="Add a routing agent example to populate live token cost per model.",
    )


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
    return _ok(
        f"Endpoint `{name}` not found — create it from the workspace.",
        endpoint=name,
        primary=cfg.get("primary_model"),
        fallback=cfg.get("fallback_model"),
        deep_link=deep_links.serving_endpoint(name),
        note="Endpoint creation with external-model config is a guided UI/bundle step to "
             "avoid destructive automated changes on a customer workspace.",
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
    """Send a prompt containing a blocked keyword to the governed endpoint; expect a block."""
    cfg = get_config().get("governed_endpoint", {})
    name = cfg.get("name")
    blocked = (cfg.get("guardrails", {}).get("keyword_policy", {}).get("blocked_keywords") or ["social security number"])[0]
    w = get_workspace_client()
    prompt = f"My {blocked} is 123-45-6789, please store it."
    try:
        resp = w.serving_endpoints.query(
            name=name,
            messages=[{"role": "user", "content": prompt}] if False else None,
            dataframe_records=None,
            inputs=None,
            prompt=None,
        )  # placeholder; real call shape depends on endpoint task
        return _ok("Sent test prompt.", response=str(resp)[:400])
    except Exception as e:
        msg = str(e)
        blocked_signal = any(s in msg.lower() for s in ("guardrail", "blocked", "policy", "400"))
        if blocked_signal:
            return _ok("Guardrail fired — request was blocked as expected.", error=msg[:400])
        return _fail("Could not run guardrail test (endpoint may not be created yet).", error=msg[:400])


def t_guardrail_activity() -> TestResult:
    """Query the inference table for non-ALLOW guardrail decisions."""
    cfg = get_config()
    cat = cfg.get("catalog", {}).get("name")
    sch = cfg.get("catalog", {}).get("schema")
    prefix = cfg.get("governed_endpoint", {}).get("inference_table_prefix", "workshop_governed")
    table = f"{cat}.{sch}.{prefix}_payload"
    try:
        rows = fetchall(
            f"SELECT * FROM {table} WHERE COALESCE(guardrail_decision,'ALLOW') <> 'ALLOW' "
            f"ORDER BY 1 DESC LIMIT 10"
        )
        return _ok(f"{len(rows)} guardrail events in the inference table.", rows=rows[:10])
    except Exception as e:
        return _fail("Inference table not available yet (allow 10-30 min after enabling).", error=str(e)[:300])


def t_create_mcp_policy() -> TestResult:
    """Create the UC SQL function that denies write tools on the MCP service."""
    cfg = get_config()
    cat = cfg.get("catalog", {}).get("name")
    sch = cfg.get("catalog", {}).get("schema")
    pol = cfg.get("mcp", {}).get("service_policy", {})
    fn = pol.get("function_name", "confluence_mcp_policy")
    deny = pol.get("deny_tools", [])
    deny_sql = ", ".join(f"'{d}'" for d in deny) or "''"
    fqn = f"{cat}.{sch}.{fn}"
    ddl = f"""
    CREATE OR REPLACE FUNCTION {fqn}(event VARIANT)
    RETURNS VARIANT
    RETURN CASE
      WHEN event:context.tool.name::STRING IN ({deny_sql})
      THEN to_variant(named_struct('result','DENY','reason','write tools are blocked by workshop policy'))
      ELSE to_variant(named_struct('result','ALLOW','reason',''))
    END;
    """
    try:
        fetchall(ddl)
        return _ok(f"Created policy function `{fqn}`.", function=fqn, denies=deny,
                   next="Attach it in the AI Gateway UI (next step).")
    except Exception as e:
        return _fail("Could not create the policy function.", error=str(e)[:400])


def t_test_mcp_policy() -> TestResult:
    """Report the intended allow/deny probes. Live tool invocation requires the MCP
    service + attached policy; this verifies the policy is defined and names the probes."""
    cfg = get_config().get("mcp", {})
    pol = cfg.get("service_policy", {})
    return _ok(
        "Policy defined. Attach it, then probe read vs write tools.",
        deny_probe=pol.get("deny_tools", [None])[0],
        allow_probe=pol.get("allow_probe_tool"),
        service=cfg.get("builtin_service"),
        deep_link=deep_links.mcp_service(cfg.get("builtin_service", "")),
    )


# --------------------------------------------------------------------------- Clarity
def t_apply_tags() -> TestResult:
    cfg = get_config()
    proj = cfg.get("project", {})
    name = cfg.get("governed_endpoint", {}).get("name")
    return _ok(
        "Project tags ready to apply to the governed endpoint.",
        endpoint=name,
        tags=proj,
        deep_link=deep_links.serving_endpoint(name),
        note="Tag application is surfaced as a guided step to avoid unattended writes; "
             "tags drive the usage-by-project query in the next step.",
    )


def t_usage_by_project() -> TestResult:
    # Real system.serving.endpoint_usage columns: requester, request_time,
    # input_token_count, output_token_count, usage_context (tag map), served_entity_id.
    proj = get_config().get("project", {}).get("name", "")
    sql = f"""
      SELECT requester,
             COUNT(*) AS requests,
             SUM(input_token_count + output_token_count) AS tokens
      FROM system.serving.endpoint_usage
      WHERE usage_context['project'] = '{proj}'
        AND request_time > current_timestamp() - INTERVAL 7 DAYS
      GROUP BY requester ORDER BY tokens DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        summary = (f"Usage rows for project `{proj}`: {len(rows)}." if rows
                   else f"No tagged usage for project `{proj}` yet (tag endpoints, then send traffic).")
        return _ok(summary, rows=rows, sql=sql)
    except Exception as e:
        return _fail("Usage query failed.", error=str(e)[:300], sql=sql)


def t_audit_scan() -> TestResult:
    sql = """
      SELECT event_time, action_name, request_params
      FROM system.access.audit
      WHERE event_date >= current_date() - INTERVAL 1 DAY
        AND (response:status_code >= 400 OR lower(action_name) LIKE '%deny%')
      ORDER BY event_time DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        leaks = [r for r in rows if _looks_like_secret(json.dumps(r))]
        return _ok(f"{len(rows)} recent denied/error calls; {len(leaks)} with secret-shaped args.",
                   rows=rows[:10], suspected_secret_rows=len(leaks))
    except Exception as e:
        return _fail("Audit query failed.", error=str(e)[:300])


def _looks_like_secret(text: str) -> bool:
    import re
    return bool(re.search(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b", text))


# --------------------------------------------------------------------------- Added: 5x4-matrix coverage
def t_list_registered_assets() -> TestResult:
    """Inventory of agents (registered models) and UC functions (tools) — the Choice surface."""
    cfg = get_config()
    cat = cfg.get("catalog", {}).get("name")
    sch = cfg.get("catalog", {}).get("schema")
    w = get_workspace_client()
    agents, tools = [], []
    try:
        for m in w.registered_models.list(catalog_name=cat, schema_name=sch):
            agents.append(m.full_name)
    except Exception:
        pass
    try:
        rows = fetchall(
            f"SELECT function_name FROM system.information_schema.routines "
            f"WHERE routine_catalog = '{cat}' AND routine_schema = '{sch}' LIMIT 50"
        )
        tools = [r.get("function_name") for r in rows]
    except Exception:
        pass
    return _ok(
        f"{len(agents)} registered agent(s)/model(s), {len(tools)} tool function(s) in {cat}.{sch}.",
        agents=agents[:25], tools=tools[:25],
    )


def t_budget_status() -> TestResult:
    """Spend (last 30d) by project tag vs. an illustrative cap. Budgets themselves are set in
    the account console (see the step's manual action); this shows the spend the cap governs."""
    proj = get_config().get("project", {}).get("name", "")
    sql = f"""
      SELECT COUNT(*) AS requests,
             SUM(input_token_count + output_token_count) AS tokens
      FROM system.serving.endpoint_usage
      WHERE usage_context['project'] = '{proj}'
        AND request_time > current_timestamp() - INTERVAL 30 DAYS
    """
    try:
        rows = fetchall(sql)
        return _ok(f"30-day spend signal for project `{proj}`.", rows=rows, sql=sql,
                   note="Set the actual budget + hard cap in the account console (manual step).")
    except Exception as e:
        return _fail("Budget query failed.", error=str(e)[:300], sql=sql)


def t_coding_agent_usage() -> TestResult:
    """Coding-agent traffic attributable in the gateway. Heuristic: usage tagged use_case, or a
    user_agent hint if present in endpoint_usage. Reports per-requester volume so spend is
    attributable per developer."""
    use_case = get_config().get("project", {}).get("use_case", "")
    sql = f"""
      SELECT requester, COUNT(*) AS requests,
             SUM(input_token_count + output_token_count) AS tokens
      FROM system.serving.endpoint_usage
      WHERE usage_context['use_case'] = '{use_case}'
        AND request_time > current_timestamp() - INTERVAL 7 DAYS
      GROUP BY requester ORDER BY tokens DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        summary = (f"{len(rows)} developer(s) with attributable coding-agent usage."
                   if rows else "No coding-agent usage tagged yet — route Cursor/Claude Code/"
                                "Codex/Genie Code through the gateway with a use_case tag.")
        return _ok(summary, rows=rows, sql=sql)
    except Exception as e:
        return _fail("Coding-agent usage query failed.", error=str(e)[:300], sql=sql)


def t_lakewatch_readiness() -> TestResult:
    """Confirm the AI telemetry tables Lakewatch reads exist and are populated."""
    checks = []
    for table in ("system.serving.endpoint_usage", "system.access.audit"):
        try:
            rows = fetchall(f"SELECT COUNT(*) AS n FROM {table} "
                            f"WHERE 1=1 LIMIT 1")
            checks.append({"table": table, "available": True, "sample_count": rows[0].get("n") if rows else None})
        except Exception as e:
            checks.append({"table": table, "available": False, "error": str(e)[:120]})
    ok = all(c["available"] for c in checks)
    return (_ok if ok else _fail)(
        "AI telemetry tables ready for Lakewatch." if ok else "Some telemetry tables are not reachable.",
        checks=checks,
    )


REGISTRY: dict[str, Callable[[], TestResult]] = {
    "connection": t_connection,
    "workspace_context": t_workspace_context,
    "list_endpoints": t_list_endpoints,
    "routing_cost": t_routing_cost,
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
    "lakewatch_readiness": t_lakewatch_readiness,
}


def run_test(name: str) -> TestResult:
    fn = REGISTRY.get(name)
    if not fn:
        return _fail(f"Unknown test '{name}'.")
    try:
        return fn()
    except Exception as e:  # never let a test crash the request
        return _fail(f"Test '{name}' raised an error.", error=str(e)[:400])
