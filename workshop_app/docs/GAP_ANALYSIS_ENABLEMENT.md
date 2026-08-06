# Gap analysis: workshop vs. the Unity AI Gateway Enablement doc

Feature-by-feature check of the 18 core steps + 21 accelerator steps against
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

---

## MUST HAVE — BASE WORKSHOP

### 1. Lock down the default: `system.ai` is open to all account users
**Gap. This is the doc's step 1 and we don't do it.**

The doc's baseline is *"block broad model-serving access first"* — restrict `USE_SCHEMA` /
`EXECUTE` on `system.ai`, and remove `CAN_QUERY` from broad groups on Foundation Model API
endpoints. We verified the underlying fact live: **`system.ai.github` grants `EXECUTE` to
`account users`.** The MCP accelerator surfaces this for MCP services only.

Why base: it is the single highest-impact finding for a security team, it takes one query to
show, and every other control is theatre if the default path is wide open. Currently a
customer could finish the workshop with a beautifully governed endpoint *and* an unrestricted
`system.ai`.

**Proposal:** one step in Choice — "What can everyone already reach?" — listing broad grants
on `system.ai` (models and MCP services) and naming the lockdown as the first rollout action.
~8 min. Read-only.

### 2. Model access control — `CAN_QUERY` on an endpoint
**Gap.**

We prove UC grants on *MCP services* (`mcp_grants`) and we register model services
(`choice_model_services`), but we never show endpoint-level ACLs (`CAN_QUERY` / `CAN_VIEW` /
`CAN_MANAGE`) — the doc's primary access-control mechanism, and GA.

Why base: "who can call this model?" is the first Access question. `CAN_MANAGE` restriction is
also what prevents shadow endpoints, which is the doc's stated pitfall.

**Proposal:** extend `verify_governed_endpoint` to report the endpoint's ACL, flagging any
broad group with `CAN_QUERY` and anyone beyond platform-admins with `CAN_MANAGE`. No new step.

### 3. Request tags vs service tags
**Partial → tighten.**

`cost_tags` covers server-side tags and now explains the distinction in the concept, but we
never *send* a request tag. The doc's exact header is
`Databricks-AI-Gateway-Request-Tags` and it's how per-project chargeback works.

Why base: the doc lists "request tags not standardized" as a day-one pitfall, and it's cheap —
one header on a routing call we already make.

**Proposal:** send the header on the routing steps and show it landing in
`request_tags`. Extends existing steps.

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

**Do now (base workshop, ~15 min net):**
1. `system.ai` broad-grant check — new Choice step (~8 min)
2. Endpoint ACL reporting — extend `verify_governed_endpoint` (0 min)
3. Request-tag header on the routing steps (0 min)

To stay inside 4 hours, item 1 lands within the recovered budget from cutting
`control_lakewatch`; items 2–3 extend existing steps.

**Do next (accelerators, no core time):**
4. `ucode` walkthrough + the 429 demo → Coding Agents
5. Policy ranking, fail-closed, MASK vs BLOCK → Policies & Guardrails
6. Secrets + `ISOLATED` binding → External Providers

**Fork per customer:** everything in NICE TO HAVE.

**Verify before promising:** which built-in policies exist on the account. Two internal
documents disagree (four vs three, `block_pii` present or not) and none of the four resolve as
SQL functions — check the AI Gateway UI Policies tab rather than quoting a name.
