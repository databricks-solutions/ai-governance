# Lab 02 — Agent evaluation & monitoring

**Category:** Unity AI Gateway for Agents · **Status:** ✅ Built

Score responses from the governed endpoint with Mosaic AI Agent Evaluation (MLflow) — correctness, relevance, safety, and custom guidelines.

## What you'll do
1. Build a small evaluation dataset (inputs + expected facts).
2. Define a `predict_fn` that calls the governed endpoint.
3. Run `mlflow.genai.evaluate` with a judge panel.
4. Review aggregate metrics and per-example scores (and traces in the Experiments UI).

## Databricks features
- Mosaic AI Agent Evaluation / `mlflow.genai.evaluate` with built-in judges and custom `Guidelines`.
- Evaluation traffic flows through the governed endpoint, inheriting all Gateway controls.

## Prerequisites
- The bundle deployed so the gateway endpoint exists.
- Installs `mlflow[databricks]` + `openai` in the notebook.

## Notes
- Judges call an LLM, so a run takes a couple of minutes.
- For continuous monitoring, schedule this over a dataset sampled from the inference table
  (`models/03-usage-tracking-finops`).
