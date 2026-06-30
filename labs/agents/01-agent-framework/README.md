# Lab 01 — Mosaic AI Agent Framework

**Build a first-class Databricks `ChatAgent` whose model calls run through the governed endpoint, then log it to MLflow and register it to Unity Catalog.**

## What you'll do
1. Define a `ChatAgent` (models-from-code) that answers through the governed endpoint.
2. Log it to MLflow with the endpoint declared as a resource dependency.
3. Load it back and test `predict`.
4. Register it to Unity Catalog (deploy is included as an optional next step).

## How it works
The agent calls the governed endpoint via the Databricks deployments client, so it inherits
every Gateway control — rate limits, guardrails, usage tracking, and payload logging — instead
of reimplementing governance per agent. Declaring the endpoint as a `DatabricksServingEndpoint`
resource gives a future deployment automatic, scoped access with no embedded tokens. Registered
in Unity Catalog, the agent is versioned and permissioned like any other asset, and its own
serving endpoint is itself governable by the Gateway. Deploying provisions dedicated capacity
and takes several minutes, so it's left as an explicit step.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `[AI Governance] Agent labs (framework + evaluation)` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
