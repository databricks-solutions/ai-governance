# Databricks AI Governance Workshop

```
A customer-facing, guided workshop for standing up a governed AI control plane on a
Databricks workspace — and proving it works live. Organized around three pillars —
Choice · Cost · Control — where every step has a concept, a "Try It" action that
exercises a real control against the connected workspace, and a "Verify" step that
proves it fired. Runs in three hours hands-on, plus about an hour of slides and discussion, with optional ~3-hour accelerators for deeper dives.
```

The workshop puts the **Unity AI Gateway** — a single, governed control plane in front of the
models, tools, and agents your organization uses — in front of a room of cloud admins, AI
governance leaders, and principal developers. It ships as a **React + FastAPI Databricks App**
([`workshop_app/`](workshop_app)), driven entirely by one config file so it runs on any customer
workspace, deployed from a single Databricks Asset Bundle.

> The Unity AI Gateway is in Beta. Feature availability and API shapes may change; the workshop
> uses the documented REST/SDK surfaces, and every step that rides a preview reports
> "confirm on this account" rather than a false green.

## Architecture

```
        clients / agents / apps
                  │
                  ▼
        ┌────────────────────────┐
        │   Unity AI Gateway      │  rate limits · guardrails · usage tracking
        │  (governed endpoint)    │  payload logging · fallbacks · traffic routing
        └───────────┬────────────┘
                    │
      ┌─────────────┼──────────────┐
      ▼             ▼              ▼
 Foundation     External      Custom / fine-
 Models         models        tuned models
      │
      ▼
 Unity Catalog: inference tables, system tables, permissions, lineage
```

**Where governance data lands:** per-request token usage and spend in `system.ai_gateway`; the
audit trail in `system.access`; full request/response payloads in Unity Catalog **inference
tables** (`<catalog>.<schema>.*`) for audit, eval, and guardrail review.

## The core workshop — Choice · Cost · Control

Three hours hands-on, plus about an hour of slides and discussion, run top to bottom against the customer's own workspace. Content lives in
[`workshop_app/config/steps.yaml`](workshop_app/config/steps.yaml); the executable checks behind
each **Try It** button live in
[`workshop_app/server/tests_registry.py`](workshop_app/server/tests_registry.py).

- **Choice** — place any model, tool, or agent behind one control plane, addressed as a Unity
  Catalog securable rather than a workspace endpoint name. Connect, discover the model surface,
  and register agents, tools, and MCP servers as first-class UC assets.
- **Cost** — project the cost of routing between models (a real custom router plugs in here), set
  budgets and per-user rate limits, tag for cost attribution, and query usage/cost by project.
- **Control** — create a governed endpoint, apply guardrails on a model service, attach a
  contextual policy to an MCP service (allow reads, deny writes), govern coding-agent traffic, and
  get end-to-end observability — scan the audit log for denied calls and leaked secrets, and open
  traces.

Progress is tracked per team in a JSON file on a Unity Catalog volume, so a room can pause and
resume with no database to provision, and everything you run is included in the exported outcomes.

## Accelerators

Beyond the core workshop, six optional **~3-hour accelerators** each get their own in-app page —
same **concept → Try It → Verify** flow, same progress store, same outcomes export. Run the one or
two that match what the customer needs to unblock rather than all six. They are defined for the
app in [`workshop_app/config/accelerators.yaml`](workshop_app/config/accelerators.yaml) (build plan
and design bar in [`workshop_app/docs/ACCELERATOR_PLAN.md`](workshop_app/docs/ACCELERATOR_PLAN.md)).

Each accelerator also has a folder under [`accelerators/`](accelerators) with a `README.md`, a
**`reference_queries.py`** notebook that reproduces the app's SQL/API checks (one section per
step, so you can reference them **without deploying the app**), and ported deep-dive notebooks.

### 🔌 MCP Servers
Managed vs external MCP, UC permissions, on-behalf-of identity, and service policies — the top
gap being read-only enforcement for coding-agent users while humans keep write. Eleven steps
distinguish the two kinds of MCP (managed UC-native endpoints vs `MCP_SERVICE` securables), prove
OBO identity, write and verify a contextual ALLOW/DENY/ASK policy, scan tool metadata for
poisoning, and show exactly what MCP telemetry does and does not capture.
→ [`accelerators/mcp-servers/`](accelerators/mcp-servers) · [reference queries](accelerators/mcp-servers/reference_queries.py)

### 🤖 Agent Registry
Make agents first-class UC assets — registered, versioned, owned, traced, and governed like any
endpoint. Inventory registered agents, register and version a representative one, confirm
versioning/ownership and traces, and close the identity gap where a custom agent endpoint lacks
the rate limits, guardrails, or usage tracking a model endpoint has.
→ [`accelerators/agent-registry/`](accelerators/agent-registry) · [reference queries](accelerators/agent-registry/reference_queries.py)

### 💻 Coding Agents
Route dev-agent traffic (Claude Code, Cursor, `ucode`, Codex) through the gateway, prove it is
actually governed, attribute per developer, and cap the spend. Catches the silent failures:
traffic landing on a legacy endpoint while limits sit on the new model service, controls that
don't fire on the provider-native path, and leaked secrets in prompts. Includes a live HTTP 429
demo and per-developer attribution with no tagging required.
→ [`accelerators/coding-agents/`](accelerators/coding-agents) · [reference queries](accelerators/coding-agents/reference_queries.py)

### 🌐 External Providers
Route Bedrock, OpenAI, and Anthropic through the gateway with credentials in secrets (never
inline) and access bound to approved workspaces. Inventory current provider access, register an
external route (including the Anthropic OAuth-relay path), verify keys are stored as secrets,
confirm the catalog is `ISOLATED` with explicit workspace bindings, and migrate one shadow
workload as proof.
→ [`accelerators/external-providers/`](accelerators/external-providers) · [reference queries](accelerators/external-providers/reference_queries.py)

### 🛡️ Policies & Guardrails
Prove guardrails actually work — not just that they're on. Safety + PII filter on input and
output, MASK vs BLOCK, how a block is delivered (4xx vs HTTP 200 + reason, and the coding-agent
"sticky block" gotcha), path coverage, and effectiveness measured on a labeled set. The
effectiveness step draws on the in-repo guardrail benchmark.
→ [`accelerators/policies-and-guardrails/`](accelerators/policies-and-guardrails) · [reference queries](accelerators/policies-and-guardrails/reference_queries.py) · [guardrail benchmark](accelerators/policies-and-guardrails/guardrail_benchmark.py)

### 🎛️ Skills
Build, govern, and deploy Agent Skills in Genie Code with a tiered registry and allowlist enforcement.
Register skills as first-class assets, control who can discover and invoke them, and audit skill usage
across your organization.
→ [`accelerators/skills/`](accelerators/skills) · [reference queries](accelerators/skills/reference_queries.py)

## Getting started

The workshop app deploys from **one Databricks Asset Bundle** — no shell script, two standard
commands. Full deploy guide, prerequisites, and the two `system` grants an account admin must run
are in [`workshop_app/README.md`](workshop_app/README.md).

```bash
cd workshop_app

# 1. Deploy: builds the frontend, creates the schema + progress volume, creates the app,
#    and grants the app's service principal — all in one pass.
databricks bundle deploy -t dev -p <profile> \
  --var="warehouse_id=<id>" --var="catalog=<uc-catalog>"

# 2. Start (or restart) the app. Databricks requires a separate run to start app compute.
databricks bundle run ai_governance_workshop_app -t dev -p <profile>
```

**Prerequisites:** the Databricks CLI authenticated to the workspace, a running SQL warehouse, an
existing Unity Catalog catalog, and Node (the bundle builds the frontend on deploy). `warehouse_id`
and `catalog` are **required**. Two `system` schema grants (`system.ai_gateway`, `system.access`)
need an account admin and unlock the telemetry steps — the workshop still runs without them, with
those steps reporting "action needed" rather than failing. See
[`workshop_app/README.md`](workshop_app/README.md) for the complete instructions.

## Reference notebooks (`accelerators/`)

The Databricks notebooks under [`accelerators/`](accelerators) let you reference and run each
accelerator's checks **without deploying the app**. Each folder holds a `README.md`, a
self-contained `reference_queries.py` that reproduces the app's SQL/API checks step by step, and
one or more ported deep-dive notebooks. They are plain notebooks — clone this repo into Databricks
(Repos or **Workspace → Import**), open one, set the widgets, and run. No bundle, no deploy.

## Repository layout

```
workshop_app/           The customer-facing workshop app (React + FastAPI Databricks App)
  config/               workshop.yaml (the one file a customer edits) · steps.yaml · accelerators.yaml
  server/               FastAPI backend — tests_registry.py holds the executable governance tests
  frontend/             React + Vite + Tailwind (Databricks design system)
  databricks.yml        Asset Bundle: app + UC schema + progress volume + grants
  docs/                 APIS_AND_SETUP.md · ACCELERATOR_PLAN.md · PREREQUISITES.md · …

accelerators/           Reference notebooks, one folder per accelerator:
  mcp-servers/            reference_queries.py + managed_mcp.py + function_calling.py
  agent-registry/         reference_queries.py + agent_framework.py + agent_evaluation.py
  coding-agents/          reference_queries.py + rate_limiting.py + usage_tracking_finops.py + openai_agents_sdk.py
  external-providers/     reference_queries.py + traffic_routing.py + fallbacks.py
  policies-and-guardrails/ reference_queries.py + guardrail_benchmark.py + apply_guardrails.py
```

## Maintainers

Maintained by the Databricks Field Engineering team. For questions or issues, open a GitHub
issue (below) or reach a maintainer:

- Scott McKean — scott.mckean@databricks.com
- Tim Lortz — tim.lortz@databricks.com

## How to get help

Databricks support doesn't cover this content. For questions or bugs, please open a
GitHub issue and the team will help on a best effort basis.

## License

&copy; 2025 Databricks, Inc. All rights reserved. The source in this repository is
provided subject to the Databricks License [https://databricks.com/db-license-source].
All included or referenced third party libraries are subject to their respective licenses.

| library | description | license | source |
|---------|-------------|---------|--------|
| databricks-sdk | Databricks SDK for Python | Apache 2.0 | https://github.com/databricks/databricks-sdk-py |
| mlflow | ML lifecycle platform | Apache 2.0 | https://github.com/mlflow/mlflow |
| openai | OpenAI Python client | Apache 2.0 | https://github.com/openai/openai-python |
| requests | HTTP client | Apache 2.0 | https://github.com/psf/requests |
| polars | DataFrame library | MIT | https://github.com/pola-rs/polars |

A full third-party dependency audit for the workshop app and accelerator notebooks — versions,
licenses, and purpose — is in [DEPENDENCIES.md](DEPENDENCIES.md).
