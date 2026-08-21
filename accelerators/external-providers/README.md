# Accelerator — External Providers

Route Bedrock, OpenAI, and Anthropic through the gateway with credentials in secrets (never
inline) and access bound to approved workspaces. A ~4-hour deep dive on bringing shadow
provider access onto one governed path.

Register providers as external models behind a governed endpoint so they inherit the same limits,
guardrails, and logging. For Anthropic, the newer **OAuth-relay** path connects a Claude
subscription without storing a long-lived key. "Approved models" is only advisory until the
catalog holding them is `isolation_mode = ISOLATED` with explicit workspace bindings.

## What you'll prove

Inventory current provider access · find external-provider routes on the workspace · confirm
provider keys are stored as secrets, not inline · confirm the approved-models catalog is
`ISOLATED` with workspace bindings · migrate one shadow workload and confirm its usage attributes
by project tag.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`reference_queries.py`](reference_queries.py) | The app's checks for all five steps — inventory, routing, secret readiness, workspace binding, usage-by-project — runnable without the app. |
| [`traffic_routing.py`](traffic_routing.py) | Deep dive: load balancing + A/B/canary across backends behind one endpoint. |
| [`fallbacks.py`](fallbacks.py) | Deep dive: automatic failover across served entities. |

## Prerequisites

- A SQL warehouse and `SELECT` on `system.ai_gateway` for the usage-by-project step.
- Permission to read catalog isolation + workspace bindings (the binding check).
- To see non-empty results, at least one external-model endpoint registered and some traffic
  tagged with the project name; otherwise the steps report "action required" with guidance.

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. The reference queries are read-only;
`traffic_routing.py` and `fallbacks.py` reconfigure a serving endpoint's served entities.
