# Intelligent AI FinOps (V2)

A deployable Databricks App that turns the "route each query to the cheapest model
that still clears a quality bar" story into a working product on **Unity AI Gateway
+ Model Serving**. V2 is a real router and a real FinOps view, not just a slideshow:

- **The app is the gateway.** It exposes an OpenAI-compatible `POST /v1/chat/completions`
  proxy (`finops-auto`) that classifies each prompt, routes it to the cheapest
  sufficient model, and enforces app-level guardrails, rate limits, semantic cache,
  fallback, and a live budget.
- **Cost and savings come from real Unity Catalog system tables** (`system.ai_gateway.usage`,
  `system.serving`), priced with the published DBU rate card, read by the app service
  principal through a SQL warehouse. Coding-agent spend and gateway reliability are
  read from the same telemetry.
- **Governance writes are real** via on-behalf-of-user: guardrails, rate limits, and
  usage tracking are applied to real serving endpoints as the signed-in admin.

Everything is **config-driven**: nothing workspace-specific is hardcoded in the
backend or `app.yaml`. It also **degrades gracefully**: any piece you have not wired
up yet (warehouse, Lakebase, endpoints) falls back to a safe default instead of
failing, so the app always runs.

---

## Two ways it runs

| Mode | Set | What you get | Setup needed |
|---|---|---|---|
| **Live** (default) | `demo_mode=false` | Real Model Serving answers/tokens/latency, real judge, real system-table cost data | Endpoints + warehouse + grants (see [V2_SETUP.md](V2_SETUP.md)) |
| **Demo** | `demo_mode=true` | Synthesised numbers + placeholder answers, prices still the real rate card | Nothing. Runs on any workspace, offline |

Live mode is the shipped default. Anything not yet configured degrades to demo for
that feature only, so a first live deploy still runs end to end.

---

## Prerequisites

To deploy into a workspace you need:

- **Databricks CLI** >= 0.229.0 (`databricks --version`), authenticated to the target
  workspace: `databricks auth login --host <workspace-url> --profile <name>`. The
  optional durable cache (Autoscaling Lakebase) needs CLI **>= 0.285.0** for the
  `databricks postgres` commands.
- **Node.js** >= 18 and **npm** (to build the frontend into `dist/`). Node is needed
  only at build time; the deployed app is Python-only.
- **Python** >= 3.11 (only for running locally; the deployed app uses the Apps runtime,
  which pip-installs `requirements.txt` for you, no manual install in the workspace).
- Permission to **create a Databricks App** in the target workspace.
- For **live mode**, the Databricks features in [V2_SETUP.md](V2_SETUP.md): Model Serving
  endpoints, an embedding endpoint, a serverless SQL warehouse, and the system-table
  grants. The app self-checks all of these at `/api/setup/readiness`.

---

## Config-driven design (nothing hardcoded)

Every workspace-specific value is a **bundle variable** in `databricks.yml`, resolved
per **target**. The backend reads only environment variables; the bundle sets them via
the app `config.env` block, which overrides `app.yaml` at deploy time. So the committed
files stay generic and each target injects its own values.

| Variable | Env var | Default | Purpose |
|---|---|---|---|
| `demo_mode` | `FINOPS_DEMO_MODE` | `false` | Offline synthesised vs real endpoints |
| `judge_enabled` | `FINOPS_JUDGE_ENABLED` | `true` | LLM-as-judge column in Compare |
| `dbu_to_usd` | `FINOPS_DBU_TO_USD` | `0.07` | Your negotiated $/DBU (list rate default) |
| `data_source` | `FINOPS_DATA_SOURCE` | `system_tables` | Cost tab: real system tables vs demo |
| `embed_endpoint` | `FINOPS_EMBED_ENDPOINT` | `databricks-gte-large-en` | Semantic-cache embeddings |
| `warehouse_id` | `FINOPS_WAREHOUSE_ID` | *(blank)* | Serverless SQL warehouse the app SP uses |
| `lakebase_endpoint` / `lakebase_host` / `lakebase_db` | `LAKEBASE_*` | *(blank)* / `databricks_postgres` | Optional durable cache + semantic cache (Autoscaling Lakebase + pgvector) |
| `tools_catalog` / `tools_schema` | `FINOPS_TOOLS_*` | *(blank)* | Optional real agent-tool functions |

Blank workspace variables are safe: the cost tab falls back to demo, the semantic
cache falls back to in-process, the tools demo falls back to a sample set.

Two targets ship in `databricks.yml`:
- **`dev`** (default, the maintainer target) ships with blank values. The maintainer's
  real sandbox values + `dev` app-resource attachments live in a **gitignored**
  `databricks.dev.local.yml` (merged via `include`; see `databricks.dev.local.yml.example`),
  so nothing workspace-specific is committed. Without that file, `dev` degrades safely.
- **`prod`** is the customer target: **fill in its `variables` block** in `databricks.yml`
  (`warehouse_id`, `lakebase_endpoint`/`lakebase_host`/`lakebase_db`, `dbu_to_usd`,
  optional `tools_*`) or pass `--var`, then `bundle deploy -t prod`.

Also editable, no code changes:
- `config/models.yaml`: the model registry in three tiers (`frontier`, `large-oss`,
  `small-oss`), each with its FMAPI DBU rate card. Trim to the endpoints your workspace
  has. `/api/models/discover` cross-references this against your live endpoints and
  flags any that are missing or unpriced.
- `config/policy.yaml`: routing thresholds, budget ceilings, fallback, rate limits.

---

## Quickstart

### Run locally
```bash
git clone <this repo> && cd intelligent-ai-finops-v2
cp .env.example .env             # set DATABRICKS_CONFIG_PROFILE for live mode

# frontend
npm install
npm run build                    # produces ./dist

# backend (serves ./dist + /api)
uv venv .venv && . .venv/bin/activate
uv pip install -r requirements.txt
uvicorn backend.main:app --port 8000
# open http://localhost:8000
```
For hot-reload frontend dev: `npm run dev` (Vite on :5173, proxies `/api` to :8000).

### Deploy to your workspace (Asset Bundle, recommended)
```bash
npm install && npm run build     # dist must exist before deploy

# 1. put your workspace values in the `prod` target of databricks.yml
#    (warehouse_id, dbu_to_usd, and optionally lakebase_endpoint/host/db / tools_*)
# 2. deploy + run
databricks bundle deploy -t prod --profile <your-profile>
databricks bundle run  intelligent_ai_finops_v2 -t prod --profile <your-profile>
```
That is the whole deploy: `bundle deploy` uploads the built `dist/` (index.html and
assets together) plus the backend, and `bundle run` starts the app and installs the
Python dependencies from `requirements.txt`. The target workspace comes from `--profile`.
Then apply the grants in [V2_SETUP.md](V2_SETUP.md) and open `/api/setup/readiness` to
confirm every check is green.

### Deploy manually (without a bundle)
```bash
npm run build
databricks apps create intelligent-ai-finops-v2 --profile <profile>
databricks sync . /Workspace/Users/<you>/intelligent-ai-finops-v2 \
  --exclude node_modules --exclude src --exclude .venv --exclude package.json \
  --exclude package-lock.json --exclude "*.config.ts" --exclude tsconfig.json --profile <profile>
databricks workspace import-dir dist /Workspace/Users/<you>/intelligent-ai-finops-v2/dist --overwrite --profile <profile>
databricks apps deploy intelligent-ai-finops-v2 \
  --source-code-path /Workspace/Users/<you>/intelligent-ai-finops-v2 --profile <profile>
```
In the manual path, `app.yaml` supplies the env, so set your values there (the bundle
`config.env` only applies to bundle deploys).

---

## The tabs

1. **Compare models**: one prompt, up to three lanes, live streaming plus an LLM judge;
   the cheapest answer within a judge point of the best wins. Includes an example-question
   library across Simple / Medium / Complex.
2. **Smart routing**: pick the models you would route across and the governance to apply
   (rate limits, guardrails, complexity-based routing, budget easing). It routes to the
   cheapest model that clears the complexity bar, and as the budget fills that bar tightens.
   A User / Admin persona toggle locks the model set for end users.
3. **Cost & savings**: real spend from system tables, spend by model and tier, the routed
   vs frontier counterfactual (what routing avoided on real traffic), coding-agent spend by
   harness and developer, gateway reliability, chargeback by team, and a forward projection.
4. **Gateway API**: the live `POST /v1/chat/completions` proxy. Try a prompt (including
   `finops-auto`), see the routing receipt (served-by, cost, savings, complexity, guardrail
   / cache / fallback badges), the semantic-cache stats, a budget cap, and the deployment
   readiness panel.
5. **Why Databricks**: build-vs-inherit, with the real config and SQL artifacts.
6. **How it works**: the request flow end to end, one governed gateway to the cheapest
   sufficient model and back.

---

## Repo structure

```
├── app.yaml                 Apps entrypoint + generic env defaults (manual deploy)
├── databricks.yml           Asset Bundle: variables + config.env + dev/prod targets
├── requirements.txt         backend deps (pinned, permissive licenses)
├── .env.example             local-dev env
├── config/                  models.yaml (registry + DBU rate card) · policy.yaml
├── backend/                 FastAPI, serves ./dist + /api
│   ├── main.py              routes (/api/*, /v1/chat/completions)
│   ├── appconfig.py         config loader + env flags
│   ├── proxy.py             the router: classify → route → govern → serve
│   ├── gateway.py           routing policy, complexity, budget ceiling
│   ├── models.py            registry (DBU rate card → $) + FMAPI invocation
│   ├── datasource.py        real system-table cost overview
│   ├── costcache.py         cost overview cache (memory → Lakebase → compute)
│   ├── semcache.py          semantic cache (embeddings + cosine; L1 in-process, L2 pgvector on Lakebase)
│   ├── lakebase.py          Autoscaling Lakebase pool (SP OAuth) + durable-store helpers
│   ├── guardrails.py        app-layer PII / keyword guardrails
│   ├── codingagents.py      coding-agent spend from user_agent
│   ├── reliability.py       gateway fallback / error telemetry
│   ├── setup.py             /api/setup/readiness + endpoint discovery
│   ├── evalset.py           bring-your-own eval set (routed vs frontier, judged)
│   ├── compare.py           Compare streaming lanes
│   └── judge.py             LLM-as-judge (+ best-effort MLflow)
├── src/                     Vite + React + TS frontend
└── dist/                    built frontend (generated by npm run build)
```

---

## Notes / scope

- **Config-driven and portable.** The only "which workspace" input is the CLI profile.
  All values are bundle variables (or `app.yaml` env for the manual path).
- **Degrades gracefully.** Missing warehouse, Lakebase, endpoint, or embedding never hard
  fails; the affected feature falls back and `/api/setup/readiness` shows what to fix.
- **Honest pricing.** Cost is real usage times the published DBU rate card times your
  `$/DBU`. Endpoints without a published rate are flagged, never given a fabricated price.
- **Out of scope by design:** end-user auth beyond the Databricks Apps identity, and
  contract-accurate billed dollars (use `system.billing.usage` join if you need billed $;
  the query shape is unchanged).
