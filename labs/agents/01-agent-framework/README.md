# Lab 01 — Mosaic AI Agent Framework

**Category:** Unity AI Gateway for Agents · **Status:** ✅ Built

Build a `ChatAgent` whose model calls run through the governed endpoint, then log it to MLflow and register it to Unity Catalog.

## What you'll do
1. Define a `ChatAgent` (models-from-code) that calls the governed endpoint.
2. Log it to MLflow with the endpoint declared as a resource dependency.
3. Load it back and test `predict`.
4. Register it to Unity Catalog (deploy is included as an optional next step).

## Databricks features
- Mosaic AI Agent Framework (`mlflow.pyfunc.ChatAgent`), MLflow logging, Unity Catalog model registry.
- `DatabricksServingEndpoint` resource so a deployed agent gets scoped access — no embedded tokens.
- Governed endpoint for all model calls.

## Prerequisites
- The bundle deployed so the gateway endpoint + `${var.catalog}.${var.schema}` schema exist.
- Installs `mlflow[databricks]`, `databricks-agents`, `openai` in the notebook.
- Permission to register models in the schema.

## Notes
- Deploying the agent (`databricks.agents.deploy`) provisions a serving endpoint and takes
  several minutes; the lab registers to UC and leaves deploy as an explicit step.
