# Dev tool — Streaming

**Category:** Developer tools · **Status:** 🟡 Planned

## Objective
Stream completions token-by-token from a governed endpoint and confirm that Gateway controls
(rate limits, guardrails, usage tracking) still apply to streamed responses.

## Databricks features
- Server-sent streaming on Model Serving (`stream: true`).

## Outline
1. Send a streaming chat completion request to the governed endpoint.
2. Consume the SSE stream and render tokens incrementally.
3. Verify usage is still recorded and output guardrails still apply.

> Status: planned — contributions welcome.
