# Lab 04 — Traffic routing

**Category:** Unity AI Gateway for Models · **Status:** ✅ Built

Split traffic across multiple served entities behind one endpoint for load balancing and A/B/canary rollouts.

## What you'll do
1. Put a champion + challenger model behind the endpoint.
2. Split traffic 50/50 and observe which entity serves each request.
3. Shift to a 90/10 canary, then promote the winner (or roll back).

## Databricks features
- Model Serving **traffic config** (percentage routes across served entities).
- A single governed endpoint URL for all callers.

## Prerequisites
- The bundle deployed so the gateway endpoint exists.
- Permission to update the endpoint config.

## Notes
- Updates wait for the endpoint to finish reconciling (can take a few minutes).
- For failure-only fallback rather than intentional splitting, see **Lab 03 — Fallbacks**.
