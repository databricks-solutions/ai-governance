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

from . import deep_links, routing
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


def t_routing_panel() -> TestResult:
    """Show the model panel, prices, and the routing policy before anything is run."""
    p = routing.panel()
    return _ok(
        f"{len(p['models'])} models on the panel; classifier = {p['classifier_model']}.",
        **p,
    )


def t_routing_compare() -> TestResult:
    """Send ONE prompt to every model and measure real tokens, latency, and cost.

    This is the measurable-ROI step: same question, three price points, answers side by
    side. Note the answers are shown so the room can judge whether the cheap model was
    actually good enough — cost savings only count if quality holds.
    """
    prompt = _routing_prompt()
    out = routing.compare(prompt)
    live = [r for r in out["results"] if not r["error"]]
    if not live:
        return _fail(
            "No model endpoint answered — check the endpoints in config `cost.routing.endpoints`.",
            prompt=prompt, **out)
    summary = f"{len(live)} model(s) answered."
    if out["spread"] and out["spread"]["ratio"]:
        summary += (f" Most expensive cost {out['spread']['ratio']}x the cheapest "
                    f"(${out['spread']['max_usd']:.6f} vs ${out['spread']['min_usd']:.6f}).")
    return _ok(summary, prompt=prompt, **out)


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
    fqn = f"{cat}.{sch}.{fn}"
    ddl = f"""
    CREATE OR REPLACE FUNCTION {fqn}(event VARIANT)
    RETURNS VARIANT
    RETURN CASE
      WHEN event:context.tool.name::STRING IN ({deny_sql})
      THEN to_variant_object(named_struct('result','DENY','reason','write tools are blocked by workshop policy'))
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
    """Report the tags to apply. Tagging is a guided step, so this is a to-do, not a pass."""
    cfg = get_config()
    proj = cfg.get("project", {})
    name = cfg.get("governed_endpoint", {}).get("name")
    return _todo(
        f"Apply these tags to `{name}` in the workspace, then re-run the usage query.",
        endpoint=name,
        tags=proj,
        deep_link=deep_links.serving_endpoint(name),
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
    sql = f"""
      SELECT requester,
             COUNT(*) AS requests,
             SUM(total_tokens) AS tokens
      FROM system.ai_gateway.usage
      WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
        AND (request_tags['project'] = {p} OR endpoint_tags['project'] = {p})
      GROUP BY requester ORDER BY tokens DESC LIMIT 20
    """
    try:
        rows = fetchall(sql)
        if rows:
            return _ok(f"Usage attributed to project `{proj}`: {len(rows)} requester(s).",
                       rows=rows, sql=sql)
        # No rows is a real (and common) outcome, not a pass: nothing is attributable yet.
        return _todo(
            f"No usage tagged `project={proj}` in the last 7 days. Tag the endpoint "
            "(previous step), send traffic through it, then re-run.",
            rows=[], sql=sql)
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


def t_lakewatch_readiness() -> TestResult:
    """Confirm the AI telemetry tables a SIEM/Lakewatch workflow reads are present.

    Counts rows in the last day rather than the whole table: an existing-but-empty table is
    not the same as a populated one, and a bare COUNT(*) over all history is slow and
    tells the room nothing about whether telemetry is flowing NOW.
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


REGISTRY: dict[str, Callable[[], TestResult]] = {
    "connection": t_connection,
    "workspace_context": t_workspace_context,
    "list_endpoints": t_list_endpoints,
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
    "lakewatch_readiness": t_lakewatch_readiness,
    "external_provider_routing": t_external_provider_routing,
    "pii_safety_readiness": t_pii_safety_readiness,
}


def run_test(name: str) -> TestResult:
    fn = REGISTRY.get(name)
    if not fn:
        return _fail(f"Unknown test '{name}'.")
    try:
        return fn()
    except Exception as e:  # never let a test crash the request
        return _fail(f"Test '{name}' raised an error.", error=str(e)[:400])
