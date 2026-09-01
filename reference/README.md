# Run the workshop without the app

The workshop app is a convenience, not a dependency. Everything it does, you can do with the
Databricks CLI, a SQL editor, and the plain queries in
[`workshop_app/queries/`](../workshop_app/queries/). This folder is the **non-app route**: the
same choice / cost / control walkthrough, run by hand.

Use it when you can't (or don't want to) deploy the app — a locked-down workspace, a quick
check, or simply to see exactly what the app runs before you trust it in front of a customer.

## What the app actually does (transparency)

We reviewed the app's server code so you can vouch for it. In short:

- **Everything targets your own workspace and account.** Every call goes through the Databricks
  SDK to your workspace API, the SQL warehouse you configured, the MCP gateway on your own
  workspace host, or a file on your own Unity Catalog volume. There is **no third-party
  telemetry and no external network call** — the only non-workspace URLs in the code are links
  to your account console (shown in the UI, never called).
- **It reads far more than it writes.** Most steps are read-only (list endpoints, read grants
  and ACLs, query system tables). The only writes it can make are: your workshop progress JSON
  on the UC volume; a governed endpoint *only if you run that step* (it will not create
  endpoints unattended — it reports a to-do instead); a keyword-blocklist / MCP policy **SQL
  function**; and project **tags** on a service. Guardrails and rate limits are set by **you**
  in the AI Gateway UI — the app never changes throughput or guardrails on a live endpoint.
- **It never reads secret values.** The provider-secret check only confirms an endpoint
  references `{{secrets/...}}`; the audit scan looks for secret-*shaped* strings and reports a
  count — it does not store or transmit them.
- **The outcomes export carries no account or Salesforce identifier.** It is a per-step status
  list, generated on demand.

The pieces that live in Python rather than plain SQL — the routing classifier, the
guardrail/response classification, the secret regex, and the MCP JSON-RPC client — are small and
reproduced inline in [`core_walkthrough.py`](core_walkthrough.py).

## Prerequisites

- The Databricks CLI, logged in: `databricks auth login --host https://<workspace>...`
- A running SQL warehouse (get its id with `databricks warehouses list`).
- Unity AI Gateway enabled on the account (see [`PREREQUISITES`](../workshop_app/docs/PREREQUISITES.md)).
- For the telemetry steps: the two `system` grants (`system.ai_gateway`, `system.access`).

Run a query file against your warehouse via the Statement Execution API (the CLI has no
`sql query` command):

```bash
databricks api post /api/2.0/sql/statements --json "$(jq -n \
  --arg w "<warehouse-id>" \
  --arg s "$(sed 's/\${days}/30/' workshop_app/queries/endpoint_inventory_v1_v3.sql)" \
  '{warehouse_id:$w, statement:$s, wait_timeout:"50s"}')"
```

…or just paste the file into the SQL editor (replace each `${...}` placeholder with a literal —
each file's header says what goes where). For the full set of terminal commands — including the
REST-only steps (governed endpoint, ACLs, model services, MCP JSON-RPC) — see
[`cli.md`](cli.md).

## Core walkthrough — the 14 steps, by hand

| # | Step | Run it without the app |
|---|------|------------------------|
| **Choice** ||
| 1 | Connect | `databricks current-user me` — confirms auth + workspace. |
| 2 | Inventory endpoints | `databricks serving-endpoints list`. |
| 2b | **v1 vs v3 split** | Run [`queries/endpoint_inventory_v1_v3.sql`](../workshop_app/queries/endpoint_inventory_v1_v3.sql) (`${days}`→30). Rows tagged `v1 (legacy endpoint)` are the migration backlog. |
| 3 | Model services | `databricks api get /api/2.1/unity-catalog/model-services`. Client contract: base URL `/serving-endpoints`→`/ai-gateway/mlflow/v1`, model `<name>`→`<catalog>.<schema>.<service>`. |
| **Cost** ||
| 4 | Models & prices | Read `cost.routing` in [`workshop.yaml`](../workshop_app/config/workshop.yaml). |
| 5 | Routing compare | Call each model's endpoint on the gateway chat path and compare tokens/cost — see `core_walkthrough.py`. |
| 6 | Spend by model | [`queries/spend_by_model.sql`](../workshop_app/queries/spend_by_model.sql). |
| 7 | Rate limits | Set in the AI Gateway UI on the endpoint; read back with `databricks serving-endpoints get <name>`. |
| 8 | Budgets | Create in the account console. Team leads / non-admins can watch their own spend with [`queries/budget_status.sql`](../workshop_app/queries/budget_status.sql). |
| 9 | Usage & tags | [`queries/usage_by_project.sql`](../workshop_app/queries/usage_by_project.sql) (`${project}`→`'your_project'`). Splits request-tagged (attribution) vs endpoint-tagged (budget-safe). |
| **Control** ||
| 10 | Governed endpoint | Create via UI, or `databricks api put /api/2.0/serving-endpoints/<name>/config` with a fallback + inference table. |
| 11 | Endpoint ACL | `databricks api get /api/2.0/permissions/serving-endpoints/<endpoint-id>`. Watch for a broad group with `CAN_QUERY`, and keep `CAN_MANAGE` to admins. |
| 12 | Guardrails | Configure PII/safety in the AI Gateway UI; the keyword blocklist is [`queries/keyword_blocklist_policy.sql`](../workshop_app/queries/keyword_blocklist_policy.sql) — create it, attach it in the UI, and prove it fired with [`queries/guardrail_activity.sql`](../workshop_app/queries/guardrail_activity.sql) (`${table}`→your inference table). A blocked prompt is the pass. |
| 13 | MCP policy | Create [`queries/mcp_service_policy.sql`](../workshop_app/queries/mcp_service_policy.sql) (ALLOW/DENY; `to_variant_object(...)`, cast VARIANT paths: `event:context.tool.name::STRING`), attach it in the UI, test via JSON-RPC. |
| 14 | Audit & secrets | [`queries/audit_scan.sql`](../workshop_app/queries/audit_scan.sql), then eyeball the args for `sk-`, `AKIA`, `ghp_`. |

For the deeper topics (MCP, agent registry, coding agents, external providers, policies &
guardrails, skills) the [`accelerators/`](../accelerators/) folder is *already* a non-app route:
each is a runnable Databricks notebook plus its own `reference_queries.py`.

`core_walkthrough.py` in this folder runs steps 1–14 end to end as one notebook, reading the
same `queries/*.sql` files so there is a single source of truth for the SQL.
