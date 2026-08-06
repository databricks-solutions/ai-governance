# Coverage: workshop vs. the Adoption & Migration guides

Gap-check of the 19 core workshop steps against the two GA-launch guides (both marked
IN PROGRESS, 2026-08-04):

- **Adoption Guide** — the target-state model: model services, provider services, service
  policies, MCP, UC layout, telemetry, budgets, network.
- **Migration Guide** — the 10-phase sequence from legacy Model Serving AI Gateway to Unity
  AI Gateway.

The explicit goal is **balance**: prove the Gateway works without turning a 4-hour session
into a feature checklist. Every "not covered" below is a deliberate call with a stated reason,
not an oversight.

---

## 1. What the guides say the shape is

**Adoption** — the target state is a UC-addressed **service** (model / model provider / MCP)
with controls attached at the service boundary, telemetry in `system.ai_gateway.usage`, and
budgets filtered by *server-side* tags.

**Migration** — 10 phases, and the ordering is the substance:

> Inventory → choose target object → **UC foundation** → provider/destination dependencies →
> recreate controls at the service boundary → **update the client contract** → validate →
> gradual cutover → remove bypass paths → (checklists)

Two rules carry more weight than the rest:

1. **There is no in-place rename.** New service alongside the old endpoint, validate, move
   clients, revoke later.
2. **A 200 is not acceptance.** Compare latency, tokens, cost, and output quality.

---

## 2. Coverage table

| Guide concept | Workshop step | Status |
|---|---|---|
| Model service as the governed object | `choice_model_services` | ✅ **Added** — was the biggest gap |
| Client contract change (base URL + FQN together) | `choice_model_services` | ✅ **Added** |
| No in-place rename / staged cutover | `choice_model_services` concept | ✅ Framed |
| Discover the model surface | `choice_list_endpoints` | ✅ |
| Agents & tools as UC assets | `choice_agent_registry` | ✅ |
| Service policies (ALLOW/DENY/ASK, ON CALL/ON RESULT) | `control_mcp_policy`, MCP accelerator | ✅ |
| Guardrails on a model service | `control_guardrails` | ✅ |
| Rate limits (the hard control) | `cost_rate_limits` | ✅ |
| Budgets + thresholds | `cost_budgets` | ✅ |
| Server-side vs. request tags | `cost_tags` | ⚠️ **Partial** — see §4 |
| `system.ai_gateway.usage` telemetry | `cost_usage`, `control_lakewatch` | ✅ |
| External-model spend in USD | `cost_spend_by_model` | ✅ |
| Inference tables / payload logging | `control_guardrails` verify, `acc_pg_readiness` | ✅ |
| Audit trail | `control_audit` | ✅ |
| MCP: managed vs. external, 3 planes, OBO | MCP accelerator (9 steps) | ✅ |
| Coding agents through the Gateway | `control_coding_agents`, Coding Agents accelerator | ✅ |
| Model **provider** services (external creds) | External Providers accelerator | ⚠️ **Partial** — see §4 |
| UC foundation (metastore, bindings, groups) | Prerequisites doc | ⚠️ Prereq, not a step |
| Inventory the current estate | — | ❌ **Deliberate** — see §5 |
| Network / PrivateLink / NCC egress | — | ❌ **Deliberate** — see §5 |
| Production-readiness & rollback checklists | POC doc §6 | ✅ As follow-up |

---

## 3. What was added

**`choice_model_services`** — the one genuine gap, and it was conceptual rather than cosmetic.
The workshop demonstrated controls but never named **what they attach to**, or that the client
contract changes. Verified live on `fevm-shm-skunkworks`:

- `/serving-endpoints/<name>/invocations` → **200** (legacy path still works)
- `/ai-gateway/mlflow/v1/chat/completions` with `model=<endpoint-name>` → **200**
- Same path with `model=system.ai.gpt-oss-120b` (an FQN) → **200**
- 24 model services exist as `MODEL_SERVICE` securables; 0 model *provider* services

That both paths answer is exactly why this needs saying out loud: a customer can route coding
agents through the Gateway, see traffic in the usage table, and still be on the legacy
contract. Nothing errors. Without this step the workshop would quietly reinforce that.

---

## 4. Partial coverage — accepted

**Server-side vs. request tags.** `cost_tags` applies project tags, but the guides draw a
sharper line: **server-side** tags (set by the platform owner on the service) are the only
trustworthy budget filter, because **request tags are caller-controlled** and must never be a
financial enforcement boundary. The step now needs one sentence on that distinction rather
than a new step — noted as a content edit, not a gap.

**Model provider services.** Covered in the External Providers accelerator, not core. The
target workspace has **zero** registered, so a core step would report "action needed" for most
customers. Correct place for it is the accelerator, where a provider is actually configured.

**UC foundation.** Metastore assignment and workspace-catalog bindings block everything
downstream, but they're not demonstrable in-app — they're prerequisites. They live in
`PREREQUISITES.md` §1–2, which is where a blocker with days of lead time belongs.

---

## 5. Deliberately not covered

**Inventory the current estate.** The guides' first phase, and the right first phase — but
it's a discovery exercise over the customer's own endpoints, ACLs, clients, and spend. That's
pre-work or a follow-up, not something a 4-hour hands-on session should spend time on. It
belongs in the pre-workshop questionnaire.

**Network: PrivateLink, NCC, egress policies.** Genuinely important and genuinely out of
scope. Front-end PrivateLink is GA; serverless PrivateLink is Enterprise-only Public Preview.
Both require account-level infrastructure changes that can't be made live in a workshop, and
the network team usually isn't in the room. Tracked as a follow-up.

**Passthrough mode.** An escape hatch that *loses* token/cost tracking, token rate limits,
model access control, and service policies. Demonstrating it would teach the wrong lesson. It
belongs in the watch-outs conversation, not a hands-on step.

**The full production-readiness checklist.** ~40 items across five categories. It's a
leave-behind artifact, not a live exercise — POC doc §6.

---

## 6. Watch-outs worth saying in the room

From the guides' risk tables — the ones that actually bite:

- **Shared identity destroys everything downstream.** One PAT shared across a team collapses
  attribution, defeats per-user budgets, and hands every holder an `all-apis` token. Per-user
  OAuth isn't a nicety; it's what makes the telemetry mean anything.
- **Never grant `USE CONNECTION`** to end users on an MCP backing connection — it bypasses
  tool visibility, rate limits, *and* service policies. Grant `EXECUTE` on the service only.
- **Request tags are caller-controlled.** Analytics, never enforcement.
- **Don't retry deterministic failures.** Policy denials, budget blocks, and authorization
  failures shouldn't be retried; only 429s, with bounded backoff.
- **Delayed cost accounting.** Concurrent requests can exceed a budget before usage reporting
  catches up — which is precisely why rate limits are the hard control and budgets are not.
- **`COALESCE(service_name, endpoint_name)`** when querying usage: legacy rows carry a null
  `service_name`. Miss this and migrated vs. legacy traffic won't reconcile.

---

## 7. Verdict

**19 core steps, one added.** Coverage of what the guides call the target state is good; the
gap was the *object model and client contract*, now `choice_model_services`.

The remaining omissions are appropriate for a 4-hour hands-on session: inventory is pre-work,
network is account-level infrastructure, passthrough is an anti-pattern, and the readiness
checklist is a leave-behind. Adding them would trade the thing that makes this workshop
work — a governed path the customer's own team stood up and watched fire — for breadth nobody
can absorb in half a day.
