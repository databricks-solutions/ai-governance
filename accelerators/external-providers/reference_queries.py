# Databricks notebook source
# MAGIC %md
# MAGIC # External Providers — reference queries
# MAGIC
# MAGIC Standalone version of the checks the **External Providers** accelerator runs inside the
# MAGIC AI Governance Workshop app, so you can reference and run them without deploying the app.
# MAGIC Each section mirrors one in-app step and its `test`. SQL runs through `spark.sql`;
# MAGIC everything else uses the Databricks SDK / REST. See `README.md`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import json

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "main", "Approved-models catalog to check for isolation")
dbutils.widgets.text("project", "ai_governance_workshop", "Project tag to attribute usage to")

CATALOG = dbutils.widgets.get("catalog")
PROJECT = dbutils.widgets.get("project")
w = WorkspaceClient()

# Endpoint-name substrings the app treats as external-provider routes.
_EXTERNAL_HINTS = ("bedrock", "openai", "gpt", "anthropic", "claude", "external")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Inventory current provider access (`list_endpoints`)
# MAGIC Map how external providers are reached today. The target is a single governed path;
# MAGIC start by listing the serving endpoints that exist.

# COMMAND ----------

endpoints = list(w.serving_endpoints.list())
print(f"{len(endpoints)} serving endpoint(s):")
for ep in endpoints:
    print("  -", ep.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Route a provider through the Gateway (`external_provider_routing`)
# MAGIC Which serving endpoints look like external-model providers routed through the Gateway
# MAGIC (Bedrock / OpenAI / Anthropic)? Registering them as external models behind a governed
# MAGIC endpoint makes them inherit the same limits, guardrails, and logging.

# COMMAND ----------

external = [ep.name for ep in endpoints if any(h in (ep.name or "").lower() for h in _EXTERNAL_HINTS)]
print("External-provider-looking endpoints:", external or "(none found by name)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Credentials in secrets, never inline (`provider_secret_readiness`)
# MAGIC A provider key pasted into config is the first pitfall. Store it in a secret scope and
# MAGIC reference it as `{{secrets/<scope>/<key>}}` — a read of the endpoint then returns the
# MAGIC reference, never the value. List the scopes and check which external endpoints reference
# MAGIC a secret.

# COMMAND ----------

scopes = [s.name for s in w.secrets.list_scopes()]
print("Secret scopes:", scopes)

def references_secret(ep_name: str) -> bool:
    full = w.serving_endpoints.get(ep_name)
    blob = json.dumps(full.as_dict(), default=str)
    return "{{secrets/" in blob

for name in external:
    print(f"  {name}: references a secret = {references_secret(name)}")
if not external:
    print("No external endpoints to check yet.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Bind approved models to approved workspaces (`workspace_binding_check`)
# MAGIC "Approved models" is only advisory until the catalog is `isolation_mode = ISOLATED` with
# MAGIC explicit workspace bindings — otherwise any workspace on the metastore can bind it.

# COMMAND ----------

cat = w.catalogs.get(CATALOG)
print("Catalog:", CATALOG, "| isolation_mode:", cat.isolation_mode)
if str(cat.isolation_mode) == "ISOLATED":
    bindings = w.api_client.do("GET", f"/api/2.1/unity-catalog/bindings/catalog/{CATALOG}")
    print(json.dumps(bindings, indent=2, default=str))
else:
    print(">>> Not ISOLATED — the approved-models list is advisory only until you isolate + bind.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Confirm routed usage by project (`usage_by_project`)
# MAGIC Migrate one workload that bypasses governance onto the governed endpoint, then confirm
# MAGIC its traffic and cost attribute by project tag (request tag or endpoint tag).

# COMMAND ----------

p = "'" + PROJECT.replace("'", "''") + "'"
display(spark.sql(f"""
    SELECT requester,
           COALESCE(service_name, endpoint_name) AS target,
           SUM(CASE WHEN request_tags['project']  = {p} THEN 1 ELSE 0 END) AS request_tagged,
           SUM(CASE WHEN endpoint_tags['project'] = {p} THEN 1 ELSE 0 END) AS endpoint_tagged,
           COUNT(*)          AS requests,
           SUM(total_tokens) AS tokens
    FROM system.ai_gateway.usage
    WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
      AND (request_tags['project'] = {p} OR endpoint_tags['project'] = {p})
    GROUP BY 1, 2 ORDER BY tokens DESC LIMIT 20
"""))

# Table watermark — if the query above is empty, check how fresh the usage table is.
display(spark.sql("""
    SELECT max(event_time) AS latest_event, current_timestamp() AS now_ts
    FROM system.ai_gateway.usage
"""))
