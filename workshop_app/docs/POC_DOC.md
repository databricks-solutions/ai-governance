# AI Governance Workshop — POC Document

**Scope:** governing AI traffic — models, tools, and coding agents — with Unity AI Gateway.
**Format:** 4-hour hands-on session, plus optional ~4-hour accelerators.
**Structure:** Choice · Cost · Control.

| | |
|---|---|
| Customer | _<account name>_ |
| Salesforce id | _<0016100001…>_ |
| Workshop date | _<date>_ |
| Databricks team | AE, AI Specialist SA |
| App | `https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com` |
| Status | ☐ Not started ☐ Prereqs ☐ Delivered ☐ Follow-up ☐ Closed |

> This is a **workshop** POC doc: the exit criteria are proofs the customer's platform team
> ran themselves in their own workspace, not a Databricks-run bake-off. Items the workshop
> cannot close on the day become tracked follow-ups (§6) — enterprise-grade delivery means
> every one of them gets an answer, even if that answer is "roadmap".

---

## 1. Business case

Coding agents and in-house AI apps are being adopted faster than platform teams can govern
them. The gap is not whether teams use AI — it is whether anyone can answer: who called which
model, under what policy, at what cost, on whose behalf.

Three questions this workshop answers with live evidence:

| Question | Pillar | Evidence produced |
|---|---|---|
| Can we adopt any model, tool, or agent without rebuilding governance each time? | **Choice** | One control plane; models, MCP services, and agents as UC assets |
| Can we see and cut what AI costs, per team? | **Cost** | Per-model USD spend, per-developer attribution, a measured routing saving |
| Can we prove a policy actually stopped something? | **Control** | A tool call returning DENY; a blocked prompt; the audit trail |

### Measurable ROI: cost routing

The Cost pillar produces a defensible number rather than a claim. Three approaches are
framed; the one the customer can stand up today is executed live.

| Option | What it is | Status (Aug 2026) | In the workshop |
|---|---|---|---|
| **Smart routing** | Databricks-managed model selection | **Beta** | Positioned, not demoed |
| **Omnigent** | Partner meta-harness above agent harnesses | **Beta** (OSS available) | Positioned, not demoed |
| **Custom router** | Cheap classifier → cheapest sufficient model | Available today | **Runs live** |

Measured on the reference workspace (Claude Sonnet 4.5 / Llama 3.3 70B / Llama 3.1 8B):

| Prompt | Routed to | Saving vs always-frontier |
|---|---|---|
| "What is 15% of 240?" | Llama 3.1 8B | **89%** |
| Multi-region DR architecture, regulated bank | Claude Sonnet 4.5 | **−0.7%** |
| Cost spread, same prompt across three models | — | **16x** cheapest → most expensive |

**Both numbers matter.** Easy work routes down and saves ~90%. Genuinely hard work routes to
the frontier model, and the classifier overhead makes it slightly *negative*. Quoting only
the 89% would not survive a CFO's second question.

Two caveats to state in the room, not bury:

- On "15% of 240", the 8B model answered **3.6** — wrong. The 70B and frontier models
  answered **36**. Cost savings only count if quality holds; this is the argument for owning
  a routing rubric rather than assuming one works.
- Dollar figures use list price until `cost.routing.dbu_to_usd` is set to the customer's
  negotiated rate. **Token counts are always real.**

**How the business case gets built:** take the per-request saving by complexity tier, apply
it to the customer's own request mix from `system.ai_gateway.usage`, and sanity-check against
actual spend from `system.ai_gateway.external_model_spend`. The workshop produces the rate;
the customer's own logs supply the volume.

---

## 2. Success criteria

Binary, and each one is something the customer's team did themselves.

| # | Criterion | Pillar | How it is proven | Status |
|---|---|---|---|---|
| 1 | Governed endpoint exists with usage tracking | Control | `verify_governed_endpoint` | ☐ |
| 2 | Full model/tool/agent inventory is visible | Choice | `list_endpoints`, `list_registered_assets` | ☐ |
| 3 | A restricted tool call returns **DENY**, a read returns **ALLOW** | Control | `test_mcp_policy` | ☐ |
| 4 | A blocked prompt is refused by a guardrail | Control | `test_guardrail` | ☐ |
| 5 | Rate limit enforced (HTTP 429 path) | Cost | `rate_limits` | ☐ |
| 6 | AI spend visible in USD, by model | Cost | `gateway_spend_by_model` | ☐ |
| 7 | Coding-agent usage attributable **per developer** | Control | `coding_agent_usage` | ☐ |
| 8 | Routing saving measured on a customer prompt | Cost | `routing_roi` | ☐ |
| 9 | Cost attributable to a project/team tag | Cost | `apply_tags` → `usage_by_project` | ☐ |
| 10 | Audit trail queryable; no secrets leaked in args | Control | `audit_scan` | ☐ |

**Exit bar:** 1–7 complete. 8–10 depend on customer-side tagging and traffic volume and
frequently become follow-ups — that is expected, not a failure.

---

## 3. Prerequisites

Ownership matters more than the list. The **account-admin** items are the most common cause
of a stalled session — they cannot be fixed live.

| Item | Owner | Lead time | Status |
|---|---|---|---|
| Unity AI Gateway enabled on account + workspace | Account admin | Days | ☐ |
| UC catalog exists; deployer can create a schema | Metastore admin | Hours | ☐ |
| SQL warehouse available | Platform | Hours | ☐ |
| **`SELECT` on `system.ai_gateway`, `.serving`, `.access`, `.billing` for the app SP** | **Account admin** | **Days** | ☐ |
| App SP granted `USE SCHEMA` + `CREATE FUNCTION` on the workshop schema | Metastore admin | Hours | ☐ |
| Service-policies **Beta** enabled (for MCP policy steps) | Account admin | Days | ☐ |
| External-storage catalog (for inference tables) | Platform | Hours | ☐ |
| Pilot users provisioned from the customer IdP | Identity | Days | ☐ |
| Coding agent chosen (Claude Code / Cursor / Codex) + `ucode` installable | Dev lead | Hours | ☐ |
| Egress/network validated if external providers in scope | Network | Days | ☐ |
| Workshop group granted `CAN_USE` on the app | Platform | Minutes | ☐ |
| Representative prompt chosen for the routing ROI step | Dev lead | Minutes | ☐ |

**Go/no-go:** `GET /api/health` returns `{"status":"ok"}`. If it returns `misconfigured`, it
names exactly what is unset. Run this the day before, not on the morning.

---

## 4. Agenda (4 hours)

| Time | Segment | Live proof |
|---|---|---|
| 0:00–0:20 | Frame: the governance gap, and what we'll prove | — |
| 0:20–0:50 | **Choice** — inventory models, tools, agents | Endpoint + asset inventory |
| 0:50–1:50 | **Control** — governed endpoint, guardrails, MCP policy | **DENY on a write tool**; blocked prompt |
| 1:50–2:00 | Break | — |
| 2:00–3:00 | **Cost** — routing ROI, rate limits, budgets, attribution | **Measured saving**; spend by model |
| 3:00–3:30 | **Control** — coding agents, audit, observability | Per-developer attribution |
| 3:30–4:00 | Wrap: export outcomes, agree follow-ups and 30/60/90 | Outcomes JSON + report |

Control runs before Cost: the routing ROI story lands better once the room has seen that
governance holds regardless of which model answers.

---

## 5. Deliverables

1. **Live governed path** in the customer's workspace — endpoint, policy function, rate
   limit, usage tracking.
2. **Outcomes export** — `<sfid>_workshop_report.md` (leave-behind) and
   `<sfid>_workshop_outcomes.json` (into the internal account journey).
3. **Repeatable template** — `config/workshop.yaml` holding their catalog, endpoints, MCP
   service, and tags; re-runnable cohort by cohort.
4. **Routing ROI worksheet** — per-tier saving plus their own request mix.
5. **`docs/APIS_AND_SETUP.md`** — every API, system table, and grant, with GA vs Beta.
6. **This document**, with §6 filled in.

---

## 6. Follow-up items

Anything not closed on the day. Each needs an owner, a date, and an answer — including
"roadmap, here is the timeline".

### 6.1 Product status to confirm per account

These are **not** workshop-day promises. Confirm each before it reaches a proposal.

| # | Item | Status (Aug 2026) | Why it matters | Owner | Due |
|---|---|---|---|---|---|
| F1 | Budget **hard blocking** ("block usage") | Rolling out | FinOps often hears "hard cap". Today: **alerts are GA**, rate limits are the hard control | | |
| F2 | **Service policies** (ALLOW/DENY) | **Beta**; attach is **UI-only** | No REST/SQL attachment, so no IaC for policy yet | | |
| F3 | **Smart routing** | **Beta** | If they want managed routing rather than their own | | |
| F4 | **Omnigent** managed | **Beta**; pricing TBD | Partner routing layer | | |
| F5 | **MCP payload logging** | **Not available** | Do not promise MCP request/response logs | | |
| F6 | Per-group budget overrides / external-model hard caps | Partial | Multi-team chargeback design | | |
| F7 | **Lakewatch** | Announced | Confirm before positioning as the SIEM answer | | |
| F8 | `system.ai_gateway.*` tables | **Beta** | Schema is additive — `DESCRIBE` before building dashboards | | |

### 6.2 Customer-side work

| # | Item | Blocks | Owner | Due |
|---|---|---|---|---|
| F9 | Tag endpoints with project/cost-centre | Criteria 9 | | |
| F10 | Enable inference tables on an external-storage catalog | Criterion 4, PII judge | | |
| F11 | Roll `ucode` out to the pilot developer cohort | Criterion 7 | | |
| F12 | Set `dbu_to_usd` to the negotiated rate | Credible dollars | | |
| F13 | Design the group/permission model beyond the pilot | Rollout | | |
| F14 | Decide the routing rubric and quality bar | ROI at scale | | |
| F15 | Migrate one shadow workload onto the governed path | Proof of adoption | | |

### 6.3 Open questions

| # | Question | Owner | Answer |
|---|---|---|---|
| Q1 | Which coding agents are actually in use, and at what spend today? | | |
| Q2 | Who owns the AI budget — platform, or each business unit? | | |
| Q3 | Is there a hard compliance requirement for request/response retention? | | |
| Q4 | Which MCP tools must be denied outright vs approved-with-review? | | |
| Q5 | What quality bar makes a cheaper model acceptable? | | |
| Q6 | Does per-user OBO satisfy their audit team, or do they need per-session? | | |

---

## 7. Use cases surfaced

Fill during delivery — these become the pipeline.

| # | Use case | Pillar | Value | Next step | UCO |
|---|---|---|---|---|---|
| U1 | Govern coding-agent traffic with per-developer attribution | Control | Removes a blind spot; makes dev-AI spend chargeable | Expand pilot cohort | |
| U2 | Cut token spend with a routing policy | Cost | Measured saving on their own mix | Rubric + shadow test | |
| U3 | Chargeback AI spend by team | Cost | Turns one line item into per-team cost | Tag standard | |
| U4 | Contextual tool policy (allow reads, deny writes) | Control | Agents can't take destructive actions | Extend to more MCP services | |
| U5 | One governed path for external providers | Choice | Retires shadow API keys | Migrate one workload | |
| U6 | AI telemetry as a security surface | Control | Anomaly detection on spend and refusals | Confirm Lakewatch status | |

### Accelerators (~4h each — run the one that matches their priority)

| Accelerator | Fits when | Prereq |
|---|---|---|
| **Coding Agents** | Devs already on Cursor/Claude Code, ungoverned | `ucode` rollout |
| **MCP Servers** | Agents need governed tool access with OBO | Service-policies Beta |
| **Policies & Guardrails** | Security wants PII/safety proof | Inference tables |
| **External Providers** | Shadow Bedrock/OpenAI keys in use | Egress validated |
| **Agent Registry** | Many agents, no ownership model | UC schema + MLflow |

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `system` grants not in place | Cost/Control steps fail live | Pre-flight the day before; `/api/health` |
| Service-policies Beta not enabled | MCP policy step can't run | Confirm at prereq stage; account admin |
| Customer expects hard budget caps | Credibility loss | Lead with rate limits as the hard control (F1) |
| Inference tables need external-storage catalog | Guardrail evidence unavailable | Identify the catalog in prereqs |
| Routing ROI quoted from the 89% alone | Fails CFO scrutiny | Always show the negative case and the quality miss |
| No tagged traffic yet | Attribution shows empty | Expected — the app says `action_required`, not a false pass |
| Lakebase still provisioning | Progress not saved | App degrades gracefully; tests still run |

---

## 9. Sign-off

| Role | Name | Date | Outcome |
|---|---|---|---|
| Customer platform lead | | | ☐ Criteria 1–7 met |
| Customer security/AI architect | | | ☐ Policy enforcement seen live |
| Customer FinOps owner | | | ☐ Cost visibility + ROI understood |
| Databricks AI Specialist SA | | | ☐ Follow-ups owned and dated |
| Databricks AE | | | ☐ Use cases → UCOs |

**Attachments:** outcomes JSON · outcomes report · `config/workshop.yaml` ·
`docs/APIS_AND_SETUP.md` · routing ROI worksheet.
