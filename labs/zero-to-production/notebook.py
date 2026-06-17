# Databricks notebook source
# MAGIC %md
# MAGIC # Zero to production — a governed endpoint end to end
# MAGIC
# MAGIC This capstone walks a single endpoint from "it returns text" to "it's ready for
# MAGIC production," applying each Unity AI Gateway control in the order you'd actually adopt
# MAGIC them. It composes the individual Models/Tools labs into one narrative and leaves the
# MAGIC endpoint in a sensible, production-appropriate state.
# MAGIC
# MAGIC | Step | Control | Pillar | Deep-dive lab |
# MAGIC |------|---------|--------|---------------|
# MAGIC | 1 | Governed endpoint | — | (bundle deploy) |
# MAGIC | 2 | Usage tracking + payload logging | Operations | `models/03` |
# MAGIC | 3 | Safety + PII guardrails | Security | `models/02` |
# MAGIC | 4 | Rate limits | Cost / Reliability | `models/01` |
# MAGIC | 5 | Fallback | Reliability | `models/04` |
# MAGIC | 6 | Governed tools | Security | `tools/01`, `tools/03` |
# MAGIC | 7 | Validate | — | — |
# MAGIC | 8 | Observe cost & usage | Cost | `models/03` |
# MAGIC | 9 | Production checklist | — | — |

# COMMAND ----------

# MAGIC %run ../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. The governed endpoint
# MAGIC Deployed by the bundle. Everything below configures *this* endpoint, and every caller
# MAGIC (apps, agents, notebooks) goes through it.

# COMMAND ----------

print("Endpoint:", ENDPOINT_NAME)
print("State:", w.serving_endpoints.get(ENDPOINT_NAME).state)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Observability first
# MAGIC Turn on usage tracking and payload logging before traffic arrives, so you can always
# MAGIC answer "who called what, and what did it cost?". (The bundle enables these at create
# MAGIC time; we assert it here.)

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

# MAGIC %md
# MAGIC ## 3. Safety & privacy guardrails
# MAGIC A production baseline: block unsafe content and mask PII in and out. (We keep topic
# MAGIC moderation off here so the endpoint stays general-purpose; add `valid_topics` to scope
# MAGIC it — see `models/02`.)

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

# MAGIC %md
# MAGIC ## 4. Cost & capacity controls
# MAGIC Production-appropriate rate limits (tune to expected concurrency and budget). These
# MAGIC protect shared capacity and cap spend before the model is ever invoked.

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
# MAGIC ## 5. Resilience: a fallback
# MAGIC Add a second model and enable fallbacks so a failure on the primary is retried
# MAGIC automatically. Both are external-model entities (see `models/04`).

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

# MAGIC %md
# MAGIC ## 6. Governed tools
# MAGIC Publish actions as Unity Catalog functions so agents act through permissioned, audited
# MAGIC tools. Full round trips are in `tools/03-function-calling` and `tools/01-managed-mcp`.

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

# MAGIC %md
# MAGIC ## 7. Validate
# MAGIC A smoke test confirms the fully governed endpoint still serves normal traffic.

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

# MAGIC %md
# MAGIC ## 8. Observe cost & usage
# MAGIC Usage flows to system tables (with lag) and full payloads to the inference table.
# MAGIC `models/03-usage-tracking-finops` builds the rollups, budget alert, and AI/BI dashboard.

# COMMAND ----------

print("Usage:      system.serving.endpoint_usage  (join system.serving.served_entities)")
print("Cost:       system.billing.usage + system.billing.list_prices")
print(f"Payloads:   {CATALOG}.{SCHEMA}.gateway_payload")
print("Dashboard:  labs/models/03-usage-tracking-finops/dashboard.lvdash.json")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Production checklist
# MAGIC The endpoint now has, in one place and applied to every caller:
# MAGIC
# MAGIC - ✅ **Observability** — usage tracking + payload logging on
# MAGIC - ✅ **Security** — safety filter + PII masking (input & output)
# MAGIC - ✅ **Cost/capacity** — endpoint and per-user rate limits
# MAGIC - ✅ **Reliability** — automatic fallback to a second model
# MAGIC - ✅ **Governed tools** — actions exposed as Unity Catalog functions
# MAGIC
# MAGIC Before go-live, also consider:
# MAGIC - **Access control** — grant `CAN_QUERY` only to the principals/groups that need it; manage tool grants in Unity Catalog.
# MAGIC - **Budgets & alerting** — schedule the FinOps queries as a job and route alerts (email/Slack).
# MAGIC - **Evaluation & monitoring** — add Agent Evaluation / MLflow monitoring (`agents/02`).
# MAGIC - **Topic scoping** — add `valid_topics` / `invalid_keywords` if the use case is narrow.
# MAGIC - **Networking** — restrict access via your workspace's private connectivity controls.
# MAGIC - **Change management** — manage all of the above as code in this bundle (`resources/`).
