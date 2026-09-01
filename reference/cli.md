# CLI cheat-sheet — the workshop from a terminal

Every core step as a copy-paste command, using the [Databricks CLI](https://docs.databricks.com/dev-tools/cli/)
plus `jq` and `curl`. This is the REST/SDK companion to the plain SQL in
[`../workshop_app/queries/`](../workshop_app/queries) — together they are the non-app route.

Everything below hits **your own** workspace and account. Nothing calls out anywhere else.

## Setup

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com   # once
export DATABRICKS_CONFIG_PROFILE=<profile>        # or pass -p <profile> per command
export WAREHOUSE_ID=$(databricks warehouses list -o json | jq -r '.[0].id')  # or paste one
export HOST=$(databricks auth env | jq -r '.env.DATABRICKS_HOST')
export TOKEN=$(databricks auth token | jq -r '.access_token')
```

A helper to run any `queries/*.sql` file on your warehouse (the CLI has **no** `sql query`
command — SQL goes through the Statement Execution API):

```bash
runsql() {  # runsql <file.sql> [sed-substitution]
  local stmt; stmt=$(sed "${2:-s/^$//}" "$1")
  databricks api post /api/2.0/sql/statements \
    --json "$(jq -n --arg w "$WAREHOUSE_ID" --arg s "$stmt" \
      '{warehouse_id:$w, statement:$s, wait_timeout:"50s"}')" \
    | jq '.result.data_array'
}
```

## Choice

```bash
# 1 — Connect
databricks current-user me

# 2 — Inventory endpoints
databricks serving-endpoints list -o json | jq -r '.[].name'

# 2b — v1 (legacy) vs v3 (model service) split.  v1 rows are the killswitch backlog.
runsql workshop_app/queries/endpoint_inventory_v1_v3.sql 's/${days}/30/'

# 3 — Model services (the governed object)
databricks api get /api/2.1/unity-catalog/model-services \
  | jq -r '.model_services[].name'
# Client contract: base URL /serving-endpoints -> /ai-gateway/mlflow/v1,
#                  model <endpoint-name>      -> <catalog>.<schema>.<service>
```

## Cost

```bash
# 5 — Routing compare: send one prompt per tier, compare tokens.
for M in databricks-meta-llama-3-1-8b-instruct \
         databricks-meta-llama-3-3-70b-instruct \
         databricks-claude-sonnet-4-5; do
  echo -n "$M  "
  curl -s "$HOST/ai-gateway/mlflow/v1/chat/completions" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H 'Databricks-Ai-Gateway-Request-Tags: {"project":"ai_governance_workshop"}' \
    -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarize LLM cost drivers.\"}]}" \
    | jq -c '.usage'
done
# The request-tag header is why this uses curl, not the SDK's query() — that hits the legacy
# path and can't set headers. Request tags = attribution only; server-side tags = budget-safe.

# 6 — Spend by model (30d)
runsql workshop_app/queries/spend_by_model.sql

# 8 — Budget basis (a non-admin can run this for their own rows)
runsql workshop_app/queries/budget_status.sql

# 9 — Usage attributed to a project tag (request- vs endpoint-tagged)
runsql workshop_app/queries/usage_by_project.sql "s/\${project}/'ai_governance_workshop'/g"

# 7 — Rate limits: set in the AI Gateway UI, then read back
databricks serving-endpoints get <governed-endpoint> -o json | jq '.ai_gateway.rate_limits'
```

Budgets are created in the **account console** (alerts GA, hard caps rolling out).

## Control

```bash
# 10 — Governed endpoint: create/patch config (fallback + inference table). Do this deliberately.
databricks api put /api/2.0/serving-endpoints/<name>/config --json @endpoint-config.json

# 11 — Who can call it (ACL). Note: takes the endpoint ID, not its name.
EP_ID=$(databricks serving-endpoints get <name> -o json | jq -r '.id')
databricks api get /api/2.0/permissions/serving-endpoints/$EP_ID \
  | jq '.access_control_list[] | {principal: (.group_name // .user_name // .service_principal_name), levels: [.all_permissions[].permission_level]}'
# Watch for a broad group with CAN_QUERY (open to everyone); keep CAN_MANAGE to admins.

# 12 — Guardrails: configure PII/safety in the UI. Keyword blocklist is a UC function:
runsql workshop_app/queries/keyword_blocklist_policy.sql \
  "s#\${function_fqn}#<cat>.<schema>.keyword_blocklist_policy#; s/\${keywords}/'social security number', 'credit card number'/"
# Prove it fired (after attaching + sending a blocked prompt):
runsql workshop_app/queries/guardrail_activity.sql "s#\${table}#<cat>.<schema>.workshop_governed_payload#"

# 13 — MCP service policy (ALLOW reads / DENY named write tools), then attach in the UI:
runsql workshop_app/queries/mcp_service_policy.sql \
  "s#\${function_fqn}#<cat>.<schema>.mcp_read_only_policy#; s/\${deny_tools}/'create_issue', 'push_files'/; s/\${reason}/'Blocked by workshop policy.'/"

# 14 — Audit & secret-leak scan
runsql workshop_app/queries/audit_scan.sql
```

## Access — "what can this identity reach?"

The app answers this with the effective-permissions API (it folds in inherited grants — more
accurate than `SHOW GRANTS`):

```bash
databricks api get "/api/2.1/unity-catalog/effective-permissions/schema/system.ai?principal=<sp-or-user>" \
  | jq '.privilege_assignments'
```

## MCP (accelerator)

```bash
# List MCP Services (the securables you can attach a policy to)
databricks api get /api/2.1/unity-catalog/mcp-services | jq -r '.mcp_services[].name'

# tools/list over JSON-RPC (errors ride inside HTTP 200 — check for .result, not the status)
curl -s "$HOST/ai-gateway/mcp-services/system.ai.github" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2025-11-25" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | sed 's/^data: //' | jq '.result.tools[].name'
```

The other accelerators ship their own runnable versions in each folder's
`reference_queries.py`.
