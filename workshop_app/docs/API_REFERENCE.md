# API reference — every call the workshop makes

One row per API the workshop touches, with the **exact HTTP method and path** and which step
uses it. Cite this when a customer asks "what is the app actually doing to my workspace?"

**On links.** The Databricks API reference is a JavaScript-rendered single-page app: it
returns HTTP 200 for *every* URL under `/api/workspace/`, including
`/api/workspace/totallyfakegroup/nope`. Deep links therefore cannot be verified from a
script, and a 404 in a customer-facing app is worse than no link. So this file cites the one
URL confirmed to exist — the AI Gateway group index — and gives exact paths you can search
for within it:

> **https://docs.databricks.com/api/workspace/aigateway**

Navigate to the operation by name in the left-hand nav. Every path below was verified by
calling it live against a workspace (`fevm-shm-skunkworks`, 2026-08-06), which is a stronger
guarantee than a doc link: the response shapes in `server/` are what the API actually
returned, not what a doc implied.

---

## 1. Unity AI Gateway — the governed objects

| Operation | Method + path | Used by | Verified |
|---|---|---|---|
| List MCP services | `GET /api/2.1/unity-catalog/mcp-services` | `mcp_inventory`, `mcp_policy_target` | ✅ returned 6 `MCP_SERVICE` securables |
| MCP service permissions | `GET /api/2.1/unity-catalog/permissions/mcp_service/{name}` | `mcp_grants` | ✅ showed `EXECUTE` → `account users` |
| List model services | `GET /api/2.1/unity-catalog/model-services` | `model_services` | ✅ returned 24 `MODEL_SERVICE` securables |
| List model provider services | `GET /api/2.1/unity-catalog/model-provider-services` | — (documented for the External Providers accelerator) | ✅ responded; 0 registered |

The securable type in the permissions path is `mcp_service` (and `model_service`) — lowercase,
singular. Reported `name` values arrive prefixed, e.g. `mcp-services/system.ai.github`, so
strip the prefix before use.

## 2. MCP runtime — JSON-RPC, not REST

These are **not** REST operations and are not in the API reference. They speak JSON-RPC 2.0
over Streamable HTTP.

| Purpose | Path | Used by |
|---|---|---|
| MCP Service invocation | `POST /ai-gateway/mcp-services/{catalog}.{schema}.{name}` | `mcp_service_tools`, `mcp_obo` |
| Managed UC-native endpoint | `POST /api/2.0/mcp/functions/{catalog}/{schema}` | `mcp_managed_tools` |

Methods used: `initialize`, `tools/list`, `tools/call`. Three implementation details, all
learned the hard way (see `server/mcp.py`):

- **JSON-RPC errors ride inside HTTP 200.** Check for a `result` key; never trust the status
  code alone.
- `MCP-Protocol-Version` is required on every request after `initialize`.
- Responses may be SSE, so `Accept` must include `text/event-stream` and the body may need
  unwrapping from `data:` lines.

Other managed families (same shape, different scope): `/api/2.0/mcp/genie/{space_id}`,
`/api/2.0/mcp/sql`, `/api/2.0/mcp/ai-search/{catalog}/{schema}/{index}`.

## 3. Model invocation — the two contracts

| Contract | Method + path | Model selector | Used by |
|---|---|---|---|
| **Unity AI Gateway** | `POST /ai-gateway/mlflow/v1/chat/completions` | service FQN, e.g. `system.ai.gpt-oss-120b` | `model_services` (documents it) |
| Legacy Model Serving | `POST /api/2.0/serving-endpoints/{name}/invocations` | endpoint name | routing steps, via the SDK |

Both were verified to return **200** on the same workspace. That is exactly why
`choice_model_services` exists: a customer can be fully on the Gateway *path* and still on the
legacy *contract*, and nothing errors to tell them.

Provider-native paths (not used by the app, documented for the accelerator):
`/ai-gateway/openai/v1`, `/ai-gateway/anthropic`, `/ai-gateway/gemini`,
`/ai-gateway/cursor/v1`, `/ai-gateway/codex/v1`.

## 4. Serving endpoints and AI Gateway config

| Operation | Method + path | Used by |
|---|---|---|
| List serving endpoints | `GET /api/2.0/serving-endpoints` | `list_endpoints`, `external_provider_routing` |
| Get serving endpoint | `GET /api/2.0/serving-endpoints/{name}` | `verify_governed_endpoint`, `rate_limits` |
| Query serving endpoint | `POST /api/2.0/serving-endpoints/{name}/invocations` | `test_guardrail`, all routing steps |
| AI Gateway config on an endpoint | `GET` / `PUT /api/2.0/serving-endpoints/{name}/ai-gateway` | read-only via the SDK in `rate_limits` |

The `ai_gateway` object holds `rate_limits`, `guardrails`, `inference_table_config`,
`usage_tracking_config`, and `fallback_config`. The app **reads** it and never writes: rate
limits and guardrails are guided UI steps so nothing changes throughput or safety on a
customer endpoint unattended.

`AiGatewayRateLimit` fields, from the installed SDK: `calls`, `tokens`, `key`, `principal`,
`renewal_period`.

## 5. Unity Catalog — inventory and DDL

| Operation | Method + path | Used by |
|---|---|---|
| List UC functions | `GET /api/2.1/unity-catalog/functions` | `list_registered_assets` |
| List registered models | `GET /api/2.1/unity-catalog/models` | `list_registered_assets` |
| Execute SQL | `POST /api/2.0/sql/statements` | every system-table query; the policy-function DDL |
| Get statement | `GET /api/2.0/sql/statements/{statement_id}` | polling inside `execute_sql` |

`functions.list` is used deliberately **instead of** `system.information_schema.routines`: it
reads the same inventory from a schema the app already has `USE SCHEMA` on, which removes a
`system` grant from the prerequisites.

## 6. Not available via API

Worth stating plainly — these are the ones that surprise people mid-workshop.

| Thing | Reality |
|---|---|
| **Attaching a service policy** | **UI-only** in Beta. No REST operation, no `ALTER ... SET SERVICE POLICY` DDL. The app creates the policy *function* (SQL) and verifies its logic by evaluating it against a synthetic event; attachment is the manual step. |
| Guardrail config (PII, safety) | Configurable in the AI Gateway UI. The legacy `ai_gateway.guardrails` object on a serving endpoint is a different, older surface. |
| Account-console budgets | Account-level, not a workspace API. Manual step with a cloud-aware deep link. |
| Creating a governed endpoint | Intentionally not automated — the app never creates or mutates endpoints on a customer workspace. |

## 7. System tables

Read through the Statement Execution API. Exact columns in `APIS_AND_SETUP.md` §3.

| Table | Status | Used by |
|---|---|---|
| `system.ai_gateway.usage` | Beta | `usage_by_project`, `coding_agent_usage`, `mcp_telemetry`, `telemetry_readiness` |
| `system.ai_gateway.external_model_spend` | Beta | `gateway_spend_by_model`, `budget_status` |
| `system.access.audit` | GA | `audit_scan`, `pii_safety_readiness`, `telemetry_readiness` |

Only `system.ai_gateway` and `system.access` are needed. `system.billing`, `system.serving`,
and `system.information_schema` were each removed once they proved avoidable, to keep the
account-admin ask as small as possible.
