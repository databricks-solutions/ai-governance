# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — OpenAI Agents SDK on a governed endpoint
# MAGIC
# MAGIC **Unity AI Gateway for Agents**
# MAGIC
# MAGIC The governed endpoint is **OpenAI-compatible**, so an agent built with the OpenAI
# MAGIC Agents SDK runs against it by pointing the client's `base_url` at Databricks. Your
# MAGIC existing agent code is unchanged, but every model call now inherits the Gateway's rate
# MAGIC limits, guardrails, usage tracking, and payload logging.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Point an `AsyncOpenAI` client at the governed endpoint.
# MAGIC 2. Define an agent with a tool.
# MAGIC 3. Run it and watch it call the tool and answer — all through the Gateway.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade openai openai-agents
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Point the Agents SDK at the governed endpoint
# MAGIC `base_url` is the workspace serving root; the "model" is our endpoint name. `HOST` and
# MAGIC `TOKEN` come from `shared/setup`. We disable the SDK's built-in tracing (it would call
# MAGIC api.openai.com); use MLflow tracing instead (`mlflow.openai.autolog()`).

# COMMAND ----------

from openai import AsyncOpenAI
from agents import (
    Agent,
    Runner,
    OpenAIChatCompletionsModel,
    function_tool,
    set_tracing_disabled,
)

set_tracing_disabled(True)

client = AsyncOpenAI(base_url=f"{HOST}/serving-endpoints", api_key=TOKEN)
model = OpenAIChatCompletionsModel(model=ENDPOINT_NAME, openai_client=client)
print(f"Agent model routed through governed endpoint: {ENDPOINT_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Define an agent with a tool
# MAGIC A plain Python tool here for portability. To use a **governed** Unity Catalog function
# MAGIC instead, see `tools/03-function-calling`, or expose it over MCP via `tools/01-managed-mcp`.

# COMMAND ----------

@function_tool
def lookup_order_status(order_id: str) -> str:
    """Look up the fulfillment status of an order by its ID."""
    return {"A1001": "shipped", "A1002": "processing on line 3"}.get(order_id, "unknown order")


agent = Agent(
    name="Support",
    instructions="You are a concise customer-support agent. Use tools when asked about orders.",
    model=model,
    tools=[lookup_order_status],
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Run the agent
# MAGIC The Runner orchestrates the tool call and final response. Every model turn is a request
# MAGIC to the governed endpoint.

# COMMAND ----------

import asyncio

result = asyncio.run(Runner.run(agent, "What's the status of order A1002?"))
print("FINAL:", result.final_output)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - **One line of config** (`base_url` → Databricks) brings an existing OpenAI Agents stack
# MAGIC   under Gateway governance — no rewrite.
# MAGIC - Because traffic flows through the endpoint, the agent is automatically rate-limited,
# MAGIC   guardrailed, and logged (confirm in `models/03-usage-tracking-finops`).
# MAGIC - Swap the plain tool for a Unity Catalog function (`tools/03`) or a managed MCP tool
# MAGIC   (`tools/01`) to govern the tools as well as the model.
# MAGIC - For a Databricks-native agent you log, register, and deploy, see
# MAGIC   `agents/01-agent-framework`.
