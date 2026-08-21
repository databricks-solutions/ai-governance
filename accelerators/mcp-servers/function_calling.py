# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Function calling with Unity Catalog functions
# MAGIC
# MAGIC Hand a governed UC function to a model and run a full tool-calling round trip.
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

# MAGIC %md ### Create the tool (a Unity Catalog function)

# COMMAND ----------

spark.sql(
    f"""
    CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.lookup_order_status(order_id STRING)
    RETURNS STRING
    COMMENT 'Look up the fulfillment status of an order by its ID.'
    RETURN
      CASE
        WHEN order_id = 'A1001' THEN 'shipped'
        WHEN order_id = 'A1002' THEN 'processing on line 3'
        ELSE 'unknown order'
      END
    """
)
print(f"Created tool: {CATALOG}.{SCHEMA}.lookup_order_status")

# COMMAND ----------

# MAGIC %md ### Describe the tool to the model

# COMMAND ----------

FUNCTION_NAME = "lookup_order_status"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": FUNCTION_NAME,
            "description": "Look up the fulfillment status of an order by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. A1001"}
                },
                "required": ["order_id"],
            },
        },
    }
]


def run_uc_tool(name: str, args: dict):
    """Execute a Unity Catalog function by name with the model-supplied arguments."""
    if name == FUNCTION_NAME:
        row = spark.sql(
            f"SELECT {CATALOG}.{SCHEMA}.lookup_order_status(:order_id) AS result",
            args={"order_id": args.get("order_id", "")},
        ).collect()
        return row[0]["result"]
    return f"unknown tool: {name}"

# COMMAND ----------

# MAGIC %md ### Tool-calling round trip

# COMMAND ----------

import json

messages = [{"role": "user", "content": "Can you check the status of order A1002 for me?"}]

# Turn 1: the model decides whether to call a tool.
resp = invoke(messages, tools=TOOLS, tool_choice="auto", max_tokens=256)
assert resp["status_code"] == 200, resp
choice = resp["body"]["choices"][0]
print("finish_reason:", choice.get("finish_reason"))
tool_calls = choice["message"].get("tool_calls") or []
show_json(tool_calls)

# COMMAND ----------

# Execute each requested tool call against Unity Catalog.
messages.append(choice["message"])  # the assistant turn carrying the tool_calls
for tc in tool_calls:
    args = json.loads(tc["function"]["arguments"])
    result = run_uc_tool(tc["function"]["name"], args)
    print(f"executed {tc['function']['name']}({args}) -> {result}")
    messages.append(
        {"role": "tool", "tool_call_id": tc["id"], "content": str(result)}
    )

# COMMAND ----------

# Turn 2: the model answers using the tool result.
final = invoke(messages, max_tokens=256)
print("HTTP", final["status_code"])
print(final["body"]["choices"][0]["message"]["content"])
