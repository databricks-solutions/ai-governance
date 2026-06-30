# Lab 02 — Usage tracking & FinOps

**Turn Gateway telemetry into a FinOps view: tokens and cost by endpoint, user, and day, plus a budget alert.**

## What you'll do
1. Confirm usage tracking + payload logging are enabled.
2. Generate traffic, then query `system.serving.endpoint_usage` for token usage.
3. Estimate cost from `system.billing.usage` joined to `system.billing.list_prices`.
4. Build per-user/per-day rollups and a month-to-date **budget alert**.
5. Inspect the inference (payload) table.
6. Import `dashboard.lvdash.json` for an AI/BI monitoring dashboard.

## How it works
The Gateway records every request to **system tables** and, when enabled, full request/response payloads to an **inference table** in Unity Catalog. `system.serving.endpoint_usage` gives token-level usage by user and time (join `system.serving.served_entities` to map to an endpoint name). `system.billing.usage` joined to `system.billing.list_prices` gives dollar cost by endpoint. Inference tables capture full payloads for audit, eval, and guardrail review. Usage and payload rows can lag live traffic by a few minutes, so re-run if a query is empty right after sending traffic.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_core_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`. Needs access to the `system` catalog (system tables enabled for your workspace).
