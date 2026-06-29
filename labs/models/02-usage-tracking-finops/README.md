# Lab 02 — Usage tracking & FinOps

**Category:** Unity AI Gateway for Models · **Status:** ✅ Built

Turn Gateway telemetry into a FinOps view: tokens and cost by endpoint, user, and day, plus a budget alert.

## What you'll do
1. Confirm usage tracking + payload logging are enabled.
2. Generate traffic, then query `system.serving.endpoint_usage` for token usage.
3. Estimate cost from `system.billing.usage` joined to `system.billing.list_prices`.
4. Build per-user/per-day rollups and a month-to-date **budget alert**.
5. Import `dashboard.lvdash.json` for an AI/BI monitoring dashboard.

## Databricks features
- Unity AI Gateway **usage tracking** and **inference (payload) tables**.
- System tables: `system.serving.endpoint_usage`, `system.billing.usage`, `system.billing.list_prices`.
- AI/BI (Lakeview) dashboard.

## Prerequisites
- The bundle deployed; some traffic sent through the endpoint (the labs do this).
- Access to the `system` catalog (system tables enabled for your workspace).
- Usage rows can lag a few minutes behind live traffic.

## Files
- `notebook.py` — the lab.
- `dashboard.lvdash.json` — importable AI/BI FinOps dashboard.
