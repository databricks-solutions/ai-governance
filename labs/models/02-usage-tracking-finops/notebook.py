# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 02 — Usage tracking & FinOps
# MAGIC
# MAGIC Turn Gateway telemetry into tokens, cost, and a budget alert.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Confirm telemetry is on

# COMMAND ----------

gw = get_ai_gateway()
show_json({k: gw.get(k) for k in ["usage_tracking_config", "inference_table_config"]})

# COMMAND ----------

# MAGIC %md ### Generate traffic

# COMMAND ----------

for i in range(5):
    invoke(f"Give me one fun fact about data governance (#{i}).", max_tokens=60)
print("Sent 5 requests through the gateway endpoint.")

# COMMAND ----------

# MAGIC %md ### Token usage from system tables

# COMMAND ----------

usage = spark.sql(
    f"""
    SELECT
      u.requester                                  AS user,
      date(u.request_time)                         AS day,
      count(*)                                     AS requests,
      sum(u.input_token_count)                     AS input_tokens,
      sum(u.output_token_count)                    AS output_tokens,
      sum(u.input_token_count + u.output_token_count) AS total_tokens
    FROM system.serving.endpoint_usage u
    JOIN system.serving.served_entities se
      ON u.served_entity_id = se.served_entity_id
    WHERE se.endpoint_name = '{ENDPOINT_NAME}'
      AND u.request_time >= current_date() - INTERVAL 7 DAYS
    GROUP BY u.requester, date(u.request_time)
    ORDER BY day DESC, total_tokens DESC
    """
)
display(usage)

# COMMAND ----------

# MAGIC %md ### Cost from billing system tables

# COMMAND ----------

cost = spark.sql(
    f"""
    WITH priced AS (
      SELECT
        u.usage_date,
        u.usage_metadata.endpoint_name AS endpoint_name,
        u.usage_quantity * p.pricing.default AS cost_usd
      FROM system.billing.usage u
      JOIN system.billing.list_prices p
        ON u.sku_name = p.sku_name
       AND u.usage_unit = p.usage_unit
       AND u.usage_end_time BETWEEN p.price_start_time AND coalesce(p.price_end_time, current_timestamp())
      WHERE u.billing_origin_product = 'MODEL_SERVING'
        AND u.usage_date >= current_date() - INTERVAL 30 DAYS
    )
    SELECT usage_date, endpoint_name, round(sum(cost_usd), 2) AS cost_usd
    FROM priced
    WHERE endpoint_name = '{ENDPOINT_NAME}'
    GROUP BY usage_date, endpoint_name
    ORDER BY usage_date DESC
    """
)
display(cost)

# COMMAND ----------

# MAGIC %md ### Budget alert

# COMMAND ----------

MONTHLY_BUDGET_USD = 100.0

mtd = (
    cost.where("usage_date >= date_trunc('MONTH', current_date())")
    .groupBy()
    .sum("cost_usd")
    .collect()
)
spend = (mtd[0][0] or 0.0) if mtd else 0.0
pct = 100 * spend / MONTHLY_BUDGET_USD if MONTHLY_BUDGET_USD else 0
print(f"Month-to-date spend on {ENDPOINT_NAME}: ${spend:,.2f} ({pct:.1f}% of ${MONTHLY_BUDGET_USD:,.0f} budget)")
if spend > MONTHLY_BUDGET_USD:
    print("⚠️  OVER BUDGET — tighten rate limits or review top consumers above.")
else:
    print("✅ Within budget.")

# COMMAND ----------

# MAGIC %md ### Inference (payload) table

# COMMAND ----------

payload_table = f"{CATALOG}.{SCHEMA}.gateway_payload"
try:
    display(spark.sql(f"SELECT * FROM {payload_table} ORDER BY timestamp_ms DESC LIMIT 20"))
except Exception as e:  # noqa: BLE001
    print(f"Payload table {payload_table} not queryable yet (rows can lag a few minutes): {e}")
