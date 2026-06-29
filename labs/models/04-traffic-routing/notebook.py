# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 04 — Traffic routing
# MAGIC
# MAGIC **Unity AI Gateway for Models**
# MAGIC
# MAGIC One endpoint can front multiple served entities and split traffic across them by
# MAGIC percentage. This enables **load balancing** across backends and **A/B testing** a new
# MAGIC model against the incumbent — all behind a single, governed URL, so callers never change.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Put two served entities behind the endpoint.
# MAGIC 2. Split traffic 50/50 (A/B).
# MAGIC 3. Send traffic and observe which entity served each request.
# MAGIC 4. Shift to a canary split (90/10) and then promote the winner.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Two served entities, 50/50 split
# MAGIC We keep the existing primary and add a "challenger" model, then route half the traffic
# MAGIC to each.

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

# MAGIC %md
# MAGIC ## 2. Observe routing
# MAGIC The response reports which served entity handled each request (the `model` /
# MAGIC `served-model-name`). Over many calls the distribution approaches the configured split.

# COMMAND ----------

from collections import Counter

served = Counter()
for i in range(20):
    body = invoke(f"Reply with the single word: pong ({i}).", max_tokens=5)["body"]
    served[body.get("model", "unknown")] += 1

show_json(dict(served))
print("Routing roughly matches the 50/50 traffic config (variance is expected over 20 calls).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Canary, then promote
# MAGIC Shift to a 90/10 canary, validate the challenger on real traffic, then promote it to
# MAGIC 100% once you're satisfied (or roll back to the champion).

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Traffic config splits load across served entities for **load balancing** and **A/B/canary** rollouts.
# MAGIC - Callers hit one stable, governed endpoint URL regardless of the split.
# MAGIC - Pair with **usage tracking** (Lab 02) to compare cost/latency per served entity, and
# MAGIC   **fallbacks** (Lab 03) for resilience on top of the split.

# COMMAND ----------

# MAGIC %md
# MAGIC **Teardown:** restore a single served entity:
# MAGIC ```python
# MAGIC set_split(100, 0)
# MAGIC ```
