# Databricks notebook source
# MAGIC %md
# MAGIC # Lab 02 — AI guardrails
# MAGIC
# MAGIC **Unity AI Gateway for Models**
# MAGIC
# MAGIC Guardrails inspect prompts (input) and completions (output) and act on unsafe or
# MAGIC non-compliant content. The Gateway supports:
# MAGIC
# MAGIC - **PII detection** — `BLOCK` the request or `MASK` detected entities.
# MAGIC - **Safety filter** — block harmful / unsafe content.
# MAGIC - **Topic moderation** — restrict conversation to an allow-list of `valid_topics`.
# MAGIC - **Invalid keyword filtering** — block requests containing banned terms.
# MAGIC
# MAGIC In this lab you apply each guardrail and watch the Gateway enforce it.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Apply guardrails (input + output)
# MAGIC We mask PII on the way in, block unsafe content both directions, restrict topics, and
# MAGIC ban a sample keyword. Tune these to your POC's policy.

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

# MAGIC %md
# MAGIC ## 2. PII masking
# MAGIC The Gateway masks detected PII before the prompt reaches the model. Inspect the
# MAGIC response — the model never sees the raw email / phone number.

# COMMAND ----------

r = invoke(
    "Summarize this contact for our CRM: Jane Doe, jane.doe@example.com, +1-415-555-0142.",
    max_tokens=80,
)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Topic moderation
# MAGIC A prompt outside the allow-list is refused by the Gateway. Expect a non-200 status or
# MAGIC a guardrail-intervention message rather than a normal completion.

# COMMAND ----------

r = invoke("Give me detailed medical advice about prescription dosages.", max_tokens=80)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Invalid keyword filtering
# MAGIC A prompt containing a banned keyword is blocked before reaching the model.

# COMMAND ----------

r = invoke("Tell me everything about competitor-secret-project.", max_tokens=80)
print("HTTP", r["status_code"])
show_json(r["body"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Guardrails run at the Gateway, so every client of the endpoint is protected uniformly.
# MAGIC - `MASK` keeps requests flowing while redacting PII; `BLOCK` rejects them outright.
# MAGIC - Pair guardrails with **payload logging** (see Lab 03 / inference tables) to audit what
# MAGIC   was blocked and why.
# MAGIC
# MAGIC **Teardown:** `put_ai_gateway({"guardrails": None})` removes all guardrails.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC Reset guardrails so the endpoint returns to a clean state for other labs (topic
# MAGIC moderation in particular would otherwise block their generic test prompts). Comment
# MAGIC this out if you want the guardrails to persist.

# COMMAND ----------

put_ai_gateway({"guardrails": None})
print("Guardrails reset. Current guardrails:", get_ai_gateway().get("guardrails"))
