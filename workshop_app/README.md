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
  calls and leaked secrets, and open traces.

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

**Prereqs:** Databricks CLI authenticated to the workspace, a SQL warehouse, an existing
Unity Catalog catalog, and Node (to build the frontend).

```bash
./deploy.sh -p <cli-profile> -w <warehouse-id> -c <uc-catalog>
```

That's the whole deploy. The script is idempotent — re-run it any time — and it:

1. checks the profile authenticates and that the warehouse **and catalog actually exist**,
   failing early with the command to list them rather than mid-deploy
2. builds the frontend
3. pins `catalog`/`schema` into `config/workshop.local.yaml` so the app and the bundle can
   never disagree
4. deploys the bundle — Lakebase instance, UC schema, the app
5. reads back the app's service principal and re-deploys so the **UC grants attach
   automatically**
6. prints the two `system` GRANT statements for your account admin
7. starts the app and polls until it reports healthy

Add `-g <group>` to grant a specific group `CAN_USE` on the app (default: `users`), and
`-s <schema>` to change the schema name.

Only one thing is left for a human: the two `system` grants below. Everything else is done.

App URL: `https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com`.
`GET /api/health` returns `{"status":"ok"}`, or `misconfigured` naming exactly what is unset.

<details>
<summary>Manual equivalent, if you can't run the script</summary>

```bash
cd frontend && npm ci && npm run build && cd ..

# warehouse_id and catalog are required — no defaults, so a missing one fails immediately
# rather than deploying an app that fails every governance step in front of the customer.
databricks bundle deploy -t dev -p <profile> \
  --var="warehouse_id=<id>" --var="catalog=<catalog>"

# Read the app's service principal, then re-deploy so the schema grants attach to it
APP_SP=$(databricks apps get ai-governance-workshop -p <profile> --output json \
          | jq -r .service_principal_client_id)
databricks bundle deploy -t dev -p <profile> \
  --var="warehouse_id=<id>" --var="catalog=<catalog>" \
  --var="app_service_principal_id=$APP_SP"

databricks bundle run ai_governance_workshop_app -t dev -p <profile> \
  --var="warehouse_id=<id>" --var="catalog=<catalog>"
```

Also set `catalog.name`/`catalog.schema` in `config/workshop.yaml` to the same values, or
the app will write to a different schema than the bundle created.
</details>

> **No lockfile yet.** `frontend/package-lock.json` is intentionally absent — the one
> generated here was missing `resolved`/`integrity` for nearly every package, so `npm ci`
> produced an unusable `node_modules`. Run a real `npm install` in `frontend/` on a machine
> with npm registry access and commit the result, then `npm ci` (and reproducible builds)
> work. Until then `deploy.sh` falls back to `npm install`, and only builds when
> `frontend/dist` is actually stale — so a deploy from a prebuilt `dist` needs no registry
> access at all.

### The one manual step: two `system` grants (account admin)

`deploy.sh` handles the warehouse, Lakebase, schema, and app-group grants. Unity Catalog
`system` schemas can't be granted from a bundle and need an account or metastore admin, so
the script prints these with the real service principal filled in:

```sql
GRANT USE CATALOG ON CATALOG system TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO `<app-sp-client-id>`;  -- usage, spend
GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO `<app-sp-client-id>`;  -- audit trail
```

**Only these two schemas.** The app deliberately reads no other — `system.billing`,
`system.serving`, and `system.information_schema` were all removed once each turned out to
be avoidable (see `docs/APIS_AND_SETUP.md`).

**If the grants aren't ready, the workshop still runs.** The model panel, full routing ROI,
endpoint discovery, asset inventory, rate limits, guardrail tests, and MCP policy
create/verify all use the serving and UC APIs and need no `system` access. Only the telemetry
steps do, and they report "action needed" rather than failing.

| Grant | Unlocks | Skippable? |
|---|---|---|
| `<catalog>.<schema>` | MCP policy function, inference-table reads, asset inventory | No |
| `system.ai_gateway` | Spend by model, budgets, per-developer attribution, routing ROI context | Only if you drop the Cost pillar's telemetry steps |
| `system.access` | Audit trail, secret-leak scan | Only if you drop `audit_scan` |

Everything else — the model panel, the routing ROI, endpoint discovery, guardrail and policy
tests — works with **no `system` grant at all**, because they use the serving and Unity
Catalog APIs directly. If `system` access can't be arranged in time, the workshop still
delivers; those two steps report `action_required` instead of failing.

See `docs/APIS_AND_SETUP.md` for the full dependency list.

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
