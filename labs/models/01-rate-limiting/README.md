# Lab 01 — Rate limiting

**Category:** Unity AI Gateway for Models · **Status:** ✅ Built

Cap traffic to a serving endpoint to protect shared capacity and control spend.

## What you'll do
1. Inspect the endpoint's current Gateway configuration.
2. Apply an **endpoint-wide** limit and a **per-user** limit (requests/minute).
3. Drive traffic past the limit and observe `429 Too Many Requests`.
4. Relax the limit to production-appropriate values.

## Databricks features
- Unity AI Gateway **rate limits** (`rate_limits`, scoped by `endpoint` or `user`).
- Model Serving invocation API.

## Prerequisites
- The bundle deployed (`scripts/deploy.sh deploy`) so the `${var.gateway_endpoint}` endpoint exists.
- Permission to update the endpoint's AI Gateway configuration.

## Run it
Open `notebook.py` in your workspace and run top-to-bottom, or run it via the
`run_core_labs` job. Set the `endpoint_name`, `catalog`, and `schema` widgets if you
deployed with non-default values.
