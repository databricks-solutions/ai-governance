# Lab 03 — Function calling

**Give a model a Unity Catalog function as a governed tool, then run a full tool-calling round trip through the gateway.**

## What you'll do
1. Create a Unity Catalog function (the tool).
2. Declare it to the governed endpoint in the OpenAI `tools` format.
3. Let the model request the call, **execute the UC function**, and feed the result back for a final answer.

## How it works
Tools let a model take actions, not just generate text. On Databricks the cleanest governed tool is a **Unity Catalog function**: it lives in UC, is permissioned and audited like any other UC object, and can be handed to a model as an OpenAI-style tool definition. The model never executes anything — it only *requests* a call; your code executes the UC function, so you control authorization and inputs. Every model call still flows through the Gateway, so rate limits, guardrails, usage tracking, and payload logging all apply to tool-calling traffic too. In production, `databricks-openai`'s `UCFunctionToolkit` auto-generates the tool definitions from UC metadata and executes the calls for you; the same function can also be exposed over MCP (`tools/01-managed-mcp`).

To tear down: `spark.sql(f"DROP FUNCTION IF EXISTS {CATALOG}.{SCHEMA}.lookup_order_status")`.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_tools_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
