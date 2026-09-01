# Accelerator — Agent Registry

Make agents first-class Unity Catalog assets — registered, versioned, owned, traced, and governed
like any endpoint. A ~3-hour deep dive that turns one-off agent deploys into reproducible,
rollback-able UC models with owners and telemetry.

A one-off deploy is not a registered agent. Each agent should be a UC model with an owner and a
version history, emitting MLflow traces, and — where it runs as a serving endpoint — carrying the
same rate limits, guardrails, and usage tracking a model endpoint does.

## What you'll prove

Inventory registered agents & tools · register and version a representative agent · confirm
versioning + ownership · confirm the telemetry tables are populated · close the identity gap where
a custom agent endpoint lacks the controls a model endpoint has.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`reference_queries.py`](reference_queries.py) | The app's checks for the inventory, versioning, telemetry, and endpoint-governance steps — runnable without the app. |
| [`agent_framework.py`](agent_framework.py) | Deep dive: build a Mosaic AI agent on governed endpoints, log it, and register it to Unity Catalog. |
| [`agent_evaluation.py`](agent_evaluation.py) | Deep dive: evaluate and monitor a governed agent with MLflow judges. |

## Prerequisites

- A SQL warehouse and an existing Unity Catalog catalog + schema.
- `SELECT` on `system.ai_gateway` and `system.access` (account/metastore admin grants) for the
  telemetry-readiness step.
- Permission to create registered models / functions in the schema (for `agent_framework.py`).

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. The registration step
(`agent_framework.py`) creates a UC model; the reference queries are read-only apart from that.
