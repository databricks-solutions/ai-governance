# Gap analysis: workshop vs. the Unity AI Gateway Enablement doc

Feature-by-feature check of the core workshop steps + 21 accelerator steps against
*Unity AI Gateway Enablement* (July 2026), which is a **customer-enablement** document —
i.e. what one specific customer needs to stand this up, not what the product can do.

That distinction drives every call below. The enablement doc is broader than a 4-hour
workshop on purpose: it includes Genie/Teams/Copilot integration, Terraform IaC, identity
provisioning, and secret rotation. Those are real requirements; most are not *live testable*
in a room.

Buckets, as requested:

- **MUST HAVE — BASE WORKSHOP** — the governed path is not credible without it.
- **MUST HAVE — ACCELERATOR X** — needed, but belongs in a named accelerator.
- **NICE TO HAVE** — for the customer fork, not the general workshop.

> **Status (2026-08-06): all three BASE items are implemented and verified live.** The core
> workshop is now **20 steps** (choice 5 / cost 8 / control 7), still inside 4 hours — the two
> new steps spend the budget recovered by cutting `control_lakewatch`, and request tags cost no
> extra time. Accelerator and fork items below remain proposals. Implementation notes are
> inline under each item; the surprises are in §"What testing changed".

---

## MUST HAVE — BASE WORKSHOP

### 1. Lock down the default: `system.ai` is open to all account users
**Gap → ✅ IMPLEMENTED as `choice_default_access` (test `default_access`).**

The doc's baseline is *"block broad model-serving access first"* — restrict `USE_SCHEMA` /
`EXECUTE` on `system.ai`, and remove `CAN_QUERY` from broad groups on Foundation Model API
endpoints. We verified the underlying fact live: **`system.ai.github` grants `EXECUTE` to
`account users`.** The MCP accelerator surfaces this for MCP services only.

Why base: it is the single highest-impact finding for a security team, it takes one query to
show, and every other control is theatre if the default path is wide open. Currently a
customer could finish the workshop with a beautifully governed endpoint *and* an unrestricted
`system.ai`.

**Implemented:** `choice_default_access`, "What can everyone already reach?", reads
`GET /api/2.1/unity-catalog/permissions/{catalog|schema}/{name}` for both `system` and
`system.ai` and reports any everyone-shaped principal holding `EXECUTE`/`ALL_PRIVILEGES`.
Read-only by design — narrowing `system` is a platform-owner decision, so the step reports the
grants and names the remediation rather than revoking on a customer metastore.

Live result on the reference workspace (`fevm-shm-skunkworks`, 2026-08-06):

```
catalog system   -> account users: BROWSE, EXECUTE, READ_VOLUME, SELECT, USE_CATALOG, USE_SCHEMA
schema system.ai -> account users: EXECUTE, READ_VOLUME, SELECT, USE_SCHEMA
```

Both securables are checked, not just `system.ai`, because the `effective-permissions` variant
shows the grant is **inherited from the `system` catalog** — revoking on the schema alone does
not close the path, which is exactly the kind of detail that makes a remediation fail silently.

### 2. Model access control — `CAN_QUERY` on an endpoint
**Gap → ✅ IMPLEMENTED as `control_endpoint_acl` (test `endpoint_acl`).**

We prove UC grants on *MCP services* (`mcp_grants`) and we register model services
(`choice_model_services`), but we never show endpoint-level ACLs (`CAN_QUERY` / `CAN_VIEW` /
`CAN_MANAGE`) — the doc's primary access-control mechanism, and GA.

Why base: "who can call this model?" is the first Access question. `CAN_MANAGE` restriction is
also what prevents shadow endpoints, which is the doc's stated pitfall.

**Implemented** as its own step rather than an extension of `verify_governed_endpoint`, because
testing showed it carries a second lesson worth its own card (below). It flags broad groups
holding `CAN_QUERY` and reports every `CAN_MANAGE` holder as the shadow-endpoint risk.

Two API behaviors found by testing, both now handled:

- `get_permissions()` takes the endpoint **id**, not its name — the name returns
  `'<name>' is not a valid Inference Endpoint ID`. The step resolves the id with a `get()`
  first.
- **Provided foundation-model endpoints have `id = None`** and carry no workspace ACL at all;
  they are not workspace securables. So `endpoint_acl` and `default_access` are not
  substitutes — FMAPI endpoints are governed *only* by the UC grants in item 1, and a customer
  who checks endpoint ACLs alone will believe they are covered when they are not. The step says
  this explicitly instead of returning a confusing failure.

Verified live on both branches: a custom endpoint returned a real 3-principal ACL
(`CAN_QUERY` service principal, 2 × `CAN_MANAGE`), and `databricks-claude-sonnet-4-5` returned
the no-ACL explanation.

### 3. Request tags vs service tags
**Partial → ✅ IMPLEMENTED. The workshop now sends the header, and the fix was bigger than
expected.**

`cost_tags` covers server-side tags and now explains the distinction in the concept, but we
never *send* a request tag. The doc's exact header is
`Databricks-AI-Gateway-Request-Tags` and it's how per-project chargeback works.

Why base: the doc lists "request tags not standardized" as a day-one pitfall, and it's cheap —
one header on a routing call we already make.

**Implemented**, and it required changing *how the workshop calls models at all*: the SDK's
`serving_endpoints.query()` targets the legacy invocations path and exposes no way to set
headers, so it cannot carry the tag. `server/routing.py` now calls
`/ai-gateway/mlflow/v1/chat/completions` directly.

Changes: `routing.query()` sends `Databricks-Ai-Gateway-Request-Tags` on every model call
(project, cost_center, environment, use_case); `cost_tags` shows both tag mechanisms and states
the trust boundary; `cost_usage` splits the count into **request-tagged** vs **endpoint-tagged**
instead of OR-ing them, so the room can see which mechanism is actually working.

---

## What testing changed

Three things only surfaced by running this against a live workspace, each of which changed the
implementation rather than just confirming it:

**1. The SDK cannot send the header at all.** `serving_endpoints.query()` is hard-wired to the
legacy `/serving-endpoints/{name}/invocations` path and takes no `headers` argument, so "send
the header" was not a one-line change: the routing module had to move to
`/ai-gateway/mlflow/v1/chat/completions` (which accepts a plain endpoint name in `model`, so no
config change was needed).

**1b. Tags confirmed landing — after a ~19 minute wait.** All six tagged routing calls appeared
in `system.ai_gateway.usage` with the full map intact, and `usage_by_project` now returns:

```
1 requester across 3 requester/target pair(s) — 6 request-tagged, 0 endpoint-tagged
```

The `0 endpoint-tagged` is correct and is the teaching contrast: no governed endpoint exists on
that workspace, so nothing carries server-side tags. Caller-supplied attribution works;
trustworthy attribution does not exist yet.

**A retraction worth recording, because it is the trap here.** I first concluded the legacy path
*accepts the header and silently drops the tag*, on the evidence that a tagged legacy call
produced no usage row. That was wrong: the table lags badly — `max(event_time)` was **20:03**
when the wall clock was **20:16**, still 20:03 at **20:25** — and my *gateway* call was missing
too. I was reading ingestion lag as a dropped tag. Hence the freshness diagnostic in
`usage_by_project`: **check `max(event_time)` before concluding tagging is broken**, or a room
spends twenty minutes debugging a working control.

Whether the legacy path records a row is still **unconfirmed** (its A/B markers fell outside the
ingested window). Doesn't affect the workshop; don't assert it to a customer either way.

**1c. `service_name` is NULL for endpoint-addressed Gateway calls.** The landed rows carry
`endpoint_name` with `service_name` NULL, because the routing steps name a plain endpoint rather
than a service FQN. So `COALESCE(service_name, endpoint_name)` is needed even for Gateway
traffic — not just for legacy rows, which is how the migration guide frames it. `usage_by_project`
groups on the COALESCE; without it the workshop's own traffic shows up as an unnamed bucket.

**2. Endpoint ACLs need the id, and FMAPI endpoints have none.** See item 2. The second half
matters most: checking endpoint ACLs alone gives false confidence, because the endpoints most
likely to be wide open are precisely the ones with no ACL to check.

**3. The `system.ai` grant is inherited from the `system` catalog.** Revoking on the schema
alone leaves the path open, so `default_access` checks both securables.

---

## MUST HAVE — ACCELERATOR

### Coding Agents accelerator

**4. `ucode` as the onboarding path — MUST HAVE**
The doc makes `ucode` the *recommended* consumer path with a full command set
(`ucode claude`, `ucode configure --agents`, `ucode configure mcp`, `ucode status`,
`ucode usage`, `ucode revert`). We mention it in prose but never walk it.

This is the accelerator's whole point: a developer running `ucode claude` and seeing their own
traffic attributed. Currently our accelerator checks attribution *after* someone else set it
up.

**5. The four common errors — MUST HAVE**
The doc's runbook ends with 401 / 404 / 429 / 503 and their remedies. A workshop that never
shows a **429** hasn't proven the rate limit is real. Pair with `cost_rate_limits`: set a low
limit, exceed it, see the 429.

**6. OAuth U2M vs PAT — MUST HAVE**
The doc is emphatic: OAuth 1-hour auto-refresh is preferred; PAT is legacy and carries
`all-apis` — the broadest possible token. Our app runs as a service principal, so this is
positioning + a `ucode` demo, not a test.

### Policies & Guardrails accelerator

**7. Built-in policies — MUST HAVE, with a caveat I tested**
The enablement doc lists **four** built-ins including `block_pii`; the MCP field guide says
there are **three** and no `block_pii`. I tried to settle it live and could not:

```
DESCRIBE FUNCTION system.ai.block_pii              -> NOT FOUND
DESCRIBE FUNCTION system.ai.block_unsafe_content   -> NOT FOUND
DESCRIBE FUNCTION system.ai.block_jailbreak        -> NOT FOUND
DESCRIBE FUNCTION system.ai.block_hallucination    -> NOT FOUND
SHOW FUNCTIONS IN system.ai LIKE '*block*'         -> FAILED
```

**None of the four resolve as SQL functions** on the reference workspace — consistent with the
field guide's note that built-ins are Databricks-managed and not browseable in Catalog Explorer
during Beta. So the disagreement is unresolved and *not resolvable by SQL*: attach them from
the AI Gateway UI Policies tab and read the list there.

Practical guidance: **do not name a specific built-in in a customer commitment.** Say "there
are built-in LLM-as-judge guardrails; we'll confirm which on your account," then check the UI.
`block_pii` in particular is the one a security team will ask for, so verify before it reaches
a proposal.

**8. Policy rank ordering + fail-closed — MUST HAVE**
Multiple policies attach with a rank; blocking policies run in parallel first, then
sequential; **any evaluation error means DENY**. We state fail-closed in the concept but never
demo two policies interacting. That interaction is where customers get surprised.

**9. PII `MASK` vs `BLOCK` — MUST HAVE**
We only demo BLOCK. MASK is the more common production choice — it lets the request through
with PII redacted. One config change on the same step.

### External Providers accelerator

**10. Secret handling — MUST HAVE**
`databricks secrets put-secret <scope> <key> --string-value ...`, and never inline a provider
key. The doc calls out credentials-in-code as a top pitfall. Our accelerator registers a
provider but skips where the credential lives.

**11. Workspace-catalog binding (`ISOLATED`) — MUST HAVE**
`isolation_mode = ISOLATED` plus explicit bindings is how the doc enforces which workspaces
see which models. Without it, "approved models" is advisory. Read-only check.

---

## NICE TO HAVE — customer fork

These are real needs in the enablement doc that shouldn't be in a general workshop. Fork them
in when the customer's shape demands it.

| # | Feature | Why fork, not core |
|---|---|---|
| 12 | **Genie budgets, free tier, 25% discount** (150 DBU/user/mo; discount to 2027-01-31; Code/One/Agent share one SKU) | Genie-specific commercial detail. Belongs in a fork for a Genie-led customer. Note the trap: per-product isolation needs a dedicated account group. |
| 13 | **Genie spaces + Conversation API** (`POST /api/2.0/genie/spaces/{id}/start-conversation`) | A different product surface. Would double the workshop. |
| 14 | **Teams / Copilot Studio integration** | Needs a Microsoft tenant and a custom connector — can't be done live. |
| 15 | **OBO for M365** (manual Entra→Databricks mapping; turnkey SAML "coming soon") | Tenant-specific and currently manual. High value for an M365 shop. |
| 16 | **Terraform / IaC** (`databricks_model_serving`, `databricks_grants`, `databricks_workspace_binding`) | The doc's labs are Terraform. Our app is click-through by design — a room of platform engineers may prefer IaC, which is exactly a fork. |
| 17 | **Service principal M2M + rotation** (`POST /oidc/v1/token`, 90–180 day secrets, 24h overlap) | Operational hygiene, not a governance proof. |
| 18 | **Automatic Identity Management vs SCIM** | Account-level identity plumbing; a prerequisite, not a step. |
| 19 | **Custom Lakeview admin dashboard** | The built-in usage dashboard covers the workshop. A custom dashboard is follow-up work. |
| 20 | **Endpoint registry table** (name, model, owner, groups, limits, status) | Governance *process*, not a product capability. Good leave-behind template. |
| 21 | **Pattern A → Pattern B migration** (`system.ai` direct → curated `catalog.services`) | The doc's maturity ladder. Our `choice_model_services` teaches the object model; the staged rollout is a follow-up plan. |
| 22 | **Naming conventions** (`{provider}-{model}-{usecase}`) | Convention, not a test. |

---

## Already covered — no action

Rate limits (QPM/TPM, per-user/group) · budgets + thresholds · guardrails on a model service ·
service policies incl. ON CALL/ON RESULT and ALLOW/DENY/ASK · usage tracking · inference
tables · `system.ai_gateway.usage` and `external_model_spend` · per-developer coding-agent
attribution · MCP services (managed vs external, three planes, OBO) · model services and the
client contract · audit trail · UC grants on MCP services.

---

## Recommended changes, ranked

**Done (base workshop) — 2026-08-06:**
1. ✅ `system.ai` broad-grant check — new Choice step `choice_default_access` (~8 min)
2. ✅ Endpoint ACL — new Control step `control_endpoint_acl` (~6 min; promoted from an
   extension because the FMAPI-has-no-ACL lesson needed its own card)
3. ✅ Request-tag header on every routing call, plus a split request/endpoint count in
   `cost_usage` (0 min)

Core is **20 steps**, still inside 4 hours: items 1–2 spend the budget recovered by cutting
`control_lakewatch`, and item 3 costs no time.

**Do next (accelerators, no core time):**
4. `ucode` walkthrough + the 429 demo → Coding Agents
5. Policy ranking, fail-closed, MASK vs BLOCK → Policies & Guardrails
6. Secrets + `ISOLATED` binding → External Providers

**Fork per customer:** everything in NICE TO HAVE.

**Verify before promising:** which built-in policies exist on the account. Two internal
documents disagree (four vs three, `block_pii` present or not) and none of the four resolve as
SQL functions — check the AI Gateway UI Policies tab rather than quoting a name.
