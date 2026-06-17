# Lab 03 — OpenAI Agents SDK on Databricks

**Category:** Unity AI Gateway for Agents · **Status:** ✅ Built

Run an agent built with the OpenAI Agents SDK against the **OpenAI-compatible** governed endpoint — your agent stack inherits Gateway governance with a one-line change.

## What you'll do
1. Point an `AsyncOpenAI` client's `base_url` at the Databricks serving root.
2. Define an agent with a tool.
3. Run it and watch the tool call + answer flow through the governed endpoint.

## Databricks features
- OpenAI-compatible Model Serving endpoint (`base_url` + token point at Databricks).
- Gateway rate limits, guardrails, usage tracking, and payload logging applied transparently.

## Prerequisites
- The bundle deployed so the gateway endpoint exists.
- Installs `openai` and `openai-agents` in the notebook.

## Notes
- The lab disables the SDK's built-in tracing (it would call api.openai.com); use MLflow
  tracing instead — see `dev-tools/tracing`.
- Swap the plain tool for a governed UC function (`tools/03-function-calling`) or a managed
  MCP tool (`tools/01-managed-mcp`).
