# Lab 04 — Fallbacks

**Category:** Unity AI Gateway for Models · **Status:** ✅ Built

Make an endpoint resilient: when the primary model errors, the Gateway transparently retries against a fallback.

## What you'll do
1. Add a second served entity to the endpoint as the fallback.
2. Enable Gateway fallbacks (`fallback_config.enabled`).
3. Send traffic and confirm requests still succeed.

## Databricks features
- Unity AI Gateway **fallbacks** (`fallback_config`).
- Multiple **served entities** + traffic config on one Model Serving endpoint.

## Prerequisites
- The bundle deployed so the gateway endpoint exists.
- Permission to update the endpoint config and its AI Gateway configuration.

## Notes
- Keep the fallback route at 0% traffic so it only serves on failure. For intentional
  splitting across models, see **Lab 05 — Traffic routing**.
- The lab waits for the endpoint to finish updating, which can take a few minutes.
