# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 01 — Rate limiting
# MAGIC
# MAGIC Cap traffic to a serving endpoint with the Unity AI Gateway.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Current Gateway configuration

# COMMAND ----------

show_json(get_ai_gateway())

# COMMAND ----------

# MAGIC %md ### Apply rate limits

# COMMAND ----------

put_ai_gateway(
    {
        "rate_limits": [
            {"calls": 2, "renewal_period": "minute", "key": "endpoint"},
            {"calls": 1, "renewal_period": "minute", "key": "user"},
        ]
    }
)
show_json(get_ai_gateway().get("rate_limits"))

# COMMAND ----------

# MAGIC %md ### Trip the limit

# COMMAND ----------

import time

deadline = time.time() + 120  # allow up to 2 minutes for the limit to propagate
saw_429 = False
attempt = 0
while time.time() < deadline and not saw_429:
    attempt += 1
    codes = [invoke("In one word, say hello.", max_tokens=5)["status_code"] for _ in range(4)]
    print(f"burst {attempt}: {codes}")
    saw_429 = 429 in codes
    if not saw_429:
        time.sleep(10)

assert saw_429, "Expected a 429 once the per-user limit is exceeded (enforcement did not engage within 2 minutes)."
print("Rate limiting confirmed: requests past the limit were rejected with 429.")

# COMMAND ----------

# MAGIC %md ### Relax the limit

# COMMAND ----------

put_ai_gateway(
    {
        "rate_limits": [
            {"calls": 1000, "renewal_period": "minute", "key": "endpoint"},
            {"calls": 200, "renewal_period": "minute", "key": "user"},
        ]
    }
)
show_json(get_ai_gateway().get("rate_limits"))
