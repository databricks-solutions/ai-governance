# Dev tool — Mock server

**Category:** Developer tools · **Status:** 🟡 Planned

## Objective
A local OpenAI-compatible mock server so labs and agents can be developed and tested offline,
without consuming a real endpoint or incurring cost.

## Databricks features
- OpenAI-compatible request/response shape matching the governed Databricks endpoint.

## Outline
1. Run the mock server locally (OpenAI chat-completions shape).
2. Point a lab/agent's base URL at the mock.
3. Develop logic offline, then switch the base URL to the governed endpoint.

> Status: planned — contributions welcome.
