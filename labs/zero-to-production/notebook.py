# Databricks notebook source
# MAGIC %md
# MAGIC # Zero to production — a governed endpoint end to end
# MAGIC
# MAGIC Take one endpoint from "returns text" to "production-ready," applying each Gateway control in adoption order.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../shared/setup

# COMMAND ----------

# MAGIC %md ### The governed endpoint

# COMMAND ----------

print("Endpoint:", ENDPOINT_NAME)
print("State:", w.serving_endpoints.get(ENDPOINT_NAME).state)

# COMMAND ----------

# MAGIC %md ### Observability first

# COMMAND ----------

put_ai_gateway(
    {
        "usage_tracking_config": {"enabled": True},
        "inference_table_config": {
            "enabled": True,
            "catalog_name": CATALOG,
            "schema_name": SCHEMA,
            "table_name_prefix": "gateway",
        },
    }
)
gw = get_ai_gateway()
show_json({k: gw.get(k) for k in ["usage_tracking_config", "inference_table_config"]})

# COMMAND ----------

# MAGIC %md ### Safety & privacy guardrails

# COMMAND ----------

put_ai_gateway(
    {
        "guardrails": {
            "input": {"safety": True, "pii": {"behavior": "MASK"}},
            "output": {"safety": True, "pii": {"behavior": "MASK"}},
        }
    }
)
show_json(get_ai_gateway().get("guardrails"))

# COMMAND ----------

# MAGIC %md ### Cost & capacity controls

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

# MAGIC %md ### Resilience: a fallback

# COMMAND ----------

FALLBACK_TARGET = "databricks-gpt-oss-120b"
update_config(
    served_entities=[
        external_entity("primary", primary_target()),
        external_entity("fallback", FALLBACK_TARGET),
    ],
    traffic_config={
        "routes": [
            {"served_model_name": "primary", "traffic_percentage": 100},
            {"served_model_name": "fallback", "traffic_percentage": 0},
        ]
    },
)
put_ai_gateway({"fallback_config": {"enabled": True}})
print("Fallback enabled:", get_ai_gateway().get("fallback_config"))

# COMMAND ----------

# MAGIC %md ### Governed tools

# COMMAND ----------

spark.sql(
    f"""
    CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.lookup_order_status(order_id STRING)
    RETURNS STRING
    COMMENT 'Look up the fulfillment status of an order by its ID.'
    RETURN CASE WHEN order_id='A1001' THEN 'shipped'
                WHEN order_id='A1002' THEN 'processing on line 3'
                ELSE 'unknown order' END
    """
)
print(f"Governed tool ready: {CATALOG}.{SCHEMA}.lookup_order_status "
      "(usable directly or over managed MCP)")

# COMMAND ----------

# MAGIC %md ### Validate

# COMMAND ----------

import time

# Give the latest config a moment to reconcile, then send a request.
time.sleep(5)
r = invoke("In one sentence, what does an AI gateway do?", max_tokens=80)
print("HTTP", r["status_code"])
print(r["body"]["choices"][0]["message"]["content"])
assert r["status_code"] == 200, "Smoke test failed — inspect the gateway config above."
print("\n✅ Governed endpoint is serving.")

# COMMAND ----------

# MAGIC %md ### Observe cost & usage

# COMMAND ----------

print("Usage:      system.serving.endpoint_usage  (join system.serving.served_entities)")
print("Cost:       system.billing.usage + system.billing.list_prices")
print(f"Payloads:   {CATALOG}.{SCHEMA}.gateway_payload")
print("Dashboard:  labs/models/02-usage-tracking-finops/dashboard.lvdash.json")

# COMMAND ----------

# MAGIC %md ### Production checklist
# MAGIC
# MAGIC The endpoint now has, in one place and applied to every caller:
# MAGIC
# MAGIC - ✅ **Observability** — usage tracking + payload logging on
# MAGIC - ✅ **Security** — safety filter + PII masking (input & output)
# MAGIC - ✅ **Cost/capacity** — endpoint and per-user rate limits
# MAGIC - ✅ **Reliability** — automatic fallback to a second model
# MAGIC - ✅ **Governed tools** — actions exposed as Unity Catalog functions
# MAGIC
# MAGIC Before go-live, also consider: access control (`CAN_QUERY` grants + UC tool grants),
# MAGIC budgets & alerting, evaluation & monitoring (`agents/02`), topic scoping
# MAGIC (`valid_topics` / `invalid_keywords`), networking, and change management (manage it all
# MAGIC as code in this bundle, `resources/`).
