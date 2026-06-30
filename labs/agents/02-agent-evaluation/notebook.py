# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Agent evaluation & monitoring
# MAGIC
# MAGIC Score responses from the governed endpoint with Mosaic AI Agent Evaluation (MLflow).
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.1" openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Evaluation dataset

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

# MAGIC %md ### The thing being evaluated

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

# MAGIC %md ### Evaluate with a judge panel

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

# MAGIC %md ### Review results

# COMMAND ----------

print("Aggregate metrics:")
show_json(results.metrics)

# COMMAND ----------

display(results.tables["eval_results"])
