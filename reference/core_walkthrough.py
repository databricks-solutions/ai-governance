# Databricks notebook source
# MAGIC %md
# MAGIC # AI Governance Workshop — core walkthrough (no app)
# MAGIC
# MAGIC The 14 core steps (Choice · Cost · Control) run by hand, so you can deliver the workshop
# MAGIC without deploying the app. Everything here targets **your own** workspace and account —
# MAGIC the SDK talks to your workspace API, SQL runs on your warehouse, and the SQL comes from
# MAGIC the same [`workshop_app/queries/*.sql`](../workshop_app/queries) files the app uses.
# MAGIC
# MAGIC Read-only unless a cell says otherwise. Guardrails, rate limits, budgets, and attaching an
# MAGIC MCP policy are set by **you** in the UI — those cells describe the action and verify it.

# COMMAND ----------

# MAGIC %pip install databricks-sdk --quiet

# COMMAND ----------

import json
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("warehouse_id", "", "SQL warehouse id")
dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "ai_governance_workshop", "Schema")
dbutils.widgets.text("project_tag", "ai_governance_workshop", "Project tag value")

WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
PROJECT = dbutils.widgets.get("project_tag")

w = WorkspaceClient()
HOST = (w.config.host or "").rstrip("/")


def _find_queries_dir() -> Path:
    """Locate workshop_app/queries by walking up from the working directory."""
    here = Path(os.getcwd()).resolve()
    for base in [here, *here.parents]:
        cand = base / "workshop_app" / "queries"
        if cand.is_dir():
            return cand
    raise FileNotFoundError(
        "Could not find workshop_app/queries — run this notebook from inside the repo checkout."
    )


QUERIES = _find_queries_dir()


def load_query(name: str, **subs: str) -> str:
    sql = (QUERIES / f"{name}.sql").read_text()
    for k, v in subs.items():
        sql = sql.replace("${" + k + "}", v)
    return sql


def run_sql(sql: str):
    """Run SQL on the configured warehouse and return list[dict]."""
    from databricks.sdk.service.sql import StatementState
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID, statement=sql, wait_timeout="50s"
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(resp.status.error.message if resp.status.error else resp.status.state)
    cols = [c.name for c in resp.manifest.schema.columns] if resp.manifest and resp.manifest.schema else []
    rows = resp.result.data_array if (resp.result and resp.result.data_array) else []
    return [dict(zip(cols, r)) for r in rows]

# COMMAND ----------

# MAGIC %md ## Choice 1 — Connect

# COMMAND ----------

me = w.current_user.me()
print("Connected as:", me.user_name, "| host:", HOST)
print("Warehouse check:", run_sql("SELECT 1 AS ok"))

# COMMAND ----------

# MAGIC %md ## Choice 2 — Inventory endpoints

# COMMAND ----------

eps = list(w.serving_endpoints.list())
print(f"{len(eps)} serving endpoints:")
for e in eps[:50]:
    print(" -", e.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Choice 2b — v1 (legacy) vs v3 (model service) split
# MAGIC A call naming a legacy endpoint lands with `service_name` NULL (v1); a model-service FQN
# MAGIC lands with `service_name` set (v3). Any **v1** row is traffic that breaks at the killswitch.

# COMMAND ----------

rows = run_sql(load_query("endpoint_inventory_v1_v3", days="30"))
for r in rows:
    print(r)
v1 = [r for r in rows if str(r.get("gateway_path", "")).startswith("v1")]
print(f"\n{len(v1)} target(s) still on the v1 path — migrate these to a model service.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Choice 3 — Model services (the governed object)
# MAGIC Client contract moves together: base URL `/serving-endpoints` → `/ai-gateway/mlflow/v1`,
# MAGIC and model `<endpoint-name>` → `<catalog>.<schema>.<service>`. No in-place rename.

# COMMAND ----------

try:
    svc = w.api_client.do("GET", "/api/2.1/unity-catalog/model-services")
    names = [s.get("name", "").split("/", 1)[-1] for s in (svc or {}).get("model_services", [])]
    print(f"{len(names)} model service(s):")
    for n in names[:20]:
        print(" -", n)
except Exception as e:
    print("Could not list model services (Unity AI Gateway may not be enabled):", str(e)[:200])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cost 5 — Routing compare (the custom-router idea)
# MAGIC Send one prompt to each tier and compare tokens. The app adds a classifier that picks the
# MAGIC cheapest sufficient tier; here we just show the spread. Retarget endpoints to your workspace.

# COMMAND ----------

TIERS = {
    "cheap": "databricks-meta-llama-3-1-8b-instruct",
    "mid": "databricks-meta-llama-3-3-70b-instruct",
    "frontier": "databricks-claude-sonnet-4-5",
}
PROMPT = "Summarize the key cost drivers of running large language models in production."

for tier, endpoint in TIERS.items():
    try:
        # The gateway chat path accepts a plain endpoint name in `model` and, unlike the SDK's
        # query(), can carry the request-tag header used for per-project attribution.
        resp = w.api_client.do(
            "POST", "/ai-gateway/mlflow/v1/chat/completions",
            headers={"Databricks-Ai-Gateway-Request-Tags": json.dumps({"project": PROJECT})},
            body={"model": endpoint, "messages": [{"role": "user", "content": PROMPT}]},
        )
        usage = (resp or {}).get("usage", {})
        print(f"{tier:9} {endpoint:45} tokens={usage.get('total_tokens')}")
    except Exception as e:
        print(f"{tier:9} {endpoint:45} ERROR {str(e)[:120]}")

# COMMAND ----------

# MAGIC %md ## Cost 6 · 8 · 9 — Spend, budget, and tagged usage (system tables)

# COMMAND ----------

print("Spend by model (30d):")
for r in run_sql(load_query("spend_by_model")):
    print(" ", r)

print("\nBudget basis — spend by model & user (a non-admin can run this for their own rows):")
for r in run_sql(load_query("budget_status")):
    print(" ", r)

print(f"\nUsage attributed to project '{PROJECT}' (request- vs endpoint-tagged):")
for r in run_sql(load_query("usage_by_project", project=f"'{PROJECT}'")):
    print(" ", r)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cost 7 — Rate limits (manual)
# MAGIC Rate limits are the hard throughput control (HTTP 429). Set them in the AI Gateway UI on
# MAGIC the endpoint, then read them back:

# COMMAND ----------

GOVERNED = "ai-governance-workshop-governed"  # your governed endpoint name
try:
    ep = w.serving_endpoints.get(GOVERNED)
    print("ai_gateway config:", ep.ai_gateway)
except Exception as e:
    print(f"Endpoint '{GOVERNED}' not found yet — create it below, then set limits in the UI. ({str(e)[:120]})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Control 10 · 11 — Governed endpoint & who can call it
# MAGIC The app creates the governed endpoint only if you run that step; do it in the UI or with a
# MAGIC PUT to `/api/2.0/serving-endpoints/<name>/config`. Then read the ACL:

# COMMAND ----------

try:
    ep = w.serving_endpoints.get(GOVERNED)
    acl = w.api_client.do("GET", f"/api/2.0/permissions/serving-endpoints/{ep.id}")
    for a in (acl or {}).get("access_control_list", []):
        print(a.get("group_name") or a.get("user_name") or a.get("service_principal_name"),
              "->", [p.get("permission_level") for p in a.get("all_permissions", [])])
    print("\nWatch for: a broad group with CAN_QUERY (open to everyone); keep CAN_MANAGE to admins.")
except Exception as e:
    print("Create the governed endpoint first.", str(e)[:150])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Control 12 · 13 — Guardrails & MCP policy (mostly manual)
# MAGIC - **Guardrails:** configure PII/safety in the AI Gateway UI; the keyword blocklist is a UC
# MAGIC   SQL function you attach. Test by sending a prompt that should be blocked — a block is the
# MAGIC   pass condition.
# MAGIC - **MCP policy:** a UC SQL function returning ALLOW/DENY. Note `to_variant_object(...)`
# MAGIC   (not `to_variant`) and cast VARIANT paths: `event:context.tool.name::STRING`. Attach it
# MAGIC   in the AI Gateway UI, then call the service over JSON-RPC to confirm DENY on a write tool.

# COMMAND ----------

# These are the same DDLs the app runs, loaded from queries/ so there's one source of truth.
# Creating a function is the one write here; it changes no endpoint behavior until you ATTACH it
# in the AI Gateway UI.
if CATALOG and SCHEMA:
    keyword_ddl = load_query(
        "keyword_blocklist_policy",
        function_fqn=f"{CATALOG}.{SCHEMA}.keyword_blocklist_policy",
        keywords="'social security number', 'credit card number'",
    )
    mcp_ddl = load_query(
        "mcp_service_policy",
        function_fqn=f"{CATALOG}.{SCHEMA}.mcp_read_only_policy",
        deny_tools="'create_issue', 'push_files'",
        reason="'Blocked by workshop policy.'",
    )
    print("--- keyword blocklist guardrail ---\n", keyword_ddl)
    print("--- MCP service policy ---\n", mcp_ddl)
    # run_sql(keyword_ddl); run_sql(mcp_ddl)   # uncomment to create them
else:
    print("Set the catalog widget to generate the policy DDL.")

# COMMAND ----------

# MAGIC %md ## Control 14 — Audit & secret-leak scan

# COMMAND ----------

import re
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")
rows = run_sql(load_query("audit_scan"))
leaks = [r for r in rows if SECRET_RE.search(json.dumps(r, default=str))]
print(f"{len(rows)} recent denied/failed call(s); {len(leaks)} with secret-shaped arguments.")
for r in rows[:10]:
    print(" ", r)
