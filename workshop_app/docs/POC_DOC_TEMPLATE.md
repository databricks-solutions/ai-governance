<!-- header [External] [Customer] - Databricks AI Governance POC -->
<!-- footer Databricks | AI Governance -->

# [Customer] // Databricks

## AI Governance - Production POC

**Template:** This is the canonical AI Governance POC DOC. It is the production follow-up to the
AI Governance Workshop: the workshop proves Choice, Cost, and Control live on the customer's own
workspace in a day; this POC takes everything the room could not finish and drives it to production
(U6). The workshop app generates an identical doc with the Tasks and Timeline and Success Criteria
filled from the session - keep this template and that export in the same structure. Replace every
placeholder; delete this note before sharing.

The AI Governance Workshop proved Choice, Cost, and Control live on [Customer]'s own workspace.
This POC takes that from a working session to production: every control the room could not finish
becomes a tracked task below, and the goal is to drive the list to zero so that AI at [Customer]
runs on one governed control plane - every model, tool, and agent inventoried, every request priced
and attributed, and every policy enforced and audited.

### Key Contacts

**Databricks**

| Name | Role |
|------|------|
| @FirstName LastName | Account Executive |
| @FirstName LastName | Solutions Architect (lead) |
| @FirstName LastName | Specialist SA - AI Governance |
| @FirstName LastName | SA Manager |

**Customer stakeholders**

| Name | Title / Role |
|------|-------------|
| Name | Platform / Cloud admin (account admin) |
| Name | AI Governance lead (policy & budget owner) |
| Name | Principal developer |
| Name | Security / compliance stakeholder |

### Executive Alignment

- **[Date]:** [Customer exec] ([title]) and [Databricks exec] ([title]) - [purpose]
- **[Date]:** [Customer exec] ([title]) and [Databricks exec] ([title]) - [purpose]

**Next alignment:**
- **[Date]:** [Customer exec] ([title]) and [Databricks exec] ([title])

### Summary & Scope

Most platform teams cannot answer "what AI is running here, who is calling it, and what is it
costing?" This POC closes that gap on [Customer]'s workspace with Unity Gateway: it puts every
model, tool, and agent behind one Unity Catalog control plane, prices and attributes every request,
and enforces and audits policy at the Gateway. The workshop proved these controls live; the goal of
this POC is to drive the remaining items below to done and reach production.

**Note:** The app-generated version replaces this paragraph's second half with the live progress read, e.g. "8 of 14 applicable controls were proven live in the workshop (57%); 2 marked N/A. The remaining 6 are the POC punch list below."

### Governance Objectives

**Choice** - Any model, tool, or agent behind one Unity Catalog control plane - proprietary and
open-weight addressed the same way, governed by UC grants, so model choice is never a single-vendor
bet.

**Cost** - Every request priced, projected, budgeted, and attributed to a team and a task - so AI
spend is visible, forecastable, and capped before it runs away.

**Control** - Rate limits, guardrails, and MCP policies that deny specific calls, with identity
propagation and the audit telemetry that proves each control actually fired.

### POC Scope & Success Criteria

**Note:** One row per control. Success criteria are the measurable "We can..." outcomes; make them quantitative where you can (volumes, thresholds, counts). Status: Proven in workshop / Action needed / Not started / N/A.

| OKR | Success criteria | Status |
|-----|-----------------|--------|
| **Choice** | Any model, tool, or agent behind one control plane, addressed as a UC securable. | |
| Inventory endpoints & flag legacy vs model services | Every serving endpoint and agent inventoried; 30-day traffic split into legacy (v1) vs Unity Gateway, with the legacy migration backlog named | |
| Put a model behind a governed name | A model stood up as a UC model service (`catalog.schema.service`) with a stable client contract and UC-grant access | |
| Choose which models teams can access | Each team's model access governed by UC grants (not per-developer keys); effective access reported per identity | |
| Run proprietary & open-weight models | At least one open-weight and one proprietary model served through the same governed Gateway path, same grants and attribution | |
| **Cost** | Project routing cost, cap spend and throughput, and attribute each request. | |
| Project routing savings | Monthly cost projected across models at [Customer]'s negotiated $/DBU and request volume; cheapest-sufficient routing savings estimated | |
| Read 30-day spend by model | 30-day AI spend in USD read by model/SKU (external + internal DBU-billed) | |
| Enforce rate limits (QPM/TPM) | QPM/TPM limits enforced per service/user/group; HTTP 429 observed when exceeded | |
| Set budgets & alert thresholds | Account budget set with an alert threshold; the alert confirmed to actually fire | |
| Attribute usage by team/tag & per task | Usage split by team tag and by task x model; server-side (budget-safe) tags in place on each team's service | |
| **Control** | Policies, guardrails, identity propagation, and the telemetry that records them. | |
| Review who can call the model service | UC grants on the model service reviewed; no over-broad EXECUTE and no shadow-service MANAGE | |
| Prove a guardrail blocks a prompt | A blocked prompt is actually stopped; the block is visible in the inference table | |
| Attach a contextual MCP policy | A UC SQL service policy allows read tools and denies write tools, running on-behalf-of the caller | |
| Scan the audit trail for leaks & denials | Audit trail queried for denied/failed calls; tool arguments scanned for secret-shaped strings | |

### Tasks and Timeline

**Note:** The production punch list. In the app-generated doc this is filled from everything flagged "Add to POC" in the session plus any step left incomplete, grouped by pillar, POC-flagged items first. Here, list the items carried out of the workshop. Owners and dates are yours to assign.

| Task | [Customer] owner | Databricks owner | Comments | Target due date | Status |
|------|-----------------|-----------------|----------|----------------|--------|
| **Kickoff & environment** | | | | | |
| POC kickoff - align scope, owners, and the success criteria above | [Name] | @FirstName LastName | Full team, both sides | [Date] | |
| Confirm workspace, Unity Gateway, and the two `system` grants are in place | [Name] | @FirstName LastName | Carries over the workshop prerequisites | [Date] | |
| **Choice** | | | | | |
| [Choice item carried from the workshop] | [Name] | @FirstName LastName | | [Date] | |
| **Cost** | | | | | |
| [Cost item carried from the workshop] | [Name] | @FirstName LastName | | [Date] | |
| **Control** | | | | | |
| [Control item carried from the workshop] | [Name] | @FirstName LastName | | [Date] | |
| **Accelerator - [name]** | | | | | |
| [Accelerator item, if an accelerator is in scope] | [Name] | @FirstName LastName | | [Date] | |
| **Readout & production sign-off** | | | | | |
| Final readout - every success criterion met, remaining risks named | [Name] | @FirstName LastName | Full team, both sides | [Date] | |
| Production sign-off and transition to steady-state ownership | [Name] | @FirstName LastName | | [Date] | |

### POC Staffing Plan

**Databricks**

| Name | Role | Focus |
|------|------|-------|
| @FirstName LastName | Lead SA | End-to-end ownership, project lead |
| @FirstName LastName | Specialist SA | AI Governance overlay |

**Customer resources**

| Name | Role | Focus |
|------|------|-------|
| Name | Platform admin | Workspace & entitlements |
| Name | AI Governance lead | Policy & budget owner |

**Cadence**

- Kickoff with the full team on both sides
- Weekly progress review against the task list above
- Final readout when the success criteria are met

### Workshop Outcomes & Current State

**Note:** What the workshop proved live, and what carried into this POC. The app fills this from the session (proven controls checked, carried controls unchecked).

**Choice** - [controls proven live; controls carried forward]

**Cost** - [controls proven live; controls carried forward]

**Control** - [controls proven live; controls carried forward]

### Mutual Success Plan

| Objective | Actions | Owner | Target |
|-----------|---------|-------|--------|
| Executive alignment | Confirm the governance mandate and the budget owner | [Name] | [Date] |
| Environment ready | Workspace, Unity Gateway, and `system` grants in place | [Name] | [Date] |
| Punch list to zero | Work the tasks above to done | Joint | [Date range] |
| Production sign-off | Readout and transition to steady state | @FirstName LastName | [Date] |

### Evaluation Results

**Note:** To be completed during and after the POC.

| Pillar / OKR | Success criteria (target) | Result | Status |
|--------------|--------------------------|--------|--------|
| Choice | [target] | | |
| Cost | [target] | | |
| Control | [target] | | |

### Resources

- [AI Governance overview](http://go/aigovernance)
- [Unity Gateway documentation](https://docs.databricks.com)
- [AI Governance Workshop app](https://github.com/databricks-solutions/ai-governance)
- [AI governance maturity assessment](https://github.com/databricks-solutions/ai-governance/blob/main/workshop_app/docs/AI_Governance_Maturity_Assessment.xlsx)

### Notes

**Note:** Running notes - filled during the POC.
