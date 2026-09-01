# Coverage: workshop vs. the POC DOC, Adoption, and Migration guides

**Note:** Workshop timing was retuned from 4 hours / 20 steps to **3 hours hands-on (+ ~1 hour slides/discussion) / ~14 steps**. References below to timing/step counts reflect the current model.

Gap-check of the core workshop steps against three sources of truth:

- **AI Governance POC DOC** — the four pillars the POC is measured on
  (**Cost / Usage / Access / Inventory**) and its three phases.
- **Adoption Guide** — target state: model services, provider services, service policies,
  MCP, UC layout, telemetry, budgets, network.
- **Migration Guide** — the 10-phase sequence from legacy Model Serving AI Gateway to Unity
  AI Gateway.

All three are marked IN PROGRESS (GA launch edition, 2026-08-04).

## The delivery shape this has to fit

| Phase | Duration | What happens |
|---|---|---|
| **Prereqs** | ~1 week | Entitlements, grants, previews, pilot users. See `PREREQUISITES.md`. |
| **Workshop** | **3 hours hands-on + ~1 hour slides** | Test and validate live, in their workspace. Core accelerators plus optional deep dives. |
| **Follow-up (POC)** | 1–2 weeks | Close what didn't land; the app's exported outcomes drive it. |

Everything below is judged against that budget. **3 hours hands-on fits ~14 core steps at ~12–13 minutes each
plus 1 hour of slides and discussion** — there is no room for a feature checklist, so every "not covered" is
a deliberate call with a stated reason.

**No migration thread.** Migration is a sequence a customer runs over weeks with their own
inventory; it is not a hands-on exercise. The workshop covers the *one thing* a migration
turns on — the client contract (`choice_model_services`) — and the sequence itself is left to
the field guides.

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

## 1b. The POC DOC's four pillars, mapped to our steps

The POC DOC measures on **Cost / Usage / Access / Inventory**. Our app is organized on
**Choice / Cost / Control** (the FY27 messaging pillars). They aren't in conflict — ours is
the customer-facing narrative, theirs is the POC delivery scorecard — but the mapping should be
explicit so an SA can report against the POC DOC without re-deriving it.

| POC DOC pillar | Its primary measure | Our steps |
|---|---|---|
| **Cost** | Budget alerts wired; cost-per-team SQL returns a table | `cost_budgets`, `cost_rate_limits`, `cost_tags`, `cost_usage`, `cost_spend_by_model`, + the routing ROI trio |
| **Usage** | Discovery dashboard + monitoring live | `cost_usage`, `control_coding_agents`, `control_traces` |
| **Access** | RBAC + ABAC + identity-aware invocation enforced at the Gateway | `control_mcp_policy`, `control_guardrails`, `mcp_grants`, `mcp_obo` (accelerator) |
| **Inventory** | Every endpoint, agent, MCP server registered and owned in UC | `choice_list_endpoints`, `choice_model_services`, `choice_agent_registry`, `mcp_inventory` |

Two POC DOC items we do **not** cover, deliberately:

- **Lakehouse Monitoring profile on the payload table** (drift on input length, refusal rate,
  latency) — needs days of accumulated traffic to show anything. A workshop-day version would
  render an empty chart. Follow-up.
- **P50/P99 latency proof that the Gateway adds ~5–10ms** — a benchmark, not a governance
  control, and it needs sustained load. Better as a pre-supplied number than a live test.

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
| `system.ai_gateway.usage` telemetry | `cost_usage`, `control_coding_agents` | ✅ |
| External-model spend in USD | `cost_spend_by_model` | ✅ |
| Inference tables / payload logging | `control_guardrails` verify, `acc_pg_readiness` | ✅ |
| Audit trail | `control_audit` | ✅ |
| MCP: managed vs. external, 3 planes, OBO | MCP accelerator (9 steps) | ✅ |
| Coding agents through the Gateway | `control_coding_agents`, Coding Agents accelerator | ✅ |
| Model **provider** services (external creds) | External Providers accelerator | ⚠️ **Partial** — see §4 |
| UC foundation (metastore, bindings, groups) | Prerequisites doc | ⚠️ Prereq, not a step |
| Inventory the current estate | — | ❌ **Deliberate** — see §5 |
| Network / PrivateLink / NCC egress | — | ❌ **Deliberate** — see §5 |
| Production-readiness & rollback checklists | — | ❌ **Deliberate** — Migration Guide §§8, 12, 13 |
| Lakehouse Monitoring on the payload table | — | ❌ **Deliberate** — needs days of traffic |
| Gateway latency benchmark (P50/P99) | — | ❌ **Deliberate** — a benchmark, not a control |

---

## 3. What was added

**`choice_model_services`** — the one genuine gap, and it was conceptual rather than cosmetic.
The workshop demonstrated controls but never named **what they attach to**, or that the client
contract changes. Verified live on a reference workspace:

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

**The POC leave-behind itself.** No longer a doc in this repo. The workshop app *generates*
it: `GET /api/export/report` (Markdown, per-step complete/incomplete) and
`GET /api/export/outcomes` (JSON, `schema_version` 2) — both including the accelerators.
Writing a static template alongside a generator that already
produces the real thing was duplication, and the static version drifted immediately.
The Confluence page for part 04 documents what those exports contain.

---

## 5. Deliberately not covered — and where it lives instead

Everything in this section is covered by the two field guides. Point customers there rather
than expanding the workshop:

> **These are the detailed field guides for adopting Unity AI Gateway fresh, or migrating
> from a previous Databricks or external gateway.**
>
> - [Unity AI Gateway **Adoption Guide**](https://docs.google.com/document/d/1Pbe3c5rj2xoOPve-bK6kdjmAJx8Yaz3tAQPQk7F7KaM/edit) — target state, object model, UC layout, telemetry, budgets, network.
> - [Unity AI Gateway **Migration Guide**](https://docs.google.com/document/d/1N656ptJw-PG2rYTKY6d74cY0LYDl7oKnNUjbYwBSVaU/edit) — the 10-phase sequence off legacy Model Serving or a third-party gateway.

**Inventory the current estate.** The guides' first phase, and the right first phase — but a
discovery exercise over the customer's own endpoints, ACLs, clients, and spend. Pre-work, not
workshop time. → Pre-workshop questionnaire; Migration Guide §1.

**The migration sequence itself.** No in-place rename exists, so migration is run-in-parallel
over weeks: validate, move clients in stages, revoke later. Not a 4-hour exercise. The
workshop covers only the pivot point — the client contract — in `choice_model_services`.
→ Migration Guide §§2–10.

**Network: PrivateLink, NCC, egress policies.** Front-end PrivateLink is GA; serverless
PrivateLink is Enterprise-only Public Preview. Both need account-level infrastructure changes
that can't be made live, and the network team usually isn't in the room.
→ Adoption Guide §9; follow-up item.

**Model provider services.** The object for centralizing external-provider credentials.
Requires real provider credentials to be meaningful, so it sits in the External Providers
accelerator. → Adoption Guide §3.

**Passthrough mode.** An escape hatch that *loses* token/cost tracking, token rate limits,
model access control, and service policies. Demonstrating it would teach the wrong lesson.
→ Adoption Guide §3 watch-outs.

**The production-readiness and rollback checklists.** ~40 items across five categories, plus
rollback criteria. Leave-behind artifacts, not live exercises. → Migration Guide §§8, 12, 13.

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

**~14 core steps + ~21 accelerator steps.** Coverage of the POC DOC's four pillars is complete
except two items that need accumulated traffic (monitoring drift, latency benchmark). Coverage
of the Adoption Guide's target state is good; the one real gap was the *object model and client
contract*, now `choice_model_services`.

Fits the delivery shape: **~1 week prereqs → 3 hours hands-on + 1 hour slides → 1–2 weeks follow-up.** ~14 core steps at
~12–13 minutes each plus slides/discussion fits the hands-on window — enough to let a
good question run without losing the last pillar.

The omissions are right for that budget. Inventory is pre-work, migration is a multi-week
sequence, network is account-level infrastructure, passthrough is an anti-pattern, and the
readiness checklists are leave-behinds. All of it is covered by the Adoption and Migration
guides, so nothing is lost — it just isn't workshop time. Adding it back would trade the thing
that makes this work (a governed path the customer's own team stood up and watched fire) for
breadth nobody absorbs in half a day.

**If you need to cut further**, the honest order to drop from the core is:
`control_traces` (a manual link only) → `cost_routing_compare` (the ROI story survives on
`cost_routing_roi` alone). That recovers ~20 minutes.

**Already cut:** `control_lakewatch`. Lakewatch is not enabled on most accounts, so a core
step named after it checked readiness for a product the room could not use — and the
telemetry it probed is already proven by `cost_usage` and `control_audit`. The check itself
survives as `telemetry_readiness` in the Agent Registry accelerator, where telemetry is the
point. Recovered ~10 minutes.

**Since added**, from the enablement-doc gap analysis (`GAP_ANALYSIS_ENABLEMENT.md`), spending
that recovered budget:

- `choice_default_access` — what all account users can already reach. The enablement doc's
  step 1, and the finding that lands hardest: `system.ai` grants `EXECUTE` to `account users`
  by default, so every control downstream sits beside an open path rather than in front of it.
- `control_endpoint_acl` — `CAN_QUERY` / `CAN_MANAGE` on the governed endpoint. The doc's
  primary access-control mechanism, and `CAN_MANAGE` restriction is what prevents shadow
  endpoints.

Net: 20 steps in the same 4 hours. Request tags were the third item and cost no time — the
routing steps now send `Databricks-Ai-Gateway-Request-Tags` on every call, and `cost_usage`
splits request- from endpoint-tagged traffic so the trust boundary is visible rather than
asserted.
