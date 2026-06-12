# Databricks notebook source
# MAGIC %md
# MAGIC # Shared setup for the Unity AI Gateway labs
# MAGIC
# MAGIC `%run` this notebook from any lab to get:
# MAGIC
# MAGIC - Notebook **widgets** for `endpoint_name`, `catalog`, and `schema` (overridable per run).
# MAGIC - A configured `WorkspaceClient` (`w`) and the workspace REST host/token.
# MAGIC - Small helpers to read/update the AI Gateway config of an endpoint and to invoke it.
# MAGIC
# MAGIC Nothing here is lab-specific — each lab layers its own Gateway control on top.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("endpoint_name", "ai-governance-gateway", "Gateway serving endpoint")
dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "ai_governance", "Schema for governance artifacts")

ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

print(f"Endpoint : {ENDPOINT_NAME}")
print(f"Catalog  : {CATALOG}")
print(f"Schema   : {SCHEMA}")

# COMMAND ----------

import json
import time

import requests
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Host + token for the few Gateway operations we drive over raw REST (the typed SDK
# surface for AI Gateway is still expanding while the feature is in Beta).
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


def put_ai_gateway(config: dict, endpoint_name: str = None) -> dict:
    """Update (PUT) the AI Gateway configuration for an endpoint.

    `config` keys: usage_tracking_config, inference_table_config, rate_limits,
    guardrails, fallback_config. Only the keys you pass are changed.
    """
    name = endpoint_name or ENDPOINT_NAME
    resp = requests.put(
        f"{HOST}/api/2.0/serving-endpoints/{name}/ai-gateway",
        headers=_HEADERS,
        data=json.dumps(config),
    )
    resp.raise_for_status()
    return resp.json()


def invoke(messages, endpoint_name: str = None, **params) -> dict:
    """Send a chat completion request through the governed endpoint.

    `messages` may be a string (treated as a single user turn) or a list of
    role/content dicts. Returns the raw JSON response.
    """
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


print("Loaded helpers: get_ai_gateway, put_ai_gateway, invoke, show_json")
