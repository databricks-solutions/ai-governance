# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 03 — Fallbacks
# MAGIC
# MAGIC Automatically retry failed requests against a fallback served entity.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Add a fallback served entity

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

# MAGIC %md ### Enable Gateway fallbacks

# COMMAND ----------

put_ai_gateway({"fallback_config": {"enabled": True}})
show_json(get_ai_gateway().get("fallback_config"))

# COMMAND ----------

# MAGIC %md ### Confirm traffic succeeds

# COMMAND ----------

codes = [invoke(f"Say OK ({i}).", max_tokens=5)["status_code"] for i in range(5)]
print("Status codes:", codes)
print("All succeeded." if all(c == 200 for c in codes) else "Some non-200s — inspect above.")
