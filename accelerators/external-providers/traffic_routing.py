# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 04 — Traffic routing
# MAGIC
# MAGIC Split traffic across served entities for load balancing and A/B/canary rollouts.
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

# MAGIC %md ### Two served entities, 50/50 split

# COMMAND ----------

# Both entities wrap Databricks Foundation Models as external models (see Lab 03).
# `external_entity` / `primary_target` / `update_config` are defined in the setup cell above.
CHAMPION_TARGET = primary_target()  # keep whatever the endpoint currently fronts
CHALLENGER_TARGET = "databricks-gpt-oss-120b"
print(f"Champion wraps:   {CHAMPION_TARGET}")
print(f"Challenger wraps: {CHALLENGER_TARGET}")

ENTITIES = [
    external_entity("champion", CHAMPION_TARGET),
    external_entity("challenger", CHALLENGER_TARGET),
]

update_config(
    served_entities=ENTITIES,
    traffic_config={
        "routes": [
            {"served_model_name": "champion", "traffic_percentage": 50},
            {"served_model_name": "challenger", "traffic_percentage": 50},
        ]
    },
)
print("50/50 split is live.")

# COMMAND ----------

# MAGIC %md ### Observe routing

# COMMAND ----------

from collections import Counter

# The /invocations response echoes the *underlying* model id, not the served-model route name
# (champion/challenger). That's enough to see the split HERE only because champion and
# challenger wrap different base models. If both wrapped the same base model, read the split
# from the endpoint's served-entity metrics or the inference table instead.
served = Counter()
for i in range(20):
    body = invoke(f"Reply with the single word: pong ({i}).", max_tokens=5)["body"]
    served[body.get("model", "unknown")] += 1

show_json(dict(served))
print(f"Champion base model:   {CHAMPION_TARGET}")
print(f"Challenger base model: {CHALLENGER_TARGET}")
print("Counts key on the underlying model id; roughly 50/50 over 20 calls (variance expected).")

# COMMAND ----------

# MAGIC %md ### Canary, then promote

# COMMAND ----------

def set_split(champion_pct: int, challenger_pct: int):
    # The config API replaces the whole config, so re-send the entities each time.
    update_config(
        served_entities=ENTITIES,
        traffic_config={
            "routes": [
                {"served_model_name": "champion", "traffic_percentage": champion_pct},
                {"served_model_name": "challenger", "traffic_percentage": challenger_pct},
            ]
        },
    )
    print(f"Split updated: champion={champion_pct}% challenger={challenger_pct}%")


set_split(90, 10)  # canary
# When ready: set_split(0, 100) to promote the challenger, or set_split(100, 0) to roll back.
