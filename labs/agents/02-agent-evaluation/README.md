# Lab 02 — Agent evaluation & monitoring

**Score responses from the governed endpoint with Mosaic AI Agent Evaluation (MLflow) — correctness, relevance, safety, and custom guidelines.**

## What you'll do
1. Build a small evaluation dataset (inputs + expected facts).
2. Define a `predict_fn` that calls the governed endpoint.
3. Run `mlflow.genai.evaluate` with a panel of judges.
4. Review aggregate metrics and per-example scores (and traces in the Experiments UI).

## How it works
Governance isn't only access and cost — it's also quality. The evaluation calls the governed
endpoint, so quality checks share the same guardrails, limits, and logging as production
traffic. A panel of built-in judges (Correctness, RelevanceToQuery, Safety) plus a custom
`Guidelines` judge covers quality, safety, and style; the judges call an LLM, so a run takes a
couple of minutes. Results log to an MLflow experiment for trend monitoring. Schedule this over
a dataset sampled from the inference table (`models/02-usage-tracking-finops`) to monitor
quality continuously and feed regressions back into guardrail and limit tuning.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `[AI Governance] Agent labs (framework + evaluation)` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
