# Databricks notebook source
# MAGIC %md
# MAGIC # Coding Agents — reference queries
# MAGIC
# MAGIC Standalone version of the checks the **Coding Agents** accelerator runs inside the AI
# MAGIC Governance Workshop app, so you can reference and run them without deploying the app.
# MAGIC Each section mirrors one in-app step and its `test`. SQL runs through `spark.sql`;
# MAGIC path/burst probes use the Databricks SDK REST client. See `README.md`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("governed_endpoint", "ai-governance-workshop-governed", "Governed serving endpoint")
dbutils.widgets.text("blocked_keyword", "social security number", "A keyword the guardrail should block")
dbutils.widgets.text("burst_size", "15", "Requests to send in the rate-limit burst")

ENDPOINT = dbutils.widgets.get("governed_endpoint")
BLOCKED = dbutils.widgets.get("blocked_keyword")
BURST = int(dbutils.widgets.get("burst_size"))
w = WorkspaceClient()

GATEWAY_CHAT_PATH = "/ai-gateway/mlflow/v1/chat/completions"
ANTHROPIC_MESSAGES_PATH = "/ai-gateway/anthropic/v1/messages"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Is it actually routed? (`coding_agent_route_check`)
# MAGIC The common silent failure: a client "pointed at the gateway" still resolves a legacy
# MAGIC endpoint, so limits/guardrails on the new **model service** never apply. A call that
# MAGIC names a model-service FQN records `service_name`; a plain-endpoint call records NULL.
# MAGIC Split recent coding-agent traffic on that column to see drift.

# COMMAND ----------

display(spark.sql("""
    SELECT service_name, endpoint_name, api_type,
           regexp_extract(user_agent, '^([A-Za-z0-9_.-]+)', 1) AS agent,
           COUNT(*) AS requests, SUM(total_tokens) AS tokens
    FROM system.ai_gateway.usage
    WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
      AND (user_agent ILIKE '%claude%' OR user_agent ILIKE '%cursor%'
           OR user_agent ILIKE '%ucode%' OR user_agent ILIKE '%codex%'
           OR user_agent ILIKE '%copilot%' OR user_agent ILIKE '%gemini%')
    GROUP BY 1, 2, 3, 4 ORDER BY requests DESC LIMIT 30
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Per-developer attribution (`coding_agent_usage`)
# MAGIC Coding agents identify themselves in `user_agent`, so traffic attributes per developer
# MAGIC with no tagging required — spend and usage roll up to a real person.

# COMMAND ----------

display(spark.sql("""
    SELECT requester,
           regexp_extract(user_agent, '^([A-Za-z0-9_.-]+)', 1) AS agent,
           api_type,
           COUNT(*)          AS requests,
           SUM(total_tokens) AS tokens
    FROM system.ai_gateway.usage
    WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
      AND (user_agent ILIKE '%claude%' OR user_agent ILIKE '%cursor%'
           OR user_agent ILIKE '%ucode%' OR user_agent ILIKE '%codex%'
           OR user_agent ILIKE '%copilot%' OR user_agent ILIKE '%gemini%')
    GROUP BY 1, 2, 3 ORDER BY tokens DESC LIMIT 25
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — Do the controls fire on the path the agent uses? (`path_coverage_check`)
# MAGIC Guardrails/limits are reliably enforced on the OpenAI-compatible chat path. Coding
# MAGIC agents often call the **provider-native** path (`/ai-gateway/anthropic/v1/messages`).
# MAGIC Probe the same guardrail-triggering prompt on both and compare — a control that
# MAGIC silently does not fire on the path a client actually uses is the dangerous gap.

# COMMAND ----------

prompt = f"My {BLOCKED} is 123-45-6789, please store it."

def _blocked(fn):
    try:
        fn()
        return False  # answered
    except Exception as e:
        return "400" in str(e) or "403" in str(e) or "guardrail" in str(e).lower()

chat_blocked = _blocked(lambda: w.api_client.do(
    "POST", GATEWAY_CHAT_PATH,
    body={"model": ENDPOINT, "messages": [{"role": "user", "content": prompt}], "max_tokens": 64},
))
anthropic_blocked = _blocked(lambda: w.api_client.do(
    "POST", ANTHROPIC_MESSAGES_PATH,
    headers={"anthropic-version": "2023-06-01"},
    body={"model": ENDPOINT, "max_tokens": 64, "messages": [{"role": "user", "content": prompt}]},
))
print("OpenAI-compatible chat path blocked :", chat_blocked)
print("Provider-native (anthropic) blocked :", anthropic_blocked)
if chat_blocked and not anthropic_blocked:
    print(">>> Coverage GAP: guardrail fires on chat path but NOT on the provider-native path.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Prove the rate limit bites — HTTP 429 (`rate_limit_429_demo`)
# MAGIC A rate limit is the hard cost control — an exceeded limit returns 429 immediately. Read
# MAGIC the configured limits, then send a burst and watch it throttle. Rate-limit changes can
# MAGIC take ~1–2 hours to take effect, and the limit must apply to the caller's identity (or
# MAGIC be endpoint-wide) to trip.

# COMMAND ----------

ep = w.serving_endpoints.get(ENDPOINT)
print("Configured rate limits:", ep.ai_gateway.rate_limits if ep.ai_gateway else None)

statuses = []
for i in range(BURST):
    try:
        w.api_client.do(
            "POST", GATEWAY_CHAT_PATH,
            body={"model": ENDPOINT, "messages": [{"role": "user", "content": f"ping {i}"}], "max_tokens": 8},
        )
        statuses.append(200)
    except Exception as e:
        statuses.append(429 if "429" in str(e) else "err")
print("Burst results:", statuses)
print("Saw a 429:", 429 in statuses)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Cap the spend with a budget (`budget_status`)
# MAGIC Attribution shows who is spending; a budget bounds it. Read the 30-day spend the gateway
# MAGIC records per model and user. (Set the budget + alert thresholds in the account console;
# MAGIC alerts are GA, hard caps are rolling out — confirm on the account.)

# COMMAND ----------

display(spark.sql("""
    SELECT usage_metadata.model     AS model,
           identity_metadata.run_by AS run_by,
           ROUND(SUM(usage_quantity), 2) AS usd
    FROM system.ai_gateway.external_model_spend
    WHERE usage_date > current_date() - 30
    GROUP BY 1, 2 ORDER BY usd DESC LIMIT 20
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — Code-secret detection (`audit_scan`)
# MAGIC Coding agents can leak API keys/tokens in prompts. Pull recent denied/failed calls from
# MAGIC the audit log and scan their arguments for secret-shaped strings.

# COMMAND ----------

SECRET = re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b")

audit = spark.sql("""
    SELECT event_time, action_name, service_name,
           user_identity.email  AS actor,
           response.status_code AS status_code,
           request_params
    FROM system.access.audit
    WHERE event_date >= current_date() - INTERVAL 1 DAY
      AND (response.status_code >= 400 OR lower(action_name) LIKE '%deny%')
    ORDER BY event_time DESC LIMIT 20
""")
display(audit)

suspected = [r for r in audit.collect() if r["request_params"] and SECRET.search(str(r["request_params"]))]
print(f"{len(suspected)} row(s) with suspected secret-shaped strings in arguments.")
