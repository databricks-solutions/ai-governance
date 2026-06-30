# Lab 03 — OpenAI Agents SDK on Databricks

**Run an agent built with the OpenAI Agents SDK against the OpenAI-compatible governed endpoint — your agent stack inherits Gateway governance with a one-line change.**

## What you'll do
1. Point an `AsyncOpenAI` client's `base_url` at the Databricks serving root.
2. Define an agent with a tool.
3. Run it and watch the tool call + answer flow through the governed endpoint.

## How it works
The governed endpoint is OpenAI-compatible, so an agent built with the OpenAI Agents SDK runs
against it just by pointing the client's `base_url` at Databricks — your existing agent code is
unchanged, but every model call now inherits the Gateway's rate limits, guardrails, usage
tracking, and payload logging. The lab disables the SDK's built-in tracing (it would call
api.openai.com) and uses MLflow tracing instead. Swap the plain Python tool for a governed
Unity Catalog function (`tools/03-function-calling`) or a managed MCP tool
(`tools/01-managed-mcp`) to govern the tools as well as the model.

## Run it
Open `notebook.py` and run top-to-bottom. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
