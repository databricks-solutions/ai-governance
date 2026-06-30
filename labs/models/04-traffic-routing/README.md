# Lab 04 — Traffic routing

**Split traffic across multiple served entities behind one endpoint for load balancing and A/B/canary rollouts.**

## What you'll do
1. Put a champion + challenger model behind the endpoint.
2. Split traffic 50/50 and observe which entity serves each request.
3. Shift to a 90/10 canary, then promote the winner (or roll back).

## How it works
One endpoint can front multiple served entities and split traffic across them by percentage, enabling **load balancing** across backends and **A/B testing** a new model against the incumbent — all behind a single, governed URL, so callers never change. Each response reports which served entity handled the request; over many calls the distribution approaches the configured split. The config API replaces the whole config, so the entities are re-sent on every split change. Pair with usage tracking (Lab 02) to compare cost/latency per entity, and fallbacks (Lab 03) for resilience on top of the split.

To restore a single served entity: `set_split(100, 0)`.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_core_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`. Updates wait for the endpoint to finish reconciling, which can take a few minutes.
