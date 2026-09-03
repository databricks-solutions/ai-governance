# Intelligent AI FinOps

A deployable Databricks App that shows a **routing layer** sending each query to
the cheapest model that still clears a quality bar — and that every piece of
doing so (governance, cost attribution, guardrails) already exists on Databricks
via **Unity AI Gateway + Model Serving**.

Built for the field: a Solutions Architect can run it locally or deploy it into
any customer workspace in minutes. Demo mode works with **zero setup** (no
serving endpoints, no network) so it survives venue wifi.

---

## Prerequisites

To **deploy** into a workspace you need:

- **Databricks CLI** ≥ 0.229.0 (`databricks --version`) authenticated to the
  target workspace: `databricks auth login --host <workspace-url> --profile <name>`.
- **Node.js** ≥ 18 and **npm** (to build the frontend → `dist/`).
- **Python** ≥ 3.11 (only for running/testing locally; the deployed app uses the
  Apps runtime).
- Permission to **create a Databricks App** in the target workspace.
- **For live mode only** (`FINOPS_DEMO_MODE=false`): the serving-endpoint IDs in
  `config/models.yaml` must actually exist and be queryable in the target
  workspace, and the app's service principal must have **CAN QUERY** on them.
  If they don't exist, either deploy in demo mode or trim `config/models.yaml`
  to the endpoints that workspace has (see *Configure before you deploy*).

Nothing else is provisioned: there is **no cluster, no SQL warehouse, no
Lakebase, and no system-table/catalog dependency**. The FastAPI backend runs as
the Databricks App container itself, and all "storage" is the two bundled YAML
files in `config/`.

## Configure before you deploy

Everything portable is data or env — you never edit code to move workspaces.
Review these before `bundle deploy`:

| What | Where | Change it when… |
|---|---|---|
| **Target workspace** | `--profile <name>` on the deploy command | always — this is the only "which workspace" input |
| **`FINOPS_DEMO_MODE`** | `app.yaml` env | `false` (default) hits real endpoints; set `true` for a zero-setup / offline demo |
| **`FINOPS_DBU_TO_USD`** | `app.yaml` env | set to the customer's **negotiated $/DBU** (default `0.07` = published list rate) so shown prices match their contract |
| **`FINOPS_JUDGE_ENABLED`** | `app.yaml` env | `false` to hide the LLM-as-judge column |
| **Which models appear** | `config/models.yaml` | trim/extend to the endpoints the target workspace actually has; each carries its FMAPI **DBU rate card** (input/output per 1M tokens) |
| **Routing thresholds & budget** | `config/policy.yaml` | tune complexity cut-offs (`small_max`/`large_max`) and budget ceilings (`downgrade_at_pct`/`open_only_at_pct`) |

> **Live vs demo trade-off:** `app.yaml` ships `FINOPS_DEMO_MODE=false` so a
> field SA gets real answers/tokens/latency out of the box. That requires the
> `config/models.yaml` endpoints to exist in the target workspace. Deploying to
> a bare workspace? Set `FINOPS_DEMO_MODE=true` and it runs anywhere with zero
> setup.

---

## Quickstart

### Run locally
```bash
git clone <this repo> && cd intelligent-ai-finops
cp .env.example .env            # set DATABRICKS_CONFIG_PROFILE for live mode (optional)

# frontend
npm install
npm run build                   # produces ./dist

# backend (serves ./dist + /api)
uv venv .venv && . .venv/bin/activate
uv pip install -r requirements.txt
uvicorn backend.main:app --port 8000
# open http://localhost:8000
```
For hot-reload frontend dev: `npm run dev` (Vite :5173, proxies `/api` → :8000).

### Deploy to a customer workspace (Asset Bundle — recommended)
```bash
npm install && npm run build     # dist must exist before deploy
databricks bundle deploy -t dev --profile <customer-profile>
databricks bundle run intelligent_ai_finops -t dev --profile <customer-profile>
```
Nothing workspace-specific is hardcoded — the target host comes from `--profile`
(or `DATABRICKS_HOST`), so the same bundle deploys anywhere. The bundle excludes
`node_modules`/`src`/build config and force-includes `dist`, so the Apps builder
never runs `npm install`.

### Deploy manually (without a bundle)
```bash
npm run build
databricks apps create intelligent-ai-finops --profile <profile>
databricks sync . /Workspace/Users/<you>/intelligent-ai-finops \
  --exclude node_modules --exclude src --exclude .venv --exclude package.json \
  --exclude package-lock.json --exclude "*.config.ts" --exclude tsconfig.json --profile <profile>
databricks workspace import-dir dist /Workspace/Users/<you>/intelligent-ai-finops/dist --overwrite --profile <profile>
databricks apps deploy intelligent-ai-finops \
  --source-code-path /Workspace/Users/<you>/intelligent-ai-finops --profile <profile>
```

---

## The tabs

1. **Compare models** — one prompt, up to three lanes, live streaming + LLM-judge; the cheapest answer within a judge point of the best wins. Includes a rich example-question library (Simple/Medium/Complex across domains).
2. **Context routing** — the **Unity Gateway box**: drag a question in (or type your own), pick the 2–3 models you'd let it route across, and tick the governance features (rate limits, guardrails, **budgets routing**, **complexity routing**, inference tables). It routes to the cheapest model that clears the complexity bar — and as the budget fills, that bar tightens toward cheaper models. A User/Admin persona toggle locks the model set + complexity for end users. Shows the model, the cost, the answer, and how it routed.
3. **Cost & savings** — the FinOps view: overall spend, spend by model/tier, the % of traffic served by a smaller model instead of a frontier one, an observability panel (traces, latency, guardrail activity, coding-agent + MCP-server signals, daily trends over a time window), and a forward cost projection with the routing savings.
4. **Why Databricks** — build-vs-inherit, with the real config/SQL artifacts.
5. **How it works** — the request flow end to end (one governed Unity Gateway endpoint → cheapest sufficient model → response).

> This is a **demo/enablement tool** for the FMAPI + Unity AI Gateway routing story — showing customers context- and budget-based routing and which models to pick when. **Prices are real** (the official FMAPI DBU rate card × your $/DBU); it does not read billing/system tables — budget is a presenter-controlled lever, not billed spend.

---

## Configuration (nothing hardcoded)

- `config/models.yaml` — curated model registry in **three buckets**: `frontier`, `large-oss`, `small-oss`. Each entry has an endpoint id, tier, and the official FMAPI **DBU rate card** (`dbu_in_per_1m` / `dbu_out_per_1m`); the app converts to dollars with `FINOPS_DBU_TO_USD`. Only endpoints with a published rate are listed (no illustrative prices). Edit this to change what shows in the dropdowns and how tiers map.
- `config/policy.yaml` — routing thresholds, budget cap, fallback, rate limits.
- `.env` / app env (see `.env.example`):
  - `FINOPS_DEMO_MODE` — synthesize offline vs. call real endpoints. Local default `true`; `app.yaml` ships `false`.
  - `FINOPS_DBU_TO_USD` (default `0.07`) — $ per DBU used to turn the DBU rate card into prices; set to the customer's negotiated rate.
  - `FINOPS_JUDGE_ENABLED`, `DATABRICKS_CONFIG_PROFILE` (local only).

**Demo vs live:** demo mode authors realistic cost/latency/judge numbers server-side (no network) so it runs anywhere with zero setup — but **prices are always the real DBU rate card**, only the token counts / latency / judge scores are synthesised. Live mode (`FINOPS_DEMO_MODE=false`) calls real Model Serving endpoints and computes cost from actual token usage. Either way the frontend never computes cost — every number comes from `/api`. This tool does **not** read billing/system tables; it's for telling the routing story, not FinOps reporting.

---

## Repo structure

```
├── app.yaml                 Databricks Apps entrypoint (uvicorn)
├── databricks.yml           Asset Bundle (bundle deploy)
├── requirements.txt         backend deps
├── .env.example
├── config/                  models.yaml · policy.yaml   (edit these, not code)
├── backend/                 FastAPI — serves ./dist + /api
│   ├── main.py              routes
│   ├── appconfig.py         config loader + env flags
│   ├── models.py            registry (DBU rate card → $) + FMAPI invocation
│   ├── gateway.py           Tab 2: route over the customer's selected models (+ budget easing)
│   ├── routing.py           classify → policy helpers
│   ├── compare.py           Tab 1 streaming lanes
│   └── judge.py             LLM-as-judge (+ MLflow)
├── src/                     Vite + React + TS frontend
│   ├── tabs/                Compare · Pipeline (Gateway box) · WhyDatabricks · Architecture
│   ├── components/          primitives · StageConfigPanel · QuestionLibrary
│   ├── data/                question library
│   └── api/                 client + types
└── dist/                    built frontend (generated by `npm run build`)
```

---

## Notes / scope

- **This is a demo/enablement tool**, not a FinOps product. Gateway feature panels (rate limits, inference tables, traces, metrics, guardrails, budgets) show illustrative content that mirrors what Unity AI Gateway does — they don't query system tables. Budget is a presenter-controlled lever that tightens routing, not real billed spend.
- **Out of scope by design:** reading billing/system tables, auth, multi-user persistence, real per-tenant budget enforcement.
