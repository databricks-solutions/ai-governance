# Lab 01 — Rate limiting

**Cap traffic to a serving endpoint with the Unity AI Gateway to protect shared capacity and control spend.**

## What you'll do
1. Inspect the endpoint's current Gateway configuration.
2. Apply an **endpoint-wide** limit and a **per-user** limit (requests/minute).
3. Drive traffic past the limit and observe `429 Too Many Requests`.
4. Relax the limit to production-appropriate values.

## How it works
Rate limits cap how much traffic a serving endpoint will accept. The Gateway can limit by **requests** or **tokens**, and scope each limit to the whole **endpoint** or to an individual **user** (`key`); `renewal_period` is always `minute`. Limits are enforced at the Gateway, *before* model compute is consumed, so excess calls are rejected with HTTP `429`. Per-user limits stop a single caller from starving everyone else on a shared endpoint. Enforcement is eventually consistent, so a config change can take a short time to engage.

To remove limits entirely: `put_ai_gateway({"rate_limits": []})`.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_core_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
