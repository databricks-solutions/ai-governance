# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Agent evaluation & monitoring
# MAGIC
# MAGIC Score responses from the governed endpoint with Mosaic AI Agent Evaluation (MLflow).
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.1" openai
# MAGIC %restart_python

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

# MAGIC %md ### Evaluation dataset

# COMMAND ----------

eval_data = [
    {
        "inputs": {"question": "What is Unity Catalog in one sentence?"},
        "expectations": {
            "expected_facts": ["governance", "data and AI assets", "Databricks"]
        },
    },
    {
        "inputs": {"question": "Name two controls an AI gateway provides."},
        "expectations": {"expected_facts": ["rate limiting", "guardrails"]},
    },
    {
        "inputs": {"question": "What does a fallback do for a serving endpoint?"},
        "expectations": {
            "expected_facts": ["retries another model", "on failure", "resilience"]
        },
    },
]

# COMMAND ----------

# MAGIC %md ### The thing being evaluated

# COMMAND ----------

from openai import OpenAI

oai = OpenAI(base_url=f"{HOST}/serving-endpoints", api_key=TOKEN)


def predict_fn(question: str) -> str:
    resp = oai.chat.completions.create(
        model=ENDPOINT_NAME,
        messages=[
            {"role": "system", "content": "Answer concisely and professionally."},
            {"role": "user", "content": question},
        ],
        max_tokens=200,
    )
    return resp.choices[0].message.content


print(predict_fn("What is Unity Catalog in one sentence?"))

# COMMAND ----------

# MAGIC %md ### Evaluate with a judge panel

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import Correctness, RelevanceToQuery, Safety, Guidelines

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=predict_fn,
    scorers=[
        Correctness(),
        RelevanceToQuery(),
        Safety(),
        Guidelines(
            name="conciseness",
            guidelines="The response must be concise (no more than 3 sentences) and professional.",
        ),
    ],
)

# COMMAND ----------

# MAGIC %md ### Review results

# COMMAND ----------

print("Aggregate metrics:")
show_json(results.metrics)

# COMMAND ----------

display(results.tables["eval_results"])
