# Getting started

This guide takes you from zero to a governed endpoint with the five core labs running.

## Prerequisites

- A Databricks workspace on a tier with **Model Serving** and **Foundation Model APIs** (pay-per-token) available.
- The **Databricks CLI** ≥ 0.230 ([install](https://docs.databricks.com/dev-tools/cli/install.html)).
- Workspace permissions to:
  - create/update Model Serving endpoints and their AI Gateway configuration,
  - create a Unity Catalog schema in your target catalog,
  - read the `system` catalog (system tables) for the FinOps lab.
- Python ≥ 3.10 locally if you want to lint/run tooling (`uv sync`).

## 1. Authenticate

Use a CLI profile or environment variables:

```bash
export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
export DATABRICKS_TOKEN=<personal-access-token>
# or: databricks auth login --host https://<your-workspace>.cloud.databricks.com
```

## 2. Configure the bundle (optional)

Defaults live in `databricks.yml` under `variables`:

| variable | default | purpose |
|----------|---------|---------|
| `catalog` | `main` | catalog for governance artifacts |
| `schema` | `ai_governance` | schema for inference/usage artifacts |
| `gateway_endpoint` | `ai-governance-gateway` | the governed endpoint name |
| `base_model` | `databricks-meta-llama-3-3-70b-instruct` | model behind the endpoint |

Override at deploy time, e.g.:

```bash
databricks bundle deploy -t dev --var="catalog=my_catalog" --var="schema=ai_gov"
```

## 3. Deploy

```bash
scripts/deploy.sh validate   # databricks bundle validate -t dev
scripts/deploy.sh deploy     # creates schema + endpoint (usage tracking + payload logging on) + job
```

The endpoint comes up with **usage tracking** and **payload (inference table) logging**
already enabled. Each lab then adds one more control.

## 4. Run the labs

**Interactively:** open `labs/models/01-rate-limiting/notebook.py` in the workspace and
run top to bottom. The shared widgets (`endpoint_name`, `catalog`, `schema`) default to
the bundle values; change them if you deployed with overrides.

**As a job:** run all five core labs end to end:

```bash
scripts/deploy.sh run        # databricks bundle run run_core_labs -t dev
```

Recommended order: 01 → 02 → 04 → 05 → 03 (run the FinOps lab last so usage/cost data exists).

## 5. Tear down

```bash
scripts/deploy.sh destroy
```

Individual Gateway controls can be cleared per the "Teardown" cell at the bottom of each
built notebook.

## Troubleshooting

- **System tables empty in Lab 03** — usage/billing rows can lag several minutes; re-run
  the query cells later. Confirm system tables are enabled for your workspace.
- **`429` outside Lab 01** — a previous run left tight rate limits; re-run Lab 01's final
  cell or `put_ai_gateway({"rate_limits": []})`.
- **Endpoint stuck updating** — config changes (Labs 04/05) reconcile asynchronously; the
  notebooks already wait, but a busy workspace can take several minutes.
