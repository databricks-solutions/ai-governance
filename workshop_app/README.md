# AI Governance Workshop — Customer App

A customer-facing, guided workshop app for standing up a **governed AI control plane** on a
Databricks workspace and proving it works live. It's organized around three pillars —
**Choice · Cost · Control** — and every step has a **concept**, a **Try It** action that
exercises the control against the connected workspace, and a **Verify** step that proves it
fired. Progress is tracked per team in a JSON file on a Unity Catalog volume, so a room can
pause and resume with no database to provision.

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
    store.py          ← progress store: one JSON file on a UC volume (in-memory + write-through)
    deep_links.py     ← links into the workspace UI for manual steps
    routes/workshop.py
  frontend/           React + Vite + Tailwind (Databricks design system)
  databricks.yml      Asset Bundle: app (command + env) + UC schema + progress volume + grants
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
the in-app **Walkthrough** page). Accelerator progress is tracked in the same volume-backed
store and included in the exported outcomes, so anything you run shows up in the internal
sales app.

## Deploy on a customer workspace

It's a plain Databricks Asset Bundle — **no shell script**. Two standard commands:

```bash
# 1. Deploy: builds the frontend, creates the schema + progress volume, creates the app, and
#    grants the app's service principal on the schema/volume — all in one pass.
databricks bundle deploy -t dev -p <profile> \
  --var="warehouse_id=<id>" --var="catalog=<uc-catalog>"

# 2. Start (or restart) the app. Databricks requires a separate run to start app compute —
#    a deploy alone does not start it.
databricks bundle run ai_governance_workshop_app -t dev -p <profile>
```

**Prereqs:** Databricks CLI authenticated to the workspace, a running SQL warehouse, an
existing Unity Catalog catalog, and Node (the bundle builds the frontend for you on deploy).

`warehouse_id` and `catalog` are **required** (no defaults), so a missing one fails immediately
rather than deploying an app that fails every step in front of the customer. Optional overrides:
`--var="workshop_group=<group>"` (who gets `CAN_USE` on the app; default `users`),
`--var="schema=<name>"`, `--var="progress_volume=<name>"`. Both commands are idempotent —
re-run them any time.

**How it's fully declarative.** The app receives its `catalog`/`schema`/`warehouse_id` as env
straight from the bundle variables (`apps.*.config.env` in `databricks.yml`), so there's no
config file to pin and the bundle is the single source of truth. The schema `grants` reference
`${resources.apps.….service_principal_client_id}`, so Terraform creates the app, reads its
service principal, and applies the grant in one `bundle deploy` — the old two-pass deploy is
gone. The frontend build runs as the bundle's `artifacts` step.

App URL: `https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com`.
`GET /api/health` returns `{"status":"ok"}`, or `misconfigured` naming exactly what is unset.

> **Local development** points the app at a workspace without the bundle — set
> `DATABRICKS_WAREHOUSE_ID`, `WORKSHOP_CATALOG`, and `WORKSHOP_SCHEMA` in the environment (or
> a `config/workshop.local.yaml` override). See the Local development section below.

> **Lockfile.** `frontend/package-lock.json` is committed and complete, so `npm ci` gives a
> reproducible build. If your environment routes package installs through a private registry
> mirror, point npm at it (`npm config set registry <your-mirror>`) before building; the
> integrity hashes in the lockfile are registry-independent.

### The one manual step: two `system` grants (account admin)

The bundle handles the warehouse, schema, and progress-volume grants (`READ/WRITE VOLUME`) to
the app's service principal automatically. Unity Catalog `system` schemas are the one thing no
bundle can grant — they need an account or metastore admin. Get the app's service principal
with `databricks apps get ai-governance-workshop -p <profile> --output json` (field
`service_principal_client_id`), then have your admin run:

```sql
GRANT USE CATALOG ON CATALOG system TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO `<app-sp-client-id>`;  -- usage, spend
GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO `<app-sp-client-id>`;  -- audit trail
```

(The app's Walkthrough page also shows these grants, and `GET /api/health` reports whether the
telemetry steps have what they need.)

**Only these two schemas.** The app deliberately reads no other — `system.billing`,
`system.serving`, and `system.information_schema` were all removed once each turned out to
be avoidable (see `docs/APIS_AND_SETUP.md`).

**If the grants aren't ready, the workshop still runs.** The model panel, full routing ROI,
endpoint discovery, asset inventory, rate limits, guardrail tests, the model-reach check
(`default_access`), the endpoint ACL check, and MCP policy create/verify all use the serving and
UC APIs and need no `system` *data* access. Only the telemetry steps do, and they report "action
needed" rather than failing.

(`default_access` reads the app identity's **effective permissions** on `system` / `system.ai`
through the UC permissions API — a metadata read that does not need `SELECT` on any `system`
schema.)

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

- **Progress store is best-effort** — progress lives in a JSON file on a UC volume. The app
  never dies if the volume is briefly unreachable: it starts without progress tracking, keeps
  the in-memory copy, and retries the write on the next update. The guidebook and every Try-It
  step still work regardless.
- **Attendee access** — the bundle adds no `permissions:` block, so by default only the
  deployer can open the app. Grant `CAN_USE` to the workshop group before the session.
- **One deploy per workspace** — the app uses a literal name, so two people deploying to the
  same workspace collide. Override the app `name:` (and `--var="schema=..."`) if that matters.

### Local development

```bash
# Backend — local dev has no bundle, so pass the values the bundle would inject as env
DATABRICKS_PROFILE=<profile> DATABRICKS_WAREHOUSE_ID=<id> \
  WORKSHOP_CATALOG=<catalog> WORKSHOP_SCHEMA=ai_governance_workshop \
  uv run uvicorn app:app --reload --port 8000
# Frontend (proxies /api to :8000)
cd frontend && npm ci && npm run dev
```

After changing anything in `frontend/src`, rebuild and commit `frontend/dist` — it is
committed so the app deploys without Node:

```bash
cd frontend && npm ci && npm run build
```

## Progress tracking (UC volume)

Progress is stored in a single JSON file on the bundle's Unity Catalog volume
(`/Volumes/<catalog>/<schema>/workshop_state/progress.json`), keyed by `customer_sfid` then
`step_id`: each entry carries `status` (not_started / in_progress / action_required / done /
failed), the last Try-It/Verify `last_result` (JSON), notes, and a timestamp. The app reads the
file into memory at startup (`server/store.py`) and rewrites it write-through on every update —
there is no database to provision, wait on, or grant CONNECT to. The whole workshop is keyed to
the Account ID set on the Walkthrough page, so progress and the outcomes export flow straight
into the internal sales app.

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
- **Routing agent (Cost):** `server/routing.py` runs a real custom router (cheap classifier →
  cheapest sufficient model) and reports live token cost per model. Retarget the three tiers
  with `cost.routing.endpoints` in `config/workshop.yaml`, and set `dbu_to_usd` to the
  negotiated rate — until then the dollars are list-price illustrative.
- **Point at a different workspace:** edit `config/workshop.yaml` (or a `workshop.local.yaml`
  override) — no code changes.
