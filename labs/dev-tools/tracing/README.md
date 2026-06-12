# Dev tool — Tracing

**Category:** Developer tools · **Status:** 🟡 Planned

## Objective
Trace gateway-routed model and tool calls with **MLflow tracing** for step-by-step debugging
and latency analysis of agents and pipelines.

## Databricks features
- MLflow 3 tracing / autologging against governed endpoints.

## Outline
1. Enable MLflow tracing in the client/agent.
2. Invoke the governed endpoint and inspect the captured spans.
3. Correlate traces with inference-table rows for full request context.

> Status: planned — contributions welcome.
