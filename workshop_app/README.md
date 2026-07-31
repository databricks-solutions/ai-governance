# AI Governance Workshop — Customer App

A customer-facing, guided workshop app for standing up a **governed AI control plane** on a
Databricks workspace and proving it works live. It's organized around three pillars —
**Choice · Control · Clarity** — and every step has a **concept**, a **Try It** action that
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

- **Choice** — connect, discover the model surface, and see the cost impact of routing between
  models (a routing-agent example plugs in here).
- **Control** — create a governed endpoint, apply guardrails on a model service, and attach a
  contextual policy to an MCP service (allow reads, deny writes). Try-It steps send blocked
  prompts / probe tool calls and show the control firing.
- **Clarity** — tag for cost attribution, query usage/cost by project, scan the audit log for
  denied calls and leaked secrets, and open traces.

The governance tests are ported from the `l200_demo` Streamlit app into FastAPI endpoints, so
each step's **Try It** button runs a real check (list endpoints, create/verify a governed
endpoint, query system/inference tables, create an MCP policy function, etc.).

## Deploy on a customer workspace

Prereqs: Databricks CLI ≥ 0.297 authenticated to the workspace, a SQL warehouse, and Node
(to build the frontend locally — `node_modules` is never uploaded, but `frontend/dist` is).

```bash
# 1. Edit config/workshop.yaml — set at minimum:
#      workspace.warehouse_id, catalog.name/schema, and the endpoint/mcp/project names.

# 2. Build the frontend
cd frontend && npm install && npm run build && cd ..

# 3. Deploy the bundle (creates the Lakebase instance + the app)
databricks bundle deploy -t dev -p <profile> --var="warehouse_id=<sql-warehouse-id>"

# 4. Start the app
databricks bundle run ai_governance_workshop_app -t dev -p <profile>
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
one row per `(run_id, step_id)` with `status` (not_started / in_progress / done / failed), the
last Try-It/Verify `last_result` (JSON), and timestamps. `run_id` is a team/session label so
multiple teams can track independently on the same deployment.

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
- **Routing agent (Choice):** the `routing_cost` test is a placeholder that names the frontier
  vs cost-efficient endpoints; replace it with a real routing agent that reports live token cost
  per model.
- **Point at a different workspace:** edit `config/workshop.yaml` (or a `workshop.local.yaml`
  override) — no code changes.
