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

Prereqs: Databricks CLI ≥ 0.297 authenticated to the workspace, a SQL warehouse, and an
existing Unity Catalog catalog. `frontend/dist` is committed, so Node is only needed if you
change anything under `frontend/src`.

> **`warehouse_id` and `catalog` are required on every `bundle` command.** Neither has a
> default — a customer-deployable bundle can't assume a warehouse or catalog exists. Omit
> either and the command fails immediately with
> `no value assigned to required variable ...`, which is deliberate: the alternative is a
> deploy that succeeds and then fails every governance step in front of the customer.

```bash
# 1. Edit config/workshop.yaml — set at minimum:
#      catalog.name (same value you pass as --var="catalog=..."), and the
#      endpoint / mcp / project names. Leave workspace.warehouse_id blank: the deployed app
#      reads the warehouse from the bundle resource (see app.yaml).

# 2. Deploy — creates the Lakebase instance, the UC schema, and the app
databricks bundle deploy -t dev -p <profile> \
  --var="warehouse_id=<sql-warehouse-id>" \
  --var="catalog=<existing-uc-catalog>"

# 3. Grant the app's service principal what it needs (see below) — REQUIRED

# 4. Start the app
databricks bundle run ai_governance_workshop_app -t dev -p <profile> \
  --var="warehouse_id=<sql-warehouse-id>" \
  --var="catalog=<existing-uc-catalog>"
```

App URL: `https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com`.

Confirm the deploy is healthy before the workshop starts — `GET /api/health` returns
`{"status":"ok"}`, or `{"status":"misconfigured", "config_problems":[...]}` naming exactly
what is unset.

### Grant the app's service principal (required)

The bundle grants the app **only** `CAN_USE` on the warehouse and `CAN_CONNECT_AND_CREATE`
on the Lakebase instance. Every Unity Catalog and system-table grant is manual, and without
them the policy-function step and all usage/cost queries fail. Get the app's service
principal id from `databricks apps get ai-governance-workshop`, then:

```sql
-- Workshop artifacts (the MCP service-policy function lives here)
GRANT USE CATALOG ON CATALOG <catalog> TO `<app-sp-client-id>`;
GRANT USE SCHEMA, CREATE FUNCTION, EXECUTE, SELECT, MODIFY
  ON SCHEMA <catalog>.<schema> TO `<app-sp-client-id>`;

-- Telemetry the Cost and Control pillars read
GRANT USE CATALOG ON CATALOG system TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.serving    TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.billing    TO `<app-sp-client-id>`;
```

Granting on `system` schemas needs a metastore or account admin — line that up before the
workshop rather than during it. See `docs/APIS_AND_SETUP.md` for the full dependency list.

### Known deployment caveats

- **Lakebase provisioning** — the app depends on the instance resource, so Terraform orders
  them, but a first deploy can still outrun a cold `CU_1` instance. The app no longer dies
  if Lakebase is unreachable: it starts without progress tracking and logs a warning, so the
  guidebook and every Try-It step still work.
- **Attendee access** — the bundle adds no `permissions:` block, so by default only the
  deployer can open the app. Grant `CAN_USE` to the workshop group before the session.
- **One deploy per workspace** — the app and Lakebase instance use literal names, so two
  people deploying to the same workspace collide. Override `--var="lakebase_instance=..."`
  and the app `name:` if that matters.

### Local development

```bash
# Backend — local dev has no app resource, so set a warehouse explicitly
DATABRICKS_PROFILE=<profile> DATABRICKS_WAREHOUSE_ID=<id> \
  uv run uvicorn app:app --reload --port 8000
# Frontend (proxies /api to :8000)
cd frontend && npm ci && npm run dev
```

After changing anything in `frontend/src`, rebuild and commit `frontend/dist` — it is
committed so the app deploys without Node:

```bash
cd frontend && npm ci && npm run build
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
