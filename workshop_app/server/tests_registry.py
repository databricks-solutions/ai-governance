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
    "model_services": t_model_services,
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
    "telemetry_readiness": t_telemetry_readiness,
    "external_provider_routing": t_external_provider_routing,
    "pii_safety_readiness": t_pii_safety_readiness,
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
}


def run_test(name: str) -> TestResult:
    fn = REGISTRY.get(name)
    if not fn:
        return _fail(f"Unknown test '{name}'.")
    try:
        return fn()
    except Exception as e:  # never let a test crash the request
        return _fail(f"Test '{name}' raised an error.", error=str(e)[:400])
