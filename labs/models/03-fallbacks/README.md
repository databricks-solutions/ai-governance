# Lab 03 — Fallbacks

**Make an endpoint resilient: when the primary model errors, the Gateway transparently retries against a fallback.**

## What you'll do
1. Add a second served entity to the endpoint as the fallback.
2. Enable Gateway fallbacks (`fallback_config.enabled`).
3. Send traffic and confirm requests still succeed.

## How it works
When the primary served entity returns an error (rate limit, timeout, provider outage), the Gateway automatically retries the request against the next served entity on the endpoint — transparently to the caller. Served entities are tried in order, so keep `primary` first and `fallback` second with the fallback route at 0% traffic, so it only serves on failure. Both entities here wrap Databricks Foundation Models as external models, so you can fail over across providers. Fallbacks are configured once at the Gateway and apply to every caller. For intentional traffic splitting across models instead, see Lab 04 — Traffic routing.

To disable: `put_ai_gateway({"fallback_config": {"enabled": False}})`.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_core_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`. The lab waits for the endpoint to finish updating, which can take a few minutes.
