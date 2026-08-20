# Databricks notebook source
# MAGIC %md
# MAGIC # Agent Registry — reference queries
# MAGIC
# MAGIC Standalone version of the checks the **Agent Registry** accelerator runs inside the AI
# MAGIC Governance Workshop app, so you can reference and run them without deploying the app.
# MAGIC Each section mirrors one in-app step and its `test`. SQL runs through `spark.sql`;
# MAGIC everything else uses the Databricks SDK. See `README.md` for the concepts.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "ai_governance_workshop", "Workshop schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
w = WorkspaceClient()

# Endpoint-name substrings the app uses to spot "agent-like" endpoints.
_AGENT_HINTS = ("agent", "assistant", "bot", "rag", "chain")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Inventory registered agents & tools (`list_registered_assets`)
# MAGIC An agent registry makes agents first-class Unity Catalog assets — discoverable,
# MAGIC versioned, and owned. List the registered models (agents) and UC functions (tools) in
# MAGIC the workshop schema.

# COMMAND ----------

agents = list(w.registered_models.list(catalog_name=CATALOG, schema_name=SCHEMA))
tools = list(w.functions.list(catalog_name=CATALOG, schema_name=SCHEMA))
print(f"{len(agents)} registered agent(s):")
for m in agents:
    print("  -", m.full_name)
print(f"\n{len(tools)} UC function(s) (tools):")
for f in tools:
    print("  -", f.full_name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Confirm versioning & ownership (`agent_versions`)
# MAGIC A one-off deploy is not a registered agent. Each should be a UC model with an owner and
# MAGIC a version history, so it is reproducible and rollback-able.

# COMMAND ----------

for m in agents:
    versions = list(w.model_versions.list(full_name=m.full_name))
    print(f"{m.full_name}  owner={m.owner}  versions={len(versions)}")
if not agents:
    print("No registered agents yet — register one (MLflow → UC model), then re-run.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Confirm traces & telemetry (`telemetry_readiness`)
# MAGIC A registered agent should emit telemetry. Confirm the AI telemetry tables are present
# MAGIC and receiving rows. (These `system` schemas require an account-admin grant — see the
# MAGIC accelerator README.)

# COMMAND ----------

display(spark.sql("""
    SELECT 'system.ai_gateway.usage' AS source, COUNT(*) AS rows_last_24h
    FROM system.ai_gateway.usage
    WHERE event_time > current_timestamp() - INTERVAL 1 DAY
"""))

display(spark.sql("""
    SELECT 'system.access.audit' AS source, COUNT(*) AS rows_last_24h
    FROM system.access.audit
    WHERE event_date >= current_date() - INTERVAL 1 DAY
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Govern the agent endpoint itself (`agent_sp_attribution`)
# MAGIC A custom agent endpoint may lack the controls a model endpoint has — rate limits,
# MAGIC guardrails, usage tracking. Where a control is missing, that agent's traffic is
# MAGIC ungoverned. Inspect agent-like endpoints and report which controls each carries.

# COMMAND ----------

rows = []
for ep in w.serving_endpoints.list():
    if not any(h in (ep.name or "").lower() for h in _AGENT_HINTS):
        continue
    full = w.serving_endpoints.get(ep.name)
    gw = full.ai_gateway
    rows.append({
        "endpoint": ep.name,
        "usage_tracking": bool(gw and gw.usage_tracking_config),
        "inference_table": bool(gw and gw.inference_table_config),
        "rate_limits": bool(gw and gw.rate_limits),
        "guardrails": bool(gw and gw.guardrails),
    })
if rows:
    display(spark.createDataFrame(rows))
else:
    print("No agent-like endpoints found by name (agent/assistant/bot/rag/chain).")
