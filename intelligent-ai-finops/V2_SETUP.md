# V2 setup: make it deployable in your Databricks workspace

This is the checklist to run the app in **live mode** against your own workspace.
The app degrades gracefully, so you can deploy first and light up each feature as you
grant it. After deploying, open **`/api/setup/readiness`** in the app: it reports every
item below as green or red with the exact fix.

---

## 1. Features to enable in your Databricks instance

| # | Feature / service | Required for | Notes |
|---|---|---|---|
| 1 | **Databricks Apps** | Everything | The app runs as an Apps container. |
| 2 | **Model Serving / Foundation Model APIs** (pay-per-token) | Live Compare, Smart routing, the OpenAI-compatible proxy (`/v1/chat/completions`) | The endpoints in `config/models.yaml` must exist in your **region**; the app SP needs `CAN_QUERY`. |
| 3 | **Embedding endpoint** (`databricks-gte-large-en`) | Semantic cache | Present by default in most workspaces; SP needs `CAN_QUERY`. Override with `embed_endpoint`. |
| 4 | **Serverless SQL warehouse** | Cost & savings, coding-agents, reliability, tools tabs | Any small serverless warehouse; SP needs `CAN USE`. Set `warehouse_id`. |
| 5 | **Unity Catalog system tables** | Real cost / usage data | Grant SP `SELECT` on `system.ai_gateway` and `system.serving` (and `system.billing` for billed-$). Metastore-admin action. |
| 6 | **AI Gateway usage tracking** on your endpoints | Cost / coding-agent / reliability data | Without it, `system.ai_gateway.usage` stays empty even with grants. Only traffic after enabling is captured. |
| 7 | **On-behalf-of-user scopes + admin consent** | Governance writes (guardrails, rate limits, usage) | Scopes `model-serving`, `sql` are declared in `databricks.yml`. The admin must consent once in-browser at first login. |
| 8 | **Autoscaling Lakebase (Postgres + pgvector)** | Optional durable cache + semantic cache | Blank config falls back to in-process cache. Persists the cost cache + semantic cache across restarts/replicas. Set `lakebase_endpoint` / `lakebase_host` / `lakebase_db` (see section below). |
| 9 | **UC catalog + schema of agent-tool functions** | Optional tools-compression demo | Blank falls back to a sample set. Set `tools_catalog` / `tools_schema`. |

Items 1 to 7 cover the full live story. 8 and 9 are optional.

---

## 2. Find the app service principal

After the first deploy:

```bash
databricks apps get intelligent-ai-finops-v2 --profile <profile> \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('service_principal_client_id'))"
```

Use that client id as `<APP_SP>` below.

---

## 3. Grants

> **Recommended: attach resources instead of granting by hand.** The bundle can
> attach the warehouse and the embedding endpoint as native app resources, which
> auto-grants the app SP `CAN_USE` / `CAN_QUERY` at deploy time. Uncomment the
> `resources:` block in the `prod` target of `databricks.yml` (set your warehouse
> id) and those two grants below are handled for you. Attach only resources that
> already exist; a blank or missing resource fails the deploy. The `dev` target
> already uses this. System-table grants (metastore-level) still run as SQL.



### System tables (metastore admin)
```sql
GRANT USE SCHEMA ON SCHEMA system.ai_gateway TO `<APP_SP>`;
GRANT SELECT     ON SCHEMA system.ai_gateway TO `<APP_SP>`;
GRANT USE SCHEMA ON SCHEMA system.serving    TO `<APP_SP>`;
GRANT SELECT     ON SCHEMA system.serving    TO `<APP_SP>`;
-- only if you want billed-$ instead of rate-card $:
GRANT USE SCHEMA ON SCHEMA system.billing    TO `<APP_SP>`;
GRANT SELECT     ON SCHEMA system.billing    TO `<APP_SP>`;
```

### Warehouse (workspace admin or warehouse owner)
Grant the app SP **CAN USE** on the warehouse referenced by `warehouse_id`
(SQL Warehouses, select the warehouse, Permissions, add the SP as "Can use").

### Serving endpoints (endpoint owner or admin)
Grant the app SP **CAN_QUERY** on each pay-per-token endpoint you route to, and on the
embedding endpoint. For the **governance write** controls (guardrails / rate limits /
usage), the writes execute as the signed-in admin via on-behalf-of-user, so the admin
just needs to consent to the `model-serving` scope at first login. (The app SP itself
cannot be granted CAN_MANAGE on system-managed endpoints.)

### Lakebase durable cache + semantic cache (optional, Autoscaling tier)

This persists the cost-overview cache **and** the semantic cache (pgvector) so hits
survive page reloads, app restarts, and replicas, and the saved-$ is real/cumulative.
Blank config falls back to the in-process cache automatically. Uses the **Autoscaling**
Lakebase tier (`databricks postgres`), not the legacy provisioned tier.

**1. Create an autoscaling project (owns a `production` branch + `primary` endpoint):**
```bash
databricks postgres create-project intelligent-ai-finops \
  --json '{"spec": {"display_name": "Intelligent AI FinOps"}}' -p <profile>
# host: databricks postgres list-endpoints projects/intelligent-ai-finops/branches/production -p <profile> -o json | jq -r '.[0].status.hosts.host'
```

**2. Federate the app service principal as a Postgres role** (this is what lets the
SP's OAuth token authenticate; a plain `CREATE ROLE` does NOT work on autoscaling):
```bash
databricks postgres create-role projects/intelligent-ai-finops/branches/production \
  --role-id finops-app-sp \
  --json '{"spec": {"identity_type": "SERVICE_PRINCIPAL", "postgres_role": "<APP_SP>", "auth_method": "LAKEBASE_OAUTH_V1"}}' -p <profile>
```

**3. Enable pgvector + create the schema/tables, then grant the SP** (connect to the
`databricks_postgres` DB as the instance owner; the semcache embedding dim matches
`databricks-gte-large-en` = 1024):
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS finops;
CREATE TABLE IF NOT EXISTS finops.cache    (key text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS finops.semcache (id bigserial PRIMARY KEY, prompt text NOT NULL, salient text NOT NULL,
                                            embedding vector(1024) NOT NULL, response jsonb NOT NULL, meta jsonb NOT NULL, ts timestamptz NOT NULL DEFAULT now());
CREATE INDEX  IF NOT EXISTS semcache_emb_hnsw ON finops.semcache USING hnsw (embedding vector_cosine_ops);
GRANT USAGE ON SCHEMA finops TO "<APP_SP>";
GRANT SELECT, INSERT, UPDATE, DELETE ON finops.cache, finops.semcache TO "<APP_SP>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA finops TO "<APP_SP>";
```

**4. Point the app at it** by setting the bundle vars (`dev`/`prod` target):
`lakebase_endpoint` = `projects/intelligent-ai-finops/branches/production/endpoints/primary`,
`lakebase_host` = the endpoint host from step 1, `lakebase_db` = `databricks_postgres`.
Autoscaling federates the SP via the role in step 2, so **no `database` app-resource
attachment is needed** (that is the provisioned-tier mechanism). Verify with
`/api/gateway/cache/stats` → `"backend":"lakebase-pgvector"` means the SP connected.

---

## 4. Point the registry at your endpoints

`config/models.yaml` is a curated registry with the FMAPI DBU rate card per model. In
your workspace or region some may not exist. After deploy, call:

```
GET /api/models/discover
```

It returns `present` (registry models live here, routable), `missing` (in the registry
but not deployed), and `extra` (live endpoints not in the registry, unpriced, flagged
never priced). Trim `config/models.yaml` to your `present` set, and add any `extra`
you want to route to together with its published DBU rate.

---

## 5. Verify

Open the deployed app and hit:

```
GET /api/setup/readiness
```

Every non-optional check should be green:
warehouse configured, system tables readable, endpoints discovered, embedding reachable.
Lakebase is optional. If anything is red, the response carries the exact fix.

If system-table grants are missing, `/api/cost/overview` returns `{"source":"demo", ...}`
and the Cost tab shows synthesised data. The app never hard-fails.
