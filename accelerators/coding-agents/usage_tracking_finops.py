# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 02 — Usage tracking & FinOps
# MAGIC
# MAGIC Turn Gateway telemetry into tokens, cost, and a budget alert.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# Self-contained setup. This accelerator notebook is meant to be referenced and run on its
# own, so the shared helper these notebooks used is inlined here: widgets for the endpoint/catalog/
# schema, a configured WorkspaceClient (`w`), the workspace REST host/token, and the small
# Gateway helpers. Adjust the widgets to point at your workspace.
import json
import time

import requests
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("endpoint_name", "ai-governance-gateway", "Gateway serving endpoint")
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "ai_governance", "Schema for governance artifacts")

ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

print(f"Endpoint : {ENDPOINT_NAME}")
print(f"Catalog  : {CATALOG}")
print(f"Schema   : {SCHEMA}")

w = WorkspaceClient()

# Host + token for the few Gateway operations driven over raw REST (the typed SDK surface for
# AI Gateway is still expanding while the feature is in Beta).
_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
HOST = _ctx.apiUrl().get()
TOKEN = _ctx.apiToken().get()
_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def get_ai_gateway(endpoint_name: str = None) -> dict:
    """Return the current AI Gateway configuration for an endpoint."""
    name = endpoint_name or ENDPOINT_NAME
    resp = requests.get(f"{HOST}/api/2.0/serving-endpoints/{name}", headers=_HEADERS)
    resp.raise_for_status()
    return resp.json().get("ai_gateway", {})


_GATEWAY_KEYS = [
    "usage_tracking_config",
    "inference_table_config",
    "rate_limits",
    "guardrails",
    "fallback_config",
]


def put_ai_gateway(config: dict, endpoint_name: str = None) -> dict:
    """Update the AI Gateway configuration for an endpoint, merging into what's already set.

    The `/ai-gateway` PUT replaces the *entire* gateway config, so this helper does a
    read-modify-write: it reads the current config and overlays the keys you pass. Pass a key
    with value `None` to remove that control (e.g. `{"guardrails": None}`).
    """
    name = endpoint_name or ENDPOINT_NAME
    current = get_ai_gateway(name)
    merged = {k: current[k] for k in _GATEWAY_KEYS if k in current}
    for k, v in config.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    resp = requests.put(
        f"{HOST}/api/2.0/serving-endpoints/{name}/ai-gateway",
        headers=_HEADERS,
        data=json.dumps(merged),
    )
    resp.raise_for_status()
    return resp.json()


def external_entity(name: str, target_endpoint: str, task: str = "llm/v1/chat") -> dict:
    """Build an external-model served entity that wraps another Databricks serving endpoint
    (provider `databricks-model-serving`). Reuses a shared auth secret."""
    return {
        "name": name,
        "external_model": {
            "name": target_endpoint,
            "provider": "databricks-model-serving",
            "task": task,
            "databricks_model_serving_config": {
                "databricks_workspace_url": HOST,
                "databricks_api_token": "{{secrets/ai_governance/api_token}}",
            },
        },
    }


def primary_target(endpoint_name: str = None) -> str:
    """Return the target the current `primary` served entity wraps: its external-model name,
    or the served-entity/entity name when the primary is a native (non-external) model."""
    name = endpoint_name or ENDPOINT_NAME
    se = w.serving_endpoints.get(name).config.served_entities[0]
    if se.external_model is not None:
        return se.external_model.name
    return se.entity_name or se.name


def update_config(served_entities: list, traffic_config: dict = None, endpoint_name: str = None) -> dict:
    """Update an endpoint's served entities (and optionally traffic config), then wait for it
    to finish reconciling."""
    name = endpoint_name or ENDPOINT_NAME
    body = {"served_entities": served_entities}
    if traffic_config:
        body["traffic_config"] = traffic_config
    resp = requests.put(
        f"{HOST}/api/2.0/serving-endpoints/{name}/config",
        headers=_HEADERS,
        data=json.dumps(body),
    )
    resp.raise_for_status()
    w.serving_endpoints.wait_get_serving_endpoint_not_updating(name=name)
    return resp.json()


def invoke(messages, endpoint_name: str = None, **params) -> dict:
    """Send a chat completion request through the governed endpoint. `messages` may be a
    string (a single user turn) or a list of role/content dicts. Returns the raw JSON."""
    name = endpoint_name or ENDPOINT_NAME
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    payload = {"messages": messages, **params}
    resp = requests.post(
        f"{HOST}/serving-endpoints/{name}/invocations",
        headers=_HEADERS,
        data=json.dumps(payload),
    )
    return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}


def show_json(obj) -> None:
    """Pretty-print a dict/list for notebook output."""
    print(json.dumps(obj, indent=2, default=str))

# COMMAND ----------

# MAGIC %md ### Confirm telemetry is on

# COMMAND ----------

gw = get_ai_gateway()
show_json({k: gw.get(k) for k in ["usage_tracking_config", "inference_table_config"]})

# COMMAND ----------

# MAGIC %md ### Generate traffic

# COMMAND ----------

for i in range(5):
    invoke(f"Give me one fun fact about data governance (#{i}).", max_tokens=60)
print("Sent 5 requests through the gateway endpoint.")

# COMMAND ----------

# MAGIC %md ### Token usage from system tables

# COMMAND ----------

usage = spark.sql(
    f"""
    SELECT
      u.requester                                  AS user,
      date(u.request_time)                         AS day,
      count(*)                                     AS requests,
      sum(u.input_token_count)                     AS input_tokens,
      sum(u.output_token_count)                    AS output_tokens,
      sum(u.input_token_count + u.output_token_count) AS total_tokens
    FROM system.serving.endpoint_usage u
    JOIN system.serving.served_entities se
      ON u.served_entity_id = se.served_entity_id
    WHERE se.endpoint_name = '{ENDPOINT_NAME}'
      AND u.request_time >= current_date() - INTERVAL 7 DAYS
    GROUP BY u.requester, date(u.request_time)
    ORDER BY day DESC, total_tokens DESC
    """
)
display(usage)

# COMMAND ----------

# MAGIC %md ### Cost from billing system tables

# COMMAND ----------

cost = spark.sql(
    f"""
    WITH priced AS (
      SELECT
        u.usage_date,
        u.usage_metadata.endpoint_name AS endpoint_name,
        u.usage_quantity * p.pricing.default AS cost_usd
      FROM system.billing.usage u
      JOIN system.billing.list_prices p
        ON u.sku_name = p.sku_name
       AND u.usage_unit = p.usage_unit
       AND u.usage_end_time BETWEEN p.price_start_time AND coalesce(p.price_end_time, current_timestamp())
      WHERE u.billing_origin_product = 'MODEL_SERVING'
        AND u.usage_date >= current_date() - INTERVAL 30 DAYS
    )
    SELECT usage_date, endpoint_name, round(sum(cost_usd), 2) AS cost_usd
    FROM priced
    WHERE endpoint_name = '{ENDPOINT_NAME}'
    GROUP BY usage_date, endpoint_name
    ORDER BY usage_date DESC
    """
)
display(cost)

# COMMAND ----------

# MAGIC %md ### Budget alert

# COMMAND ----------

MONTHLY_BUDGET_USD = 100.0

mtd = (
    cost.where("usage_date >= date_trunc('MONTH', current_date())")
    .groupBy()
    .sum("cost_usd")
    .collect()
)
spend = (mtd[0][0] or 0.0) if mtd else 0.0
pct = 100 * spend / MONTHLY_BUDGET_USD if MONTHLY_BUDGET_USD else 0
print(f"Month-to-date spend on {ENDPOINT_NAME}: ${spend:,.2f} ({pct:.1f}% of ${MONTHLY_BUDGET_USD:,.0f} budget)")
if spend > MONTHLY_BUDGET_USD:
    print("⚠️  OVER BUDGET — tighten rate limits or review top consumers above.")
else:
    print("✅ Within budget.")

# COMMAND ----------

# MAGIC %md ### Inference (payload) table

# COMMAND ----------

payload_table = f"{CATALOG}.{SCHEMA}.gateway_payload"
try:
    display(spark.sql(f"SELECT * FROM {payload_table} ORDER BY timestamp_ms DESC LIMIT 20"))
except Exception as e:  # noqa: BLE001
    print(f"Payload table {payload_table} not queryable yet (rows can lag a few minutes): {e}")
