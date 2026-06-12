# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 05 — Traffic routing
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

from databricks.sdk.service.serving import ServedEntityInput, TrafficConfig, Route

CHALLENGER_MODEL = "databricks-meta-llama-3-1-8b-instruct"

current = w.serving_endpoints.get(ENDPOINT_NAME)
primary_model = current.config.served_entities[0].entity_name
print(f"Champion (primary): {primary_model}")
print(f"Challenger:         {CHALLENGER_MODEL}")

w.serving_endpoints.update_config(
    name=ENDPOINT_NAME,
    served_entities=[
        ServedEntityInput(name="champion", entity_name=primary_model, entity_version="1", scale_to_zero_enabled=True),
        ServedEntityInput(name="challenger", entity_name=CHALLENGER_MODEL, entity_version="1", scale_to_zero_enabled=True),
    ],
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="champion", traffic_percentage=50),
            Route(served_model_name="challenger", traffic_percentage=50),
        ]
    ),
)
w.serving_endpoints.wait_get_serving_endpoint_not_updating(name=ENDPOINT_NAME)
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
    w.serving_endpoints.update_config(
        name=ENDPOINT_NAME,
        traffic_config=TrafficConfig(
            routes=[
                Route(served_model_name="champion", traffic_percentage=champion_pct),
                Route(served_model_name="challenger", traffic_percentage=challenger_pct),
            ]
        ),
    )
    w.serving_endpoints.wait_get_serving_endpoint_not_updating(name=ENDPOINT_NAME)
    print(f"Split updated: champion={champion_pct}% challenger={challenger_pct}%")


set_split(90, 10)  # canary
# When ready: set_split(0, 100) to promote the challenger, or set_split(100, 0) to roll back.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Traffic config splits load across served entities for **load balancing** and **A/B/canary** rollouts.
# MAGIC - Callers hit one stable, governed endpoint URL regardless of the split.
# MAGIC - Pair with **usage tracking** (Lab 03) to compare cost/latency per served entity, and
# MAGIC   **fallbacks** (Lab 04) for resilience on top of the split.

# COMMAND ----------

# MAGIC %md
# MAGIC **Teardown:** restore a single served entity:
# MAGIC ```python
# MAGIC set_split(100, 0)
# MAGIC ```
