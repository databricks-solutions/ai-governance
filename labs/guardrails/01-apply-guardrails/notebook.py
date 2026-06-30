# Databricks notebook source
# MAGIC %md
# MAGIC # Guardrail Lab · Part 1 — Apply guardrails
# MAGIC Apply Unity AI Gateway guardrails (PII, safety, topic, keyword) and watch the endpoint enforce them. See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### 1. Apply guardrails (input + output)

# COMMAND ----------

put_ai_gateway(
    {
        "guardrails": {
            "input": {
                "pii": {"behavior": "MASK"},
                "safety": True,
                "valid_topics": ["technology", "databricks", "data", "ai"],
                "invalid_keywords": ["competitor-secret-project"],
            },
            "output": {
                "pii": {"behavior": "MASK"},
                "safety": True,
            },
        }
    }
)
show_json(get_ai_gateway().get("guardrails"))

# COMMAND ----------

# MAGIC %md ### 2. PII masking — the model never sees the raw email / phone

# COMMAND ----------

r = invoke(
    "Summarize this contact for our CRM: Jane Doe, jane.doe@example.com, +1-415-555-0142.",
    max_tokens=80,
)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md ### 3. Topic moderation — off-topic prompt is refused

# COMMAND ----------

r = invoke("Give me detailed medical advice about prescription dosages.", max_tokens=80)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md ### 4. Invalid keyword filtering — banned term is blocked

# COMMAND ----------

r = invoke("Tell me everything about competitor-secret-project.", max_tokens=80)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md ### Cleanup — reset guardrails so other labs start clean

# COMMAND ----------

put_ai_gateway({"guardrails": None})
print("Guardrails reset. Current guardrails:", get_ai_gateway().get("guardrails"))
