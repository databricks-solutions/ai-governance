# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 04 — Fallbacks
# MAGIC
# MAGIC **Unity AI Gateway for Models**
# MAGIC
# MAGIC Fallbacks make an endpoint resilient: when the primary served entity returns an error
# MAGIC (rate limit, timeout, provider outage), the Gateway automatically retries the request
# MAGIC against the next served entity on the endpoint — transparently to the caller.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Add a second served entity to act as the fallback.
# MAGIC 2. Enable Gateway fallbacks.
# MAGIC 3. Send traffic and confirm requests still succeed.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Add a fallback served entity
# MAGIC The endpoint ships with a single served entity (`primary`). We read its current config,
# MAGIC keep the existing primary, and append a second model as the fallback. The Gateway treats
# MAGIC served entities in order, so the primary stays first and the fallback second.

# COMMAND ----------

from databricks.sdk.service.serving import ServedEntityInput, TrafficConfig, Route

FALLBACK_MODEL = "databricks-meta-llama-3-1-8b-instruct"

# Discover the existing primary entity rather than assuming its model name.
current = w.serving_endpoints.get(ENDPOINT_NAME)
primary = current.config.served_entities[0]
primary_model = primary.entity_name
print(f"Existing primary served entity: {primary.name} -> {primary_model}")

w.serving_endpoints.update_config(
    name=ENDPOINT_NAME,
    served_entities=[
        ServedEntityInput(
            name="primary",
            entity_name=primary_model,
            entity_version="1",
            scale_to_zero_enabled=True,
        ),
        ServedEntityInput(
            name="fallback",
            entity_name=FALLBACK_MODEL,
            entity_version="1",
            scale_to_zero_enabled=True,
        ),
    ],
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="primary", traffic_percentage=100),
            Route(served_model_name="fallback", traffic_percentage=0),
        ]
    ),
)
print("Endpoint now has a primary + fallback served entity. Waiting for it to be ready...")
w.serving_endpoints.wait_get_serving_endpoint_not_updating(name=ENDPOINT_NAME)
print("Ready.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Enable Gateway fallbacks
# MAGIC With `fallback_config.enabled = true`, a failed request to `primary` is automatically
# MAGIC retried against `fallback` before an error is returned to the client.

# COMMAND ----------

put_ai_gateway({"fallback_config": {"enabled": True}})
show_json(get_ai_gateway().get("fallback_config"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Confirm traffic succeeds
# MAGIC Send a few requests. With fallbacks enabled, transient failures on the primary are
# MAGIC absorbed and the caller still gets `200`s.

# COMMAND ----------

codes = [invoke(f"Say OK ({i}).", max_tokens=5)["status_code"] for i in range(5)]
print("Status codes:", codes)
print("All succeeded." if all(c == 200 for c in codes) else "Some non-200s — inspect above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Fallbacks are configured once at the Gateway and apply to every caller.
# MAGIC - Order served entities primary → fallback; keep fallback traffic at 0% so it only
# MAGIC   serves on failure (use **Lab 05** for intentional traffic splitting instead).
# MAGIC - Combine with external-model served entities to fail over across providers.
# MAGIC
# MAGIC **Teardown:** `put_ai_gateway({"fallback_config": {"enabled": False}})`.
