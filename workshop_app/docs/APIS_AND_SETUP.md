# APIs, system tables, and setup the workshop depends on

Everything the workshop app touches, what it needs, and — importantly — what is **GA** vs
**Beta/Preview**. Read this before promising a capability to a customer.

Verified against a live workspace (`fevm-shm-skunkworks`, AWS) on **2026-08-05**. Unity AI
Gateway went GA on **2026-08-04**, so several adjacent pieces are still Beta; those are
called out per row rather than glossed.

---

## 1. Availability at a glance

| Capability | Status | Consequence for the workshop |
|---|---|---|
| Unity AI Gateway (core) | **GA** (2026-08-04) | Safe to demo and promise. |
| Model services, MCP services | **GA** | Safe. UC securables, `GRANT EXECUTE`. |
| Rate limits (QPM / TPM) | **GA** | Safe. Service, user, and group scopes. |
| Inference tables (model services) | **GA** | Needs an **external-storage catalog**; rows lag up to ~1h. |
| Budget tracking + **alerts** | **GA** | Safe. |
| Budget **hard blocking** ("block usage") | **Rolling out** | Do **not** promise hard caps — confirm per account. |
| Service policies (ALLOW/DENY) | **Beta** | Function creation is scriptable; **attaching is UI-only**. |
| Guardrails on Unity AI Gateway | **Beta** (via service policies) | Legacy model-serving guardrails are separately Public Preview. |
| `system.ai_gateway.usage` | **Beta** | Works; schema is additive, so `DESCRIBE` before relying on a column. |
| `system.ai_gateway.external_model_spend` | **Beta** | Gives **USD directly** — no price join. |
| `system.serving.endpoint_usage` | Public Preview | **Not used** — 90-day retention, empty tag map, misses Gateway routes. |
| `system.billing.usage` | **GA** | **Not used** — `external_model_spend` already gives USD. |
| MCP payload logging | **Not available** | Do not claim it. |
| Smart routing (Databricks-managed) | **Beta** | Position as roadmap; the app does not demo it. |
| Omnigent (managed) | **Beta** (OSS available) | Partner/meta-harness layer; positioned, not demoed. |
| Lakewatch | Announced | Not a workshop step — not enabled on most accounts. Confirm status before positioning it. |

---

## 2. Databricks APIs the app calls

All via `databricks-sdk` (`requirements.txt` pins `>=0.38`) as the **app's service
principal** — see §5 on why that matters.

| API | SDK call | Used by |
|---|---|---|
| Serving endpoints — list | `w.serving_endpoints.list()` | `list_endpoints`, `external_provider_routing` |
| Serving endpoints — get | `w.serving_endpoints.get(name)` | `verify_governed_endpoint`, `endpoint_acl` |
| Serving endpoints — query | `w.serving_endpoints.query(name, messages=[ChatMessage(...)], max_tokens=...)` | `test_guardrail` |
| Serving endpoints — ACL | `w.serving_endpoints.get_permissions(endpoint_id)` | `endpoint_acl` |
| Gateway chat completions | `w.api_client.do("POST", "/ai-gateway/mlflow/v1/chat/completions", ...)` | all routing steps (see §7) |
| UC permissions | `w.api_client.do("GET", "/api/2.1/unity-catalog/permissions/{type}/{name}")` | `default_access`, `mcp_grants` |
| SQL Statement Execution | `w.statement_execution.execute_statement(warehouse_id, statement, wait_timeout)` | every system-table query, the policy DDL |
| Registered models — list | `w.registered_models.list(catalog_name, schema_name)` | `list_registered_assets` |
| UC functions — list | `w.functions.list(catalog_name, schema_name)` | `list_registered_assets` (avoids a `system` grant) |
| Current user | `w.current_user.me()` | Lakebase user resolution |
| Database (Lakebase) — get instance | `w.database.get_database_instance(name)` | progress store host |
| Database (Lakebase) — credentials | `w.database.generate_database_credential(...)` | per-connection OAuth token |

**Not used, deliberately:** no endpoint create/update, no tag writes, no policy attachment.
Those are guided UI steps so the app never makes unattended changes to a customer workspace.
They surface as `action_required`, not as passes.

### Query shape gotcha

`serving_endpoints.query` accepts many mutually exclusive payload shapes. For chat endpoints
it must be `messages=[ChatMessage(role=..., content=...)]`. Passing `messages=None` is
accepted by the SDK and sends **no prompt** — a silent no-op that looks like a pass.

### Why the routing steps bypass the SDK

`serving_endpoints.query()` is hard-wired to `POST /serving-endpoints/{name}/invocations` — the
**legacy** contract — and it exposes no way to add headers, so it cannot carry
`Databricks-Ai-Gateway-Request-Tags`. `server/routing.py` therefore calls
`/ai-gateway/mlflow/v1/chat/completions` through `api_client.do()` instead. The Gateway path
accepts a plain endpoint name in `model` (not just a service FQN), so this needed no config
change. See §7 and `API_REFERENCE.md` §3.

---

## 3. System tables — verified columns

Only the columns the app actually reads. All confirmed present on the reference workspace.

### `system.ai_gateway.usage` *(Beta)* — the primary source
Preferred over `system.serving.endpoint_usage`: it covers all Gateway traffic (FMAPI,
external models, MCP) and carries the tag maps and `user_agent` the workshop relies on.

```
event_time, requester, requester_type, user_agent, api_type,
endpoint_name, endpoint_tags (MAP), request_tags (MAP),
destination_model, input_tokens, output_tokens, total_tokens,
status_code, latency_ms, routing_information, mcp_metadata
```

Used by `usage_by_project`, `coding_agent_usage`, `telemetry_readiness`.

### `system.ai_gateway.external_model_spend` *(Beta)* — dollars, no join
```
usage_date, usage_quantity (DECIMAL, USD), usage_unit ('USD'),
usage_metadata.model, usage_metadata.provider, usage_metadata.endpoint_name,
identity_metadata.run_by, custom_tags
```

`usage_quantity` is already USD, so **no `list_prices` join**. Used by
`gateway_spend_by_model` and `budget_status`. Estimated from token counts × published
provider prices — informational, will not match an invoice exactly.

### `system.access.audit` *(GA)*
```
event_time, event_date, action_name, service_name,
user_identity.email, response.status_code, request_params
```

⚠️ **`response` is a STRUCT.** Use `response.status_code`. The VARIANT-path form
`response:status_code` fails with `DATATYPE_MISMATCH.UNEXPECTED_INPUT_TYPE`. This bug was
present in the app and is fixed.

### `system.billing.usage` + `list_prices` *(GA)* — **not used**
The app does not read these, so it needs no `system.billing` grant.
`system.ai_gateway.external_model_spend` already reports USD, which covers the workshop's
need. Recorded here because it is the right tool for *total platform* AI spend (including
serverless inference DBUs, which `external_model_spend` excludes) — useful for a follow-up
FinOps conversation, not for the workshop:

```sql
SELECT u.sku_name,
       ROUND(SUM(u.usage_quantity * p.pricing.default), 2) AS usd
FROM system.billing.usage u
JOIN system.billing.list_prices p
  ON  u.sku_name   = p.sku_name
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date > current_date() - 14
GROUP BY 1 ORDER BY usd DESC
```

Verified live — relevant SKUs: `ENTERPRISE_SERVERLESS_REAL_TIME_INFERENCE_*`,
`ENTERPRISE_ANTHROPIC_MODEL_SERVING`, `ENTERPRISE_OPENAI_MODEL_SERVING`.

### `system.serving.endpoint_usage` *(Public Preview)* — **not used**
Mentioned only for contrast. Its tag map is `usage_context` (not `request_tags`) and in
practice it is **almost always empty** — the reason the workshop's tag-based queries returned
nothing before switching to `system.ai_gateway.usage`. It also has 90-day retention and
misses Gateway-native routes, so reading it would cost a `system.serving` grant for no
signal. Dropped deliberately (see §8).

---

## 4. Unity Catalog objects

| Object | Created by | Notes |
|---|---|---|
| Catalog | **Customer, in advance** | Must exist. `--var="catalog=..."`, mirrored in `config/workshop.yaml`. |
| Schema | **The bundle** (`resources.schemas`) | Was missing before; the policy step failed on any fresh workspace. |
| Service-policy function | The app (`create_mcp_policy`) | `CREATE OR REPLACE FUNCTION`; needs `CREATE FUNCTION`. |
| Inference table | AI Gateway UI | `<catalog>.<schema>.<prefix>_payload`. Needs an external-storage catalog. |
| MCP service | Built-in (`system.ai.*`) | e.g. `system.ai.atlassian`. Grant with `GRANT EXECUTE`. |
| Lakebase instance | **The bundle** | `CU_1`. Progress only — the workshop runs without it. |

### Managed MCP vs MCP Services — the distinction that decides your controls

Two different things are both called "MCP". Which one you point at determines whether a
service policy can exist at all. All rows verified live on `fevm-shm-skunkworks`, 2026-08-06.

| | **Managed (UC-native) endpoints** | **MCP Services** |
|---|---|---|
| URL | `/api/2.0/mcp/{functions,genie,sql,ai-search}/…` | `/ai-gateway/mcp-services/<catalog>.<schema>.<name>` |
| UC securable | **No** — raw endpoints | **Yes** — `MCP_SERVICE` |
| Service policies (ALLOW/DENY/ASK) | **Cannot attach** | **Supported** |
| Auth scope | per family: `unity-catalog`, `genie`, `ai-search`, `sql` | per connection |
| MCP-specific telemetry | **None** | usage row + `mcpCall` audit row |
| Examples | UC functions, Genie, SQL, Vector Search | `system.ai.*`, plus external/custom |

**Three planes**, in sequence on every call:

1. **Authenticate** — the OAuth scope picks the endpoint *family*. It grants no per-object
   access. A PAT can't be scope-limited and needs `all-apis`, so scoped OAuth is the
   least-privilege choice.
2. **Authorize** — UC grants: `USE CATALOG` + `USE SCHEMA` to **see** a tool, `EXECUTE` to
   **call** it. Holding `EXECUTE` without the two `USE` grants is the most common silent
   failure.
3. **Behavior** — service policies, ON CALL and ON RESULT, fail-closed. MCP Services only.

Deny behavior differs by endpoint, which matters when you interpret an empty list:

- **UC functions / AI Search** — ungranted objects are **absent** from `tools/list`
  (deny-by-absence, object grain). An empty list is ambiguous: no functions, or no grant.
- **Databricks SQL** — three generic tools are always listed; denial happens at invocation.
- **Genie** — tools are pinned to the `space_id` in the URL; scoping is at configuration time.

**Live control-plane calls** (used by `server/mcp.py`):

```bash
# Every MCP_SERVICE securable on the metastore
databricks api get /api/2.1/unity-catalog/mcp-services

# Who may call one (Plane 2)
databricks api get /api/2.1/unity-catalog/permissions/mcp_service/system.ai.github
```

Verified findings worth knowing before a customer session:

- The metastore exposed **6** provided services (`github`, `slack`, `gmail`,
  `google_drive`, `google_calendar`, `microsoft_365`). `system.ai.atlassian` returned
  **403** — the securable exists but needs per-user OAuth consent. Availability is
  per-workspace; enumerate rather than assume.
- **`system.ai.github` grants `EXECUTE` to `account users`** — open to the whole account by
  default. Prefer deny-by-absence (grant in a customer-owned catalog) over revoking inside
  `system.ai`, where a schema-level revoke may not cascade.
- **`system.ai.github` is already filtered to read-only** — 26 tools, 0 write-capable. There
  is no `push_files` to deny on it, so a "deny writes" demo needs an external MCP that
  actually exposes a write tool.
- **OBO is real and demonstrable**: `tools/call get_me` returned the *caller's* GitHub
  identity. Two participants get two different answers — that's the proof.

**Protocol gotchas** (all cost real debugging time):

- **JSON-RPC errors arrive inside HTTP 200** over Streamable HTTP. Never infer success from
  the status code — check for a `result` key.
- `MCP-Protocol-Version` is required on every request after `initialize`.
- Responses may be SSE, so `Accept` must allow `text/event-stream` and the body may need
  unwrapping from `data:` lines.
- Self-hosted external servers must be **stateless** — a stateful server behind the
  replicated gateway proxy can fail the first `tools/call` even after `initialize` and
  `tools/list` succeed.

**External MCP registration** (the activation path for a customer not yet on Databricks MCP):
HTTP connection → register the MCP Service → per-user OAuth consent → `GRANT EXECUTE` →
invoke. Do **not** grant `USE CONNECTION` to end users; it bypasses tool selection and
auditing.

**MCP payload logging is not in Beta.** Identity, service, and tool name are recorded;
arguments and results are not. Say that plainly — "no payload logging" is not "no
auditability", but it isn't full capture either.

### Service-policy function contract

```sql
CREATE OR REPLACE FUNCTION <catalog>.<schema>.<name>(event VARIANT)
RETURNS VARIANT
RETURN CASE
  WHEN event:context.tool.name::STRING IN ('create_confluence_page')
  THEN to_variant_object(named_struct('result','DENY','reason','blocked by policy'))
  ELSE to_variant_object(named_struct('result','ALLOW','reason',''))
END
```

Two things that cost real debugging time:

1. **`to_variant_object`, not `to_variant`.** `to_variant` does not exist —
   `UNRESOLVED_ROUTINE`. The app shipped with `to_variant`, so this step could never have
   worked. Fixed and verified.
2. **Cast VARIANT paths.** `event:context.tool.name` yields VARIANT; compare only after
   `::STRING`.

Verified live: `create_confluence_page` → `DENY`, `search_confluence_pages` → `ALLOW`.

Attaching the policy is **UI-only in Beta** — no REST or SQL. So the app verifies policy
*logic* by evaluating the function against a synthetic event, and enforcement is confirmed by
invoking the tool from an agent.

---

## 5. Identity: what the app proves, and what it does not

The app runs as **its own service principal**. Every Try-It result therefore reflects the
service principal's permissions, **not** the individual participant's.

This matters for the on-behalf-of claim. The workshop can legitimately say:

- Unity AI Gateway propagates the **caller's** identity to model and MCP services, and
  `system.ai_gateway.usage.requester` records it per user (verified live: 19 distinct
  developers attributed across `claude-cli`, `codex-tui`, `ucode`, `omnigent-probe`).
- Service policies see the caller via `event:context.actor`.

It must **not** claim that a green check in this app proves OBO. The app is a governed
observer; OBO is proven by a participant driving their own coding agent through the Gateway
and seeing their own identity in the logs. The Coding Agents accelerator is where that
happens.

---

## 6. Coding-agent onboarding (`ucode`)

`ucode` is the Databricks CLI that installs, authenticates, and configures a coding agent
against the Gateway — the default path for the Coding Agents accelerator.

```bash
ucode cursor          # or: ucode codex / claude
ucode configure --profiles DEFAULT --use-pat   # PAT instead of OAuth
```

Base URL shape: `https://<workspace>/ai-gateway/<agent>/v1` (`cursor`, `codex`, `gemini`,
`mlflow`). OAuth is preferred — per-user credentials, no shared secret, so attribution and
rate limits work per developer.

Detection is by `user_agent`, which needs no tagging. Live examples:

```
claude-cli/2.1.146 (external, sdk-py, agent-sdk/0.2.83)   anthropic/v1/messages
ucode/0.1.0 codex/0.136.0                                 openai/v1/responses
Go-http-client/2.0                                        cursor/v1/chat/completions
```

---

## 7. Cost routing (the ROI story)

Three options are framed; **only the custom router executes.**

| Option | What it is | Status | In the app |
|---|---|---|---|
| Smart routing | Databricks-managed model selection | **Beta** | Positioned only |
| Omnigent | Partner meta-harness above agent harnesses | **Beta** (OSS available) | Positioned only |
| Custom router | Cheap classifier → cheapest sufficient model | Available today | **Runs live** |

Implementation: `server/routing.py`. Classifier is the cheapest model, and **its cost counts
as overhead**. Pricing comes from `cost.routing` in `config/workshop.yaml`;
`dbu_to_usd` defaults to list price, so dollars are illustrative until a customer sets their
negotiated rate — token counts are always real.

Measured live (`databricks-claude-sonnet-4-5` / `llama-3.3-70b` / `llama-3.1-8b`):

| Prompt | Routed to | Saving vs always-frontier |
|---|---|---|
| "What is 15% of 240?" | Llama 3.1 8B | **89%** |
| Multi-region DR architecture for a regulated bank | Claude Sonnet 4.5 | **−0.7%** |

Both numbers are the point. Easy work routes down and saves ~90%; genuinely hard work routes
to the frontier model and the classifier overhead makes it *slightly negative*. Quoting only
the 89% would be dishonest — the real ROI is the saving applied to the customer's own request
mix, which `gateway_spend_by_model` grounds in their actual spend.

A quality caveat worth showing the room: on "15% of 240", `llama-3.1-8b` answered **3.6**
(wrong) while the 70B and frontier models answered **36**. Cost savings only count if quality
holds — which is the argument for owning the routing rubric rather than assuming one.

Two honesty properties built in:
- **Fails safe** — a classifier error routes to the frontier model, never silently down.
- **Counterfactual is labelled** — frontier cost is priced on the *routed* response's token
  counts, so it is a close per-request estimate, not an exact figure.

### Request tags on every routed call

Each model call carries `Databricks-Ai-Gateway-Request-Tags` (project, cost_center,
environment, use_case) so its tokens attribute to the workshop project in
`system.ai_gateway.usage.request_tags`. That is what lets `cost_usage` show attribution the room
just generated, rather than whatever traffic happened to exist beforehand.

Two caveats to state out loud:
- Request tags are **caller-supplied** — an attribution signal, never an enforcement boundary.
  Budget filters must use server-side `endpoint_tags`, which the caller cannot change.
- The usage table is **not real-time**. Rows can take minutes to appear, so `cost_usage` says so
  rather than letting an empty result read as "tagging is broken."

---

## 8. Permissions checklist

**Deploying user:** create Databricks Apps; create a database instance (workspace users
normally inherit `CAN CREATE`); `CAN_USE` on the warehouse; `USE CATALOG` + `CREATE SCHEMA`
on the target catalog.

**App service principal** — granted by the bundle: `CAN_USE` on the warehouse,
`CAN_CONNECT_AND_CREATE` on Lakebase. Unity Catalog grants are manual (see the README grant
block): `USE CATALOG` + `USE SCHEMA`/`CREATE FUNCTION`/`EXECUTE`/`SELECT`/`MODIFY` on the
workshop schema, plus `USE SCHEMA` + `SELECT` on exactly **two** system schemas.

### Keeping the `system` grant surface to two schemas

Granting on `system` needs an account or metastore admin, so the app minimizes what it asks
for. It reads **only** `system.ai_gateway` and `system.access`:

| Schema | Why | Alternative considered |
|---|---|---|
| `system.ai_gateway` | `usage` (attribution, coding agents, telemetry) and `external_model_spend` (USD) | None — this is the only source of Gateway-native traffic and direct USD |
| `system.access` | `audit` — denied calls, secret-shaped args | None — no API equivalent |

Three schemas were **removed** after checking each was avoidable:

- **`system.billing`** — never actually queried. `system.ai_gateway.external_model_spend`
  reports USD directly, so the `list_prices` join was unnecessary.
- **`system.information_schema`** — replaced with the UC Functions API
  (`w.functions.list(catalog_name=..., schema_name=...)`), which reads the same inventory
  from the schema the app already has `USE SCHEMA` on. Verified live: returns the policy
  functions correctly.
- **`system.serving`** — only a legacy readiness check. `endpoint_usage` has 90-day
  retention, an almost-always-empty `usage_context` tag map, and misses Gateway-native
  routes, so it added a grant requirement for no signal.

**What still works with no `system` grant at all:** the model panel, the full routing ROI
(compare + route + saving), endpoint discovery, asset inventory, governed-endpoint checks,
rate limits, guardrail tests, and the MCP policy create/verify. Those use the serving and
Unity Catalog APIs. Only the telemetry steps need `system` — `usage_by_project`, `coding_agent_usage`,
`gateway_spend_by_model`, `budget_status`, `audit_scan`, `mcp_telemetry`,
`telemetry_readiness`, and `pii_safety_readiness` — and they degrade to `action_required`,
not a crash.

**Account admin still needed for:** the two `system` grants, creating budgets, and enabling
the service-policies Beta. Line these up before the workshop.

---

## 9. Pre-flight check

- [ ] Unity AI Gateway enabled on the account/workspace
- [ ] Target catalog exists; deployer can create a schema in it
- [ ] SQL warehouse running; app SP has `CAN_USE`
- [ ] App SP granted `SELECT` on `system.ai_gateway` and `system.access` — just these two
      *(account admin; without them 7 telemetry steps report `action_required`, the rest work)*
- [ ] `GET /api/health` returns `{"status":"ok"}`
- [ ] Governed endpoint created, with an inference table if guardrail steps are in scope
      *(external-storage catalog required)*
- [ ] Service-policies Beta enabled if MCP policy steps are in scope *(account admin)*
- [ ] Routing endpoints in `cost.routing.endpoints` exist on the workspace
- [ ] `cost.routing.dbu_to_usd` set to the negotiated rate, or dollars flagged illustrative
- [ ] Workshop group granted `CAN_USE` on the app
- [ ] Confirmed whether budget **hard blocking** is available on this account
