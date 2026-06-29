# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 03 — Fallbacks
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
# MAGIC The endpoint fronts a Databricks Foundation Model via an external-model served entity.
# MAGIC We keep that `primary` and append a second model (also wrapped as an external model)
# MAGIC as the fallback. The Gateway treats served entities in order, so `primary` stays first
# MAGIC and `fallback` second. `external_entity` / `primary_target` / `update_config` come from
# MAGIC `shared/setup`.

# COMMAND ----------

FALLBACK_TARGET = "databricks-gpt-oss-120b"

# Preserve whatever the current primary wraps, then add the fallback.
primary = primary_target()
print(f"Primary wraps:  {primary}")
print(f"Fallback wraps: {FALLBACK_TARGET}")

update_config(
    served_entities=[
        external_entity("primary", primary),
        external_entity("fallback", FALLBACK_TARGET),
    ],
    traffic_config={
        "routes": [
            {"served_model_name": "primary", "traffic_percentage": 100},
            {"served_model_name": "fallback", "traffic_percentage": 0},
        ]
    },
)
print("Endpoint now has a primary + fallback served entity, and is ready.")

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
# MAGIC   serves on failure (use **Lab 04** for intentional traffic splitting instead).
# MAGIC - Combine with external-model served entities to fail over across providers.
# MAGIC
# MAGIC **Teardown:** `put_ai_gateway({"fallback_config": {"enabled": False}})`.
