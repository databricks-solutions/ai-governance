# Lab 03 — OpenAI Agents SDK on Databricks

**Category:** Unity AI Gateway for Agents · **Status:** 🟡 Planned

## Objective
Run an agent built with the OpenAI Agents SDK against the Databricks **OpenAI-compatible**
endpoint, so an existing agent stack inherits Gateway governance with minimal code change.

## Databricks features
- OpenAI-compatible Model Serving endpoint (base URL + token point at Databricks).
- Gateway rate limits, guardrails, and usage tracking applied transparently.

## Outline
1. Point the OpenAI client `base_url`/`api_key` at the governed Databricks endpoint.
2. Define agent tools (optionally backed by UC functions / managed MCP).
3. Run the agent and confirm requests are governed and logged.

> Status: planned — contributions welcome.
