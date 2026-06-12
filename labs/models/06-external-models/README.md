# Lab 06 — External models

**Category:** Unity AI Gateway for Models · **Status:** 🟡 Planned

## Objective
Govern third-party models (e.g. OpenAI, Anthropic, Google) behind a Unity AI Gateway
**external-model** endpoint, so the same rate limits, guardrails, usage tracking, and
fallbacks apply uniformly whether the model is hosted on Databricks or external.

## Databricks features
- External model serving endpoints.
- Provider credentials stored as Databricks **secrets** / Unity Catalog connections.
- All Gateway controls from Labs 01–05 applied to the external endpoint.

## Prerequisites
- A provider API key stored in a Databricks secret scope.

## Outline
1. Create a secret scope and store the provider API key.
2. Create an external-model serving endpoint referencing the provider + key.
3. Attach rate limits, guardrails, and usage tracking (reuse `shared/setup`).
4. Invoke the external model through the governed endpoint.
5. Add a Databricks-hosted model as a fallback for cross-provider resiliency.

> Status: planned — contributions welcome.
