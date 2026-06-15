# Lab 03 — Function calling

**Category:** Unity AI Gateway for Tools · **Status:** ✅ Built

Give a model a **Unity Catalog function** as a governed tool, then run a full tool-calling round trip through the gateway.

## What you'll do
1. Create a Unity Catalog function (the tool).
2. Declare it to the governed endpoint in the OpenAI `tools` format.
3. Let the model request the call, **execute the UC function**, and feed the result back for a final answer.

## Databricks features
- Unity Catalog functions as governed, permissioned, audited tools.
- Foundation Model API tool/function calling through the governed endpoint.
- All Gateway controls (rate limits, guardrails, usage tracking, payload logging) apply to tool-calling traffic.

## Prerequisites
- The bundle deployed so the gateway endpoint and `${var.catalog}.${var.schema}` schema exist.
- Permission to create and execute UC functions in that schema.

## Run it
Open `notebook.py` and run top-to-bottom. Production note: `databricks-openai`'s
`UCFunctionToolkit` can generate the tool definitions and execute calls for you.
