# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 04 — Traffic routing
# MAGIC
# MAGIC Split traffic across served entities for load balancing and A/B/canary rollouts.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Two served entities, 50/50 split

# COMMAND ----------

# Both entities wrap Databricks Foundation Models as external models (see Lab 03).
# `external_entity` / `primary_target` / `update_config` come from `shared/setup`.
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

served = Counter()
for i in range(20):
    body = invoke(f"Reply with the single word: pong ({i}).", max_tokens=5)["body"]
    served[body.get("model", "unknown")] += 1

show_json(dict(served))
print("Routing roughly matches the 50/50 traffic config (variance is expected over 20 calls).")

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
