# Lab 01 — Mosaic AI Agent Framework

**Category:** Unity AI Gateway for Agents · **Status:** 🟡 Planned

## Objective
Build an agent with the Mosaic AI **Agent Framework** that calls models and tools exclusively
through governed Gateway endpoints, then log and deploy it via MLflow + Unity Catalog.

## Databricks features
- Mosaic AI Agent Framework, MLflow models, Unity Catalog model registry.
- Governed model + tool endpoints from the Models and Tools labs.

## Outline
1. Define an agent that calls the governed endpoint and UC-function tools.
2. Log the agent to MLflow and register it in Unity Catalog.
3. Deploy it as a serving endpoint (itself governed by the Gateway).
4. Confirm rate limits, guardrails, and usage tracking apply end to end.

> Status: planned — contributions welcome.
