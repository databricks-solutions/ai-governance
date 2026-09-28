# Databricks notebook source
# MAGIC %md
# MAGIC # Unity Gateway Workshop — Production Runbook
# MAGIC
# MAGIC The workshop app proves governance interactively. This notebook is the **production
# MAGIC hand-off**: every SQL statement and CI/CD command the app relies on, gathered so a
# MAGIC platform team can stand the same controls up **outside** the app — in a job, a pipeline,
# MAGIC or by hand — as part of a real rollout.
# MAGIC
# MAGIC Nothing here is magic the app does secretly: each cell mirrors what a workshop step runs.
# MAGIC The app addresses the governed model on the **v3 Unity Catalog plane** — a model service
# MAGIC `catalog.schema.service` on `/ai-gateway/mlflow/v1`, **never** a legacy v1 serving
# MAGIC endpoint by flat name (the only v1 read left is the Choice "flag v1 vs v3" inventory).
# MAGIC
# MAGIC Set the widgets, then run top to bottom. Grants and service creation need an
# MAGIC **account/metastore admin**; the read queries need `SELECT` on the `system` schemas.

# COMMAND ----------

dbutils.widgets.text("catalog", "uaigw_fe", "UC catalog")
dbutils.widgets.text("schema", "workshop", "UC schema")
dbutils.widgets.text("service", "governed", "Governed model service (bare name)")
dbutils.widgets.text("app_service_principal", "<app-service-principal>", "App SP (databricks apps get ...)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SERVICE = dbutils.widgets.get("service")
FQN = f"{CATALOG}.{SCHEMA}.{SERVICE}"          # the governed model service, v3 UC securable
APP_SP = dbutils.widgets.get("app_service_principal")
print("Governed model service FQN:", FQN)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. CI/CD — deploy the app (Databricks Asset Bundle)
# MAGIC
# MAGIC Run these in a shell (CI runner or laptop) from `workshop_app/`, not in the notebook.
# MAGIC The bundle is the single source of truth: catalog/schema/warehouse reach the app as env,
# MAGIC and it grants the app's own service principal on the schema/volume in one pass.
# MAGIC
# MAGIC ```bash
# MAGIC # 0. One-time auth (creates the named profile the commands reuse)
# MAGIC databricks auth login --host https://<workspace>.cloud.databricks.com --profile <profile>
# MAGIC
# MAGIC # 1. Validate (catches config/schema errors before touching the workspace)
# MAGIC databricks bundle validate -t dev -p <profile> --var="warehouse_id=<id>"
# MAGIC
# MAGIC # 2. Deploy — builds the UI, creates the schema + progress volume + app, grants the app SP.
# MAGIC #    On a CUSTOMER workspace ALWAYS pass --var="catalog=<uc-catalog>" (uaigw_fe is internal).
# MAGIC databricks bundle deploy -t dev -p <profile> \
# MAGIC   --var="warehouse_id=<id>" --var="catalog=<uc-catalog>"
# MAGIC
# MAGIC # 3. Start app compute (a deploy alone does NOT start it — this second command is required)
# MAGIC databricks bundle run ai_governance_workshop_app -t dev -p <profile> \
# MAGIC   --var="warehouse_id=<id>" --var="catalog=<uc-catalog>"
# MAGIC
# MAGIC # 4. Health + on-behalf-of (OBO) verification
# MAGIC #    /api/health must return {"status":"ok","config_problems":[]}.
# MAGIC #    effective_user_api_scopes must include serving.serving-endpoints for OBO to work.
# MAGIC databricks apps get ai-governance-workshop -p <profile> -o json \
# MAGIC   | jq '{state: .app_status.state, scopes: .effective_user_api_scopes}'
# MAGIC ```
# MAGIC
# MAGIC Made a change? Re-run steps 2 and 3. The internal hosted instance needs only
# MAGIC `--var="warehouse_id=..."` (catalog/schema default to `uaigw_fe`/`workshop`).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Access grants (account/metastore admin)
# MAGIC
# MAGIC Two `system` grants let the app read Gateway telemetry (the cost/audit steps), and one
# MAGIC grant on the governed model service is how you scope **who can call it** on the v3 plane:
# MAGIC `EXECUTE` = can call, `MANAGE` = can reconfigure (keep with admins — the shadow-service
# MAGIC risk). Replace `<app-service-principal>` via the widget.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Telemetry reads (cost + audit steps). Get the app SP with:
# MAGIC --   databricks apps get ai-governance-workshop -o json | jq -r .service_principal_client_id
# MAGIC GRANT USE CATALOG ON CATALOG system TO `${app_service_principal}`;
# MAGIC GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO `${app_service_principal}`;
# MAGIC GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO `${app_service_principal}`;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Who can CALL the governed model service (Control > "Review who can call the model
# MAGIC -- service"). Grant EXECUTE to the pilot group; never a broad group like `account users`.
# MAGIC -- Inspect current grants:
# MAGIC SHOW GRANTS ON MODEL SERVICE ${catalog}.${schema}.${service};
# MAGIC -- Scope it to the pilot group (example):
# MAGIC -- GRANT EXECUTE ON MODEL SERVICE ${catalog}.${schema}.${service} TO `pilot-group`;
# MAGIC -- Revoke an over-broad grant:
# MAGIC -- REVOKE EXECUTE ON MODEL SERVICE ${catalog}.${schema}.${service} FROM `account users`;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Stand up the governed model service (v3)
# MAGIC
# MAGIC The app never creates this unattended on a customer workspace (guided UI step). Its
# MAGIC create/verify Try-It reads `GET /api/2.1/unity-catalog/model-services/{fqn}`. For a
# MAGIC scripted rollout, create it in front of a base model, then verify below.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
try:
    svc = w.api_client.do("GET", f"/api/2.1/unity-catalog/model-services/{FQN}")
    conf = (svc or {}).get("config", {}) or {}
    print(f"✓ Model service {FQN} exists")
    print("  rate_limits configured:", bool(conf.get("rate_limits")))
    print("  inference table:", bool(conf.get("inference_table_config") or conf.get("auto_capture_config")))
except Exception as e:
    print(f"✗ {FQN} not found — create it in the AI Gateway UI in front of the base model, "
          f"attach an inference table + rate limits, then re-run.\n  {str(e)[:300]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Guardrail policies (UC service policies)
# MAGIC
# MAGIC A service policy is a UC SQL function returning `to_variant_object(...)` with `result`
# MAGIC (ALLOW/DENY/ASK). **Creating the function is automatable; ATTACHING it to the service is
# MAGIC UI-only in Beta** (AI Gateway > Policies). Two policies the workshop uses — model-service
# MAGIC keyword blocklist, and MCP-service write-tool deny. The app ships these as
# MAGIC `queries/keyword_blocklist_policy.sql` and `queries/mcp_service_policy.sql`.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Keyword-blocklist guardrail for the governed MODEL service (event carries the prompt).
# MAGIC -- Attach it in the AI Gateway Policies tab (ON_CALL) after creating it. Fail-closed.
# MAGIC CREATE OR REPLACE FUNCTION ${catalog}.${schema}.keyword_blocklist_policy(event VARIANT)
# MAGIC RETURNS VARIANT
# MAGIC RETURN CASE
# MAGIC   WHEN exists(
# MAGIC          array('social security number', 'credit card number'),
# MAGIC          kw -> lower(event:input.messages[0].content::STRING) LIKE concat('%', kw, '%'))
# MAGIC   THEN to_variant_object(named_struct('result', 'DENY', 'reason', 'Blocked keyword in request.'))
# MAGIC   ELSE to_variant_object(named_struct('result', 'ALLOW', 'reason', ''))
# MAGIC END;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- MCP service policy: ALLOW reads, DENY named write tools (event carries the tool name).
# MAGIC -- Attach it in the AI Gateway Policies tab on the MCP service.
# MAGIC CREATE OR REPLACE FUNCTION ${catalog}.${schema}.mcp_read_only_policy(event VARIANT)
# MAGIC RETURNS VARIANT
# MAGIC RETURN CASE
# MAGIC   WHEN event:context.tool.name::STRING IN ('get_file_contents')
# MAGIC   THEN to_variant_object(named_struct('result', 'DENY', 'reason', 'Blocked by workshop policy.'))
# MAGIC   ELSE to_variant_object(named_struct('result', 'ALLOW', 'reason', ''))
# MAGIC END;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. On-behalf-of (OBO) for MCP
# MAGIC
# MAGIC MCP tool calls run **as the signed-in user**, not the app service principal, so identity
# MAGIC propagates to the upstream provider. Two `databricks.yml` fields on the app resource
# MAGIC enable it (already set in this repo):
# MAGIC
# MAGIC ```yaml
# MAGIC resources:
# MAGIC   apps:
# MAGIC     ai_governance_workshop_app:
# MAGIC       forward_user_access_token: true          # pass the user token to the app
# MAGIC       user_api_scopes:                          # scopes users consent to on first open
# MAGIC         - serving.serving-endpoints
# MAGIC ```
# MAGIC
# MAGIC The app reads `X-Forwarded-Access-Token` per request and builds a user-scoped client
# MAGIC (`server/config.py`). Without these, the OBO step honestly reports it ran as the app SP.
# MAGIC Provider-backed MCP services (e.g. `system.ai.github`) also need the **user** to have
# MAGIC consented to that connection. Verify: `... apps get ... | jq .effective_user_api_scopes`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. The telemetry queries the app runs
# MAGIC
# MAGIC These read `system.ai_gateway.*` and `system.access.audit` — the proof that cost and
# MAGIC control fired. Run them directly for a dashboard or a scheduled job. Each mirrors a
# MAGIC workshop step (source: `workshop_app/queries/*.sql`).

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Cost > 30-day spend by model (queries/spend_by_model.sql)
# MAGIC SELECT usage_metadata.model AS model, usage_metadata.provider AS provider,
# MAGIC        ROUND(SUM(usage_quantity), 2) AS usd
# MAGIC FROM system.ai_gateway.external_model_spend
# MAGIC WHERE usage_date > current_date() - 30
# MAGIC GROUP BY 1, 2 ORDER BY usd DESC LIMIT 20;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Choice > flag v1 vs v3 traffic (queries/endpoint_inventory_v1_v3.sql). service_name
# MAGIC -- NULL = a call that named a plain endpoint (v1); service_name set = a model-service FQN
# MAGIC -- (v3). This split is the migration-backlog signal — the ONE place v1 is read on purpose.
# MAGIC SELECT CASE WHEN service_name IS NULL THEN 'v1 (endpoint name)' ELSE 'v3 (model service)' END AS plane,
# MAGIC        COUNT(*) AS requests, SUM(total_tokens) AS tokens
# MAGIC FROM system.ai_gateway.usage
# MAGIC WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
# MAGIC GROUP BY 1 ORDER BY requests DESC;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Control > audit trail scan (queries/audit_scan.sql reads system.access.audit).
# MAGIC SELECT event_time, action_name, request_params
# MAGIC FROM system.access.audit
# MAGIC WHERE service_name = 'aibraingateway'
# MAGIC   AND event_time > current_timestamp() - INTERVAL 7 DAYS
# MAGIC ORDER BY event_time DESC LIMIT 50;

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC **Full query sources** live in `workshop_app/queries/` — this notebook shows the
# MAGIC production-critical ones with concrete values. The app runs them with the same SQL,
# MAGIC filling `${...}` placeholders from `config/workshop.yaml`.
