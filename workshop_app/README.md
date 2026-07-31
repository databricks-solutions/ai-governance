# AI Governance Workshop — Customer App

A customer-facing, guided workshop app for standing up a **governed AI control plane** on a
Databricks workspace and proving it works live. It's organized around three pillars —
**Choice · Cost · Control** — and every step has a **concept**, a **Try It** action that
exercises the control against the connected workspace, and a **Verify** step that proves it
fired. Progress is tracked per team in Lakebase so a room can pause and resume.

React + FastAPI Databricks App, deployed from one Asset Bundle, driven entirely by a single
config file so it runs on any customer workspace.

## Structure

```
workshop_app/
  config/
    workshop.yaml     ← the ONE file a customer edits (warehouse, catalog, endpoints, mcp, project)
    steps.yaml        ← the guidebook: intro + pillars/steps (concept / try-it / verify)
  server/             FastAPI backend
    tests_registry.py ← the executable governance tests (ported from l200_demo)
    workspace_sql.py  ← SQL against the workspace warehouse (system tables, inference tables)
    db.py             ← Lakebase progress store
    deep_links.py     ← links into the workspace UI for manual steps
    routes/workshop.py
  frontend/           React + Vite + Tailwind (Databricks design system)
  databricks.yml      Asset Bundle: app + Lakebase instance
  app.yaml            App runtime config
```

## What each pillar covers

- **Choice** — open, multi-AI ecosystem: connect, discover the model surface, and register
  agents, tools, and MCP servers as first-class Unity Catalog assets.
- **Cost** — intelligent cost controls: see the cost impact of routing between models (a
  routing-agent example plugs in here), set budgets and hard spend caps, tag for cost
  attribution, and query usage/cost by project.
- **Control** — agent-aware data + AI governance: create a governed endpoint, apply guardrails
  on a model service, attach a contextual policy to an MCP service (allow reads, deny writes),
  govern coding-agent traffic, and get end-to-end observability — scan the audit log for denied
  calls and leaked secrets, open traces, and confirm Lakewatch telemetry.

The governance tests are ported from the `l200_demo` Streamlit app into FastAPI endpoints, so
each step's **Try It** button runs a real check (list endpoints, create/verify a governed
endpoint, query system/inference tables, create an MCP policy function, etc.).

## Accelerators (optional add-ons)

Beyond the core workshop, five optional **~4-hour accelerators** each get their own page (same
concept → Try It → Verify flow), driven by `config/accelerators.yaml`:

- **MCP Servers** — on-behalf-of auth to a managed/external MCP.
- **Agent Registry** — register, version, and own a representative agent.
- **Coding Agents** — govern dev-agent traffic with per-developer attribution
  and code-secret detection.
- **External Providers** — route Bedrock/OpenAI/Anthropic through the Gateway;
  migrate one shadow workload.
- **Policies & Guardrails** — safety filter on input/output, custom PII-leakage
  judge, red-team dataset.

Run the one that matches the customer's priority (the accelerator overview and links live on
the in-app **Introduction** page). Accelerator progress is tracked in Lakebase and included in
the exported outcomes, so anything you run shows up in the internal sales app.

## Deploy on a customer workspace

Prereqs: Databricks CLI ≥ 0.297 authenticated to the workspace, a SQL warehouse, and Node
(to build the frontend locally — `node_modules` is never uploaded, but `frontend/dist` is).

> **You must supply a SQL warehouse id on every `bundle` command.** The bundle has no
> default warehouse (it's customer-deployable and can't assume one exists), so both
> `bundle deploy` and `bundle run` require `--var="warehouse_id=<sql-warehouse-id>"`.
> Omitting it fails with `Invalid SQL warehouse resource sql-warehouse: ID  is invalid.`

```bash
# 1. Edit config/workshop.yaml — set at minimum:
#      workspace.warehouse_id, catalog.name/schema, and the endpoint/mcp/project names.

# 2. Build the frontend
cd frontend && npm install && npm run build && cd ..

# 3. Deploy the bundle (creates the Lakebase instance + the app) — warehouse id is required
databricks bundle deploy -t dev -p <profile> --var="warehouse_id=<sql-warehouse-id>"

# 4. Start the app — warehouse id is required here too
databricks bundle run ai_governance_workshop_app -t dev -p <profile> --var="warehouse_id=<sql-warehouse-id>"
```

App URL: `https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com`.
If the first deploy fails with "database instance ... does not exist", the Lakebase instance
is still provisioning — wait until it's `AVAILABLE` and re-run the deploy.

### Local development

```bash
# Backend (uses your CLI profile; set a warehouse in config or DATABRICKS_WAREHOUSE_ID)
DATABRICKS_PROFILE=<profile> uv run uvicorn app:app --reload --port 8000
# Frontend (proxies /api to :8000)
cd frontend && npm run dev
```

## Progress tracking (Lakebase)

Progress is stored in the bundle's Lakebase instance, schema `workshop`, table `step_progress`:
one row per `(customer_sfid, step_id)` with `status` (not_started / in_progress / done / failed),
the last Try-It/Verify `last_result` (JSON), and timestamps. The whole workshop is keyed to the
Salesforce account id set on the Introduction page, so progress and the outcomes export flow
straight into the internal sales app. (Deployments from before this change auto-migrate the
legacy `run_id` column to `customer_sfid` on startup.)

## Export → the internal sales app

The Intro page's **Export workshop outcomes** panel produces two files (the deliverer confirms
the Salesforce account id first):

- **`<sfid>_workshop_report.md`** — a per-step complete/incomplete report grouped by pillar, for
  the customer leave-behind (`GET /api/export/report`).
- **`<sfid>_workshop_outcomes.json`** — the machine-readable outcomes (`schema_version` 1) the
  internal AI Governance sales app ingests to track the account and drive next steps
  (`GET /api/export/outcomes`). Load it in that app's **Account Journey → Workshop handoff**.

## Extending

- **Add a step:** add an entry under a pillar in `config/steps.yaml`. If it has a `test`, add a
  matching function to `server/tests_registry.py` and register it in `REGISTRY`.
- **Routing agent (Cost):** the `routing_cost` test is a placeholder that names the frontier
  vs cost-efficient endpoints; replace it with a real routing agent that reports live token cost
  per model.
- **Point at a different workspace:** edit `config/workshop.yaml` (or a `workshop.local.yaml`
  override) — no code changes.
