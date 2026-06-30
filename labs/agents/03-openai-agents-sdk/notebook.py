# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — OpenAI Agents SDK on a governed endpoint
# MAGIC
# MAGIC Run an OpenAI Agents SDK agent against the OpenAI-compatible governed endpoint.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade openai openai-agents
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Point the Agents SDK at the governed endpoint

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

# MAGIC %md ### Define an agent with a tool

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

# MAGIC %md ### Run the agent

# COMMAND ----------

import asyncio

result = asyncio.run(Runner.run(agent, "What's the status of order A1002?"))
print("FINAL:", result.final_output)
