# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Agent evaluation & monitoring
# MAGIC
# MAGIC **Unity AI Gateway for Agents**
# MAGIC
# MAGIC Governance isn't only access and cost — it's also *quality*. Mosaic AI Agent
# MAGIC Evaluation (via MLflow) scores responses from the governed endpoint with built-in
# MAGIC LLM judges for correctness, relevance, safety, and custom guidelines, and logs the
# MAGIC results to an MLflow experiment you can monitor over time.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Build a small evaluation dataset.
# MAGIC 2. Define a `predict_fn` that calls the governed endpoint.
# MAGIC 3. Run `mlflow.genai.evaluate` with a panel of judges.
# MAGIC 4. Review per-example scores.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.1" openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Evaluation dataset
# MAGIC Each row has `inputs` (passed to the agent) and optional `expectations` (ground truth
# MAGIC the judges check against). Keep it small here; in practice curate from real traffic in
# MAGIC the inference table (`models/03`).

# COMMAND ----------

eval_data = [
    {
        "inputs": {"question": "What is Unity Catalog in one sentence?"},
        "expectations": {
            "expected_facts": ["governance", "data and AI assets", "Databricks"]
        },
    },
    {
        "inputs": {"question": "Name two controls an AI gateway provides."},
        "expectations": {"expected_facts": ["rate limiting", "guardrails"]},
    },
    {
        "inputs": {"question": "What does a fallback do for a serving endpoint?"},
        "expectations": {
            "expected_facts": ["retries another model", "on failure", "resilience"]
        },
    },
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The thing being evaluated
# MAGIC `predict_fn` calls the **governed endpoint** (so eval traffic is itself rate-limited,
# MAGIC guardrailed, and logged). It takes the keys from `inputs` and returns the response.

# COMMAND ----------

from openai import OpenAI

oai = OpenAI(base_url=f"{HOST}/serving-endpoints", api_key=TOKEN)


def predict_fn(question: str) -> str:
    resp = oai.chat.completions.create(
        model=ENDPOINT_NAME,
        messages=[
            {"role": "system", "content": "Answer concisely and professionally."},
            {"role": "user", "content": question},
        ],
        max_tokens=200,
    )
    return resp.choices[0].message.content


print(predict_fn("What is Unity Catalog in one sentence?"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Evaluate with a judge panel
# MAGIC - **Correctness** — does the answer cover the expected facts?
# MAGIC - **RelevanceToQuery** — is it on-topic? (reference-free)
# MAGIC - **Safety** — is it free of harmful content? (reference-free)
# MAGIC - **Guidelines** — does it follow a custom style rule?

# COMMAND ----------

import mlflow
from mlflow.genai.scorers import Correctness, RelevanceToQuery, Safety, Guidelines

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=predict_fn,
    scorers=[
        Correctness(),
        RelevanceToQuery(),
        Safety(),
        Guidelines(
            name="conciseness",
            guidelines="The response must be concise (no more than 3 sentences) and professional.",
        ),
    ],
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Review results
# MAGIC Aggregate metrics plus a per-example table. Open the run in the **Experiments** UI for
# MAGIC the full traces and judge rationales.

# COMMAND ----------

print("Aggregate metrics:")
show_json(results.metrics)

# COMMAND ----------

display(results.tables["eval_results"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - Evaluation runs against the **governed endpoint**, so quality checks share the same
# MAGIC   guardrails, limits, and logging as production traffic.
# MAGIC - Built-in judges (Correctness, Safety, RelevanceToQuery) plus custom **Guidelines**
# MAGIC   cover quality, safety, and style; results are logged to MLflow for trend monitoring.
# MAGIC - Schedule this as a job over a dataset sampled from the inference table to monitor
# MAGIC   quality continuously, and feed regressions back into guardrail/limit tuning.
# MAGIC - To evaluate a deployed agent (not just the endpoint), point `predict_fn` at the
# MAGIC   agent from `agents/01-agent-framework`.
