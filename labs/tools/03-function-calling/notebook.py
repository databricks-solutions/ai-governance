# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Function calling with Unity Catalog functions
# MAGIC
# MAGIC Hand a governed UC function to a model and run a full tool-calling round trip.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Create the tool (a Unity Catalog function)

# COMMAND ----------

spark.sql(
    f"""
    CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.lookup_order_status(order_id STRING)
    RETURNS STRING
    COMMENT 'Look up the fulfillment status of an order by its ID.'
    RETURN
      CASE
        WHEN order_id = 'A1001' THEN 'shipped'
        WHEN order_id = 'A1002' THEN 'processing on line 3'
        ELSE 'unknown order'
      END
    """
)
print(f"Created tool: {CATALOG}.{SCHEMA}.lookup_order_status")

# COMMAND ----------

# MAGIC %md ### Describe the tool to the model

# COMMAND ----------

FUNCTION_NAME = "lookup_order_status"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": FUNCTION_NAME,
            "description": "Look up the fulfillment status of an order by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. A1001"}
                },
                "required": ["order_id"],
            },
        },
    }
]


def run_uc_tool(name: str, args: dict):
    """Execute a Unity Catalog function by name with the model-supplied arguments."""
    if name == FUNCTION_NAME:
        row = spark.sql(
            f"SELECT {CATALOG}.{SCHEMA}.lookup_order_status(:order_id) AS result",
            args={"order_id": args.get("order_id", "")},
        ).collect()
        return row[0]["result"]
    return f"unknown tool: {name}"

# COMMAND ----------

# MAGIC %md ### Tool-calling round trip

# COMMAND ----------

import json

messages = [{"role": "user", "content": "Can you check the status of order A1002 for me?"}]

# Turn 1: the model decides whether to call a tool.
resp = invoke(messages, tools=TOOLS, tool_choice="auto", max_tokens=256)
assert resp["status_code"] == 200, resp
choice = resp["body"]["choices"][0]
print("finish_reason:", choice.get("finish_reason"))
tool_calls = choice["message"].get("tool_calls") or []
show_json(tool_calls)

# COMMAND ----------

# Execute each requested tool call against Unity Catalog.
messages.append(choice["message"])  # the assistant turn carrying the tool_calls
for tc in tool_calls:
    args = json.loads(tc["function"]["arguments"])
    result = run_uc_tool(tc["function"]["name"], args)
    print(f"executed {tc['function']['name']}({args}) -> {result}")
    messages.append(
        {"role": "tool", "tool_call_id": tc["id"], "content": str(result)}
    )

# COMMAND ----------

# Turn 2: the model answers using the tool result.
final = invoke(messages, max_tokens=256)
print("HTTP", final["status_code"])
print(final["body"]["choices"][0]["message"]["content"])
