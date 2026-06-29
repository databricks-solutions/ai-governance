# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 01 — Rate limiting
# MAGIC
# MAGIC **Unity AI Gateway for Models**
# MAGIC
# MAGIC Rate limits cap how much traffic a serving endpoint will accept, protecting shared
# MAGIC capacity and capping spend. The Gateway can limit by **requests** or **tokens**, and
# MAGIC scope each limit to the whole **endpoint** or to an individual **user**.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Inspect the endpoint's current Gateway config.
# MAGIC 2. Apply an endpoint-wide and a per-user token/request limit.
# MAGIC 3. Drive traffic past the limit and observe `429 Too Many Requests`.
# MAGIC 4. Relax the limit and confirm recovery.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Current Gateway configuration
# MAGIC The endpoint was deployed with usage tracking and payload logging on. There are no
# MAGIC rate limits yet.

# COMMAND ----------

show_json(get_ai_gateway())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Apply rate limits
# MAGIC We set a small limit so it is easy to trip during the lab:
# MAGIC
# MAGIC - **Endpoint**: 2 requests / minute across all callers.
# MAGIC - **Per user**: 1 request / minute.
# MAGIC
# MAGIC `key` selects the scope (`endpoint` or `user`); `renewal_period` is always `minute`.
# MAGIC We use very low limits so a couple of requests trip them quickly.

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

# MAGIC %md
# MAGIC ## 3. Trip the limit
# MAGIC Rate-limit enforcement is eventually consistent: it can take a short time to take
# MAGIC effect after a config change. We poll — firing a small burst every few seconds — until
# MAGIC the Gateway starts rejecting excess calls with HTTP `429` (before they reach the model).

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

# MAGIC %md
# MAGIC ## 4. Relax the limit
# MAGIC Raise the limits to production-appropriate values (tune these to your POC's expected
# MAGIC concurrency and budget).

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Rate limits are enforced at the Gateway, *before* model compute is consumed.
# MAGIC - Per-user limits stop a single caller from starving everyone else on a shared endpoint.
# MAGIC - Combine with **usage tracking** (Lab 02) to set limits from real consumption data.
# MAGIC
# MAGIC **Teardown:** to remove limits entirely, `put_ai_gateway({"rate_limits": []})`.
