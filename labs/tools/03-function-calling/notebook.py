# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Function calling with Unity Catalog functions
# MAGIC
# MAGIC **Unity AI Gateway for Tools**
# MAGIC
# MAGIC Tools let a model take actions, not just generate text. On Databricks the cleanest
# MAGIC governed tool is a **Unity Catalog function**: it lives in UC, is permissioned and
# MAGIC audited like any other UC object, and can be handed to a model as an OpenAI-style tool.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Create a Unity Catalog function (the tool).
# MAGIC 2. Describe it to the governed endpoint as a `tools` definition.
# MAGIC 3. Let the model decide to call it, then **execute the UC function** and feed the
# MAGIC    result back for a final answer.
# MAGIC
# MAGIC Every model call still flows through the Gateway, so rate limits, guardrails, usage
# MAGIC tracking, and payload logging all apply to the tool-calling traffic too.

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create the tool (a Unity Catalog function)
# MAGIC A small, deterministic SQL function so the lab is self-contained. In practice this is
# MAGIC where you'd wrap a real lookup, calculation, or API behind a governed UC function.

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

# MAGIC %md
# MAGIC ## 2. Describe the tool to the model
# MAGIC The Gateway endpoint speaks the OpenAI chat schema, so tools are declared in the
# MAGIC standard `tools` format. We map the UC function to a tool definition. (In production,
# MAGIC `databricks-openai`'s `UCFunctionToolkit` generates these definitions and executes the
# MAGIC calls for you — see the takeaways.)

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

# MAGIC %md
# MAGIC ## 3. Tool-calling round trip
# MAGIC Send the user question with the tool definition. The model returns `tool_calls`; we
# MAGIC execute the UC function and send the result back so the model can answer in natural
# MAGIC language.

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - **Unity Catalog functions are governed tools**: permissions, lineage, and audit apply
# MAGIC   exactly as they do for tables — no separate tool registry to secure.
# MAGIC - The model never executes anything; it only *requests* a call. Your code executes the
# MAGIC   UC function, so you control authorization and inputs.
# MAGIC - All tool-calling traffic flows through the governed endpoint, inheriting rate limits,
# MAGIC   guardrails, and logging from the Models labs.
# MAGIC - **Production shortcut:** `databricks-openai`'s `UCFunctionToolkit` auto-generates the
# MAGIC   tool definitions from UC function metadata and executes the calls — see
# MAGIC   `agents/01-agent-framework` for the agent-grade pattern, and
# MAGIC   `tools/01-managed-mcp` to expose the same functions over MCP.
# MAGIC
# MAGIC **Teardown:** `spark.sql(f"DROP FUNCTION IF EXISTS {CATALOG}.{SCHEMA}.lookup_order_status")`
