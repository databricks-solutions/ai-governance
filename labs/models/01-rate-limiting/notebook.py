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
# MAGIC - **Endpoint**: 5 requests / minute across all callers.
# MAGIC - **Per user**: 2 requests / minute.
# MAGIC
# MAGIC `key` selects the scope (`endpoint` or `user`); `renewal_period` is always `minute`.

# COMMAND ----------

put_ai_gateway(
    {
        "rate_limits": [
            {"calls": 5, "renewal_period": "minute", "key": "endpoint"},
            {"calls": 2, "renewal_period": "minute", "key": "user"},
        ]
    }
)
show_json(get_ai_gateway().get("rate_limits"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Trip the limit
# MAGIC Fire requests in a tight loop. Once the per-user limit (2/min) is exceeded the
# MAGIC Gateway rejects further calls with HTTP `429` before they reach the model.

# COMMAND ----------

results = []
for i in range(6):
    r = invoke(f"In one word, say hello (attempt {i}).", max_tokens=5)
    results.append(r["status_code"])
    print(f"attempt {i}: HTTP {r['status_code']}")

print("\nStatus codes:", results)
assert 429 in results, "Expected at least one 429 once the per-user limit is exceeded."
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
# MAGIC - Combine with **usage tracking** (Lab 03) to set limits from real consumption data.
# MAGIC
# MAGIC **Teardown:** to remove limits entirely, `put_ai_gateway({"rate_limits": []})`.
