# Accelerator — Coding Agents

Route dev-agent traffic (Claude Code, Cursor, `ucode`, Codex) through the gateway, prove it is
actually governed, attribute per developer, and cap the spend. A ~3-hour deep dive on the surface
where the field sees the most questions and the most silent failures.

Coding agents call model providers directly by default. Pointing them at the governed model
service (OpenAI-compatible base URL + the service FQN as the model) puts every request behind the
gateway's limits, guardrails, and telemetry — and they identify themselves in `user_agent`, so
spend attributes to a real developer with no tagging. Prefer **OAuth** over a PAT.

## What you'll prove

Check where coding-agent traffic actually lands (governed model service vs a legacy endpoint) ·
per-developer attribution · whether controls fire on the provider-native path as well as the
OpenAI-compatible one · a live HTTP 429 from a burst · 30-day spend per model/user · a secret-leak
scan over denied/failed audit rows.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`reference_queries.py`](reference_queries.py) | The app's checks for all six steps — routing, attribution, path coverage, the 429 burst, budget, and audit scan — runnable without the app. |
| [`rate_limiting.py`](rate_limiting.py) | Deep dive: per-endpoint & per-user token/request limits and observing `429`. |
| [`usage_tracking_finops.py`](usage_tracking_finops.py) | Deep dive: tokens & cost from system tables + a budget alert. Ships with [`usage_dashboard.lvdash.json`](usage_dashboard.lvdash.json). |
| [`openai_agents_sdk.py`](openai_agents_sdk.py) | Deep dive: point an existing agent stack at the OpenAI-compatible endpoint. |

## Prerequisites

- A SQL warehouse; `SELECT` on `system.ai_gateway` (attribution, routing, budget) and
  `system.access` (audit scan) — account/metastore admin grants.
- A governed serving endpoint with rate limits configured (for the 429 demo). Rate-limit changes
  can take ~1–2 hours to take effect, and the limit must apply to the caller's identity (or be
  endpoint-wide) to trip.
- Some coding-agent traffic already routed through the gateway, or the attribution/route steps
  return "no traffic yet".

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. The 429 burst sends real requests to
the endpoint; everything else is read-only.
