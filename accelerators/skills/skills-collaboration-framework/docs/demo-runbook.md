# Demo Runbook — Skills Collaboration Framework Live Arc

> **CRITICAL:** After every sync, open a **new** Genie Code chat thread.
> Skill changes only take effect in a new thread — never reuse an existing one during the demo.

## Prerequisites

- Workspaces (a dev→staging→prod SDLC):
  - **DEV** (Tier 1 self-upload): `https://dbc-a1b2c3d4-e5f6.cloud.databricks.com` (`greenwood-demo-dev`)
  - **STAGING** (Tier 2 target): `https://dbc-b2c3d4e5-f6a7.cloud.databricks.com` (`greenwood-demo-staging`)
  - **PROD** (part of the Tier 3 fan-out): `https://dbc-c3d4e5f6-a7b8.cloud.databricks.com` (`greenwood-demo-prod`)
  - Tier 3 syncs to **all three** (dev + staging + prod) — enterprise skills are available everywhere.
- Genie Code Agent Mode enabled in all three (verify: workspace Settings)
- ADO pipeline wired and the `databricks-skills` variable group set
- SP OAuth secret registered in the ADO variable group
- Git remote: `azure` → ADO (`https://dev.azure.com/greenwood/cicd-demo/_git/skills-collaboration-framework`)

---

## Workspace topology — set expectations before demoing

This implementation's tier behavior depends on the org's **workspace topology**, and that
varies. The `workspaces.json` mapping is the single knob that absorbs the difference — the
scripts and CI don't change:

| Topology | `tier2.{domain}` | `tier3.workspaces` | What the demo shows |
|----------|------------------|--------------------|---------------------|
| **dev→staging→prod SDLC** (this greenwood demo) | `[staging]` (every domain → the STAGING URL) | `[dev, staging, prod]` | T2 lands in STAGING's `/.assistant/skills` (team integration), T3 fans out to all three — a **live, visible** "T2 is staged, T3 is everywhere" boundary. T1 never syncs (self-uploaded to DEV only). |
| **One workspace per domain** | `[ws_for_that_domain]` | `[all domain workspaces]` | True domain isolation: a T2 skill appears only in its domain's workspace. |
| **Multiple workspaces per domain** (a real Greenwood case) | `[ws_a, ws_b, …]` | `[every workspace]` | A T2 skill fans out to all of the domain's workspaces; T3 fans out to all. `sync-skills.sh`/`prune-deprecated.sh` iterate the list. |

**When demoing, say this out loud:** "Tiers map to *reach*. We only have three demo workspaces, so
instead of one-per-domain we model a dev→staging→prod lifecycle: a personal Tier-1 skill is
dogfooded in DEV, a team's Tier-2 skill is promoted to STAGING for integration, and an enterprise
Tier-3 skill fans out to all three so it's available everywhere. In your environment — multiple
workspaces per domain — the same `workspaces.json` lists each domain's workspaces and the identical
scripts iterate them. The added production concern is auth: a CI SP valid in every target workspace
(account-level OAuth M2M) — here the SP must be entitled in all three, since they're distinct."

> [!NOTE]
> **Greenwood-aligned domains:** the eleven Tier-2 domains (`acute`, `community`, `dgp`, `faa`, `aa`,
> `ed`, `lmps`, `maa`, `quality-analytics`, `infrastructure`, `eabi`) mirror Greenwood's team structure
> so the demo reads as familiar. Each domain ships a baseline Tier-2 skill (12 T2 skills total —
> `infrastructure` has two), plus one enterprise Tier-3 skill, `catalog-navigator`, that applies
> across all domains. Every baseline skill is deliberately scoped to **aggregate / operational /
> metadata** data (`pii: false`, read-only) — clinical *patient-level* data is PHI, which the
> framework's own §2.2 tier rule forces to Tier 3. That's the model working, not a shortcut: the
> tier rules keep operational analytics at T2 and would push any patient-level skill to T3.

### Clinical Environment (Tier 3)

> [!NOTE]
> Seven clinical skills ship as `data_classification: regulated` PHI — and that classification is
> *why* they are Tier 3. The framework's §2.2 tier rule forces regulated/PII data to T3; a T2
> skill carrying PHI would fail the gate. The tier boundary is doing its job, not imposing
> bureaucracy.
>
> All seven read `greenwood_dbw_catalog.greenwood_ehr` (a real EHR-shaped catalog modelling Greenwood's
> semantic layer). Per the framework's reach-vs-runtime-grants model, the skills auto-load in
> every workspace that receives the Tier-3 sync — but they only *execute* successfully where the
> calling user holds Unity Catalog grants to that catalog. No grants, no rows; the framework never
> downgrades the catalog's own access controls.
>
> **Skills:** `clinical-code-resolver`, `elixhauser-comorbidity-profiler`, `vte-cohort-analyzer`,
> `sepsis-cohort-analyzer`, `stroke-mi-cohort-analyzer`, `readmission-cohort-analyzer`,
> `risk-adjusted-outcome-analyzer`.
>
> The **`vte-cohort-analyzer`** flagship demonstrates the Tier-3 write path: it documents building
> the governed `pop_vte()` cohort (scalar predicate function → `pop_vte_tbl` cohort table →
> `mv_vte_endpoint` metric view → `population_definition` registration). The framework's
> write-eligibility gate would reject any `CREATE` or `INSERT` statement in a Tier-2 skill — so
> the write path is itself a T3-only capability, not just a convention.

---

## Step A — Born at Tier 1 (personal sandbox, no sync)

**Story:** Developer creates a personal skill. CI hard-gates only. Never synced.

1. `git checkout -b demo/step-a`
2. Verify `tier1/platform.lead/hello-databricks/SKILL.md` exists
3. `git push azure demo/step-a`
4. Open a PR in Azure DevOps → watch the **Validate** stage:
   - `LintAndScan` — passes
   - `ValidateMeta` — passes
   - `AIReview` — runs but reports "no Tier 2/3 SKILL.md changed" (T1 = lint + scan only)
5. Merge the PR
6. Verify: the **Sync** stage does **not** publish `hello-databricks` (T1 path not in the sync trigger paths)
7. Verify: `/.assistant/skills/` (STAGING workspace) has no `hello-databricks` folder

**Key message:** Governance starts at PR creation. Tier 1 = **runtime isolation** by design — a
gated personal namespace, not a private folder.

> **Say this out loud (turns the "nothing synced" beat into the point):** "This is the most
> important slide for your developers. Tier 1 is a *gated sandbox namespace*. It's version-controlled
> and visible to the team — so it's discoverable and promotable — but it is **runtime-isolated**: the
> framework never syncs it to a shared workspace, so nothing an author builds here can reach a
> clinician until it's promoted through the process you're about to see. That's the safety guarantee:
> not that the code is hidden, but that its *reach* is zero until governance widens it." ~90 seconds,
> then move to Step B.

> [!NOTE]
> **Precise framing (in case someone asks "so anyone can see my Tier 1 skill?"):** Yes — and that's
> intentional. "Sole owner" here means **runtime reach**, not source secrecy: only the promotion
> path can ever publish it, and only to widening tiers. Committing to Git is what earns Tier 1 its
> lint + secret-scan gates and the clean `git mv` promotion path (T1→T2→T3). A truly private,
> laptop-only skill would get *no* gates and couldn't be promoted without being recreated.

---

## Step B — Tier-2 Skill PR

**Story:** `pipeline-cost-analyzer` enters T2. All gates run; steward approves.

1. `git checkout -b demo/step-b`
2. Show `tier2/infrastructure/pipeline-cost-analyzer/SKILL.md` — point out name + description only
3. Show `registry.yaml` — governance metadata separate from the skill file
4. `git push azure demo/step-b`
5. Open PR in Azure DevOps
6. **Show reviewer auto-request:** the branch policy's "Automatically included reviewers" for `tier2/infrastructure/` requests the domain steward
7. Watch the **Validate** stage:
   - `LintAndScan` — show green
   - `ValidateMeta` — show green (tier matches registry, name matches, domain is mapped in `workspaces.json`)
   - `SkillTests` — show green (per-skill regression assertions from `TESTS.yaml`)
   - `AIReview` — **show the PR comment** (verdict, score, rationale from AI Gateway; advisory at T2)
8. Approve as steward + merge
9. Watch the merge build's **Sync** stage → `sync-skills.sh 2 infrastructure` runs (publishing to the STAGING workspace), then the **Report eval_score** step attaches an "AI Skill Review" report to the build summary and tags the build `eval-<skill>-<score>` (the score lives in the build, never written back to the protected `main` branch)
10. Show workspace: `databricks workspace list /.assistant/skills` (STAGING) → `pipeline-cost-analyzer` appears at the **top level** (flat — the `tier2/infrastructure/` structure lives only in Git, never in the workspace; `TESTS.yaml` is stripped by the sync)

**Key message:** Hard gates are deterministic. Smart gate shows the AI reviewing a skill against the skill. The PR comment shows the score; the build (not the repo) is its durable record.

---

## Step C — Payoff: Genie Code auto-loads the skill

**Story:** Real answer from real data. Auto-load, no manual `@` mention needed.

> **Bridge from Step B (say before opening the thread):** "Nothing else happened. No admin
> uploaded anything, no user installed anything. The merge *was* the deployment. Watch —"

> [!WARNING]
> **This is the payoff AND the highest live risk — it's a non-deterministic LLM. De-risk before
> you present:**
> - **Freeze the exact prompt** (below) — do not improvise it live.
> - **Pre-capture a known-good screenshot/recording** of the successful auto-load + answer. If it
>   faceplants live, show the capture and keep narrating — never leave dead air.
> - **Fallback rule if it doesn't auto-load in ~2 tries** (say it calmly): "Auto-load matches on
>   the skill's description — occasionally a fresh thread needs a nudge," then `@`-mention
>   `pipeline-cost-analyzer` explicitly. The skill still works; you've just shown the manual path.

1. Open the **STAGING** workspace: `https://dbc-b2c3d4e5-f6a7.cloud.databricks.com` (Tier 2 target)
2. Open Genie Code (Agent Mode)
3. Open a **NEW** chat thread
4. Ask (frozen prompt — use verbatim): *"What are my top 5 most expensive Databricks jobs in the last 30 days?"*
5. Observe:
   - Skill name `pipeline-cost-analyzer` appears in the Agent Mode context (auto-loaded)
   - SQL runs against `system.billing.usage` + `system.lakeflow.jobs`
   - Returns a ranked table + 2–3 recommendations
6. Ask a follow-up: *"Which SKU is trending up?"* → verify skill-shaped answer continues

**Key message:** Auto-load via description matching. Zero manual wiring. Real data, real answer.

---

## Step D — Promote to Tier 3

**Story:** Skill widens to enterprise. Registry records approval chain.

1. `git checkout -b demo/step-d`
2. `git mv tier2/infrastructure/pipeline-cost-analyzer tier3/pipeline-cost-analyzer`
3. Update `registry.yaml`:
   - `tier: 2` → `tier: 3`
   - `approvals.council:` and `approvals.security:` — set each to an **authorized approver**
     from [`config/governance.yaml`](../config/governance.yaml) (e.g. council `platform-lead@greenwood.example.com`,
     security `security-lead@greenwood.example.com`). A name not on the allowlist fails the build —
     that's the point: sign-offs can't be self-attested. (To *show* the failure, first commit an
     unauthorized name like `nobody@example.invalid` and let the gate reject it, then correct it.)
   - Remove `domain:` field (T3 skills are org-wide)
4. Commit + push + open PR → show all gates pass (validate-meta requires council + security
   approvals **and** that each is authorized in `governance.yaml`)
5. Merge → watch sync: `sync-skills.sh 3` syncs to `/.assistant/skills/` on **all three** workspaces
   (dev + staging + prod) — a wider reach than the Tier 2 target, which was staging-only
6. Open a new Genie Code thread **in PROD** (`https://dbc-c3d4e5f6-a7b8.cloud.databricks.com`) — the
   skill now loads there too. It was only in staging as a T2 skill; as a T3 skill it's everywhere.

**Key message:** Tier promotion is a PR. Approval is recorded in registry. Sync widens reach from
one staged workspace (T2) to the whole fleet (T3) automatically.

---

## Step E — Deprecation

**Story:** Deprecated skill disappears from Genie Code.

1. `git checkout -b demo/step-e`
2. Update `registry.yaml` for `pipeline-cost-analyzer`:
   ```yaml
   deprecated: true
   removed_after: "2026-06-17"
   ```
3. `git mv tier3/pipeline-cost-analyzer archive/pipeline-cost-analyzer`
4. Commit + push + merge
5. Trigger prune: run `bash scripts/prune-deprecated.sh` (locally or as a scheduled ADO pipeline;
   set `DATABRICKS_HOST` + the SP M2M creds so it authenticates as the CI service principal)
6. Watch prune run `databricks workspace delete /.assistant/skills/pipeline-cost-analyzer` on
   **every** T3 workspace (dev + staging + prod) — it removes from exactly the workspaces sync published to
7. Open a **new** Genie Code thread in PROD → ask the same cost question
8. **Skill no longer auto-loads** — no skill-shaped answer

**Key message:** Deprecation is enforced, not documented. The repo is the source of truth.

> **Narrative note:** Run Step E *fast* — it's the **mechanism** (flip a flag, prune removes the
> skill from the workspace). Don't dwell on "governance is enforced" here; that lands harder as
> Step E2's payoff. Treat E as the ~60-second setup for E2.

---

## Step E2 — Ownership-Health Job (auto-deprecation PR)

**Story:** An ownerless skill triggers an automatic deprecation PR — no human has to notice.

> **The payoff line (say it):** "You just saw deprecation as a deliberate action. But the real
> win is you don't have to *remember* to do it — an ownerless skill nominates *itself* for
> deprecation. Governance that runs without anyone watching."

1. Create a throwaway branch: `git checkout -b demo/step-e2`
2. Add a minimal T2 skill entry to `registry.yaml` with **no `owner` field** (or an owner email not
   listed in `governance.yaml`):
   ```yaml
   - name: orphaned-analyzer
     tier: 2
     domain: infrastructure
     version: "1.0.0"
     deprecated: false
   ```
3. Commit + push (no PR needed — this simulates a skill that lost its owner after merge).
4. Run the health job locally: `bash scripts/ownership-health.sh`
   - Observe the report flagging `orphaned-analyzer` as ownerless.
   - Observe `scripts/open-deprecation-pr.sh` called automatically, opening a draft PR titled
     **"chore: auto-deprecate ownerless skill orphaned-analyzer"**.
5. Show the opened PR — it sets `deprecated: true` + `removed_after` 30 days out.
6. Point out: the PR itself passes all binding gates (lint, validate-meta, AI review). A human
   either merges it or reassigns an owner and closes it.

**Key message:** Governance is active, not passive. Ownerless skills are automatically nominated
for deprecation — the system enforces accountability without manual audits.

---

## Step F — Vendor portability (narrated)

**Story:** The CI is vendor-neutral. This environment runs on Azure DevOps only — this org's
GitHub (EMU) blocks hosted runners and environment connections — but the same `scripts/` port
to any CI unchanged.

1. Open `azure-pipelines.yml` and show that each step is a one-line `bash scripts/…` call —
   **zero logic in the CI YAML**.
2. Show `scripts/ai-review.sh` and `scripts/check-branch-protection.sh` — both still carry a
   `CI_SYSTEM=github` code path (PR comment via `gh`, branch check via the GitHub API).
3. **Say this out loud:** "Porting to GitHub Actions is a thin set of workflow YAMLs that call
   these exact scripts — no gate logic is rewritten. We don't ship them here only because this
   org's GitHub can't run pipelines, so there'd be nothing to demo against."

**Key message:** Vendor neutrality is structural — all logic lives in shared `scripts/`, so the
CI system is a swappable front-end. Azure DevOps is simply the one that can run here.

> **Don't make F its own act.** After five live steps, a talk-only closer deflates. Compress the
> whole point to one sentence, then pivot to the vision close below:
> "Every gate you just saw is a plain script — Azure DevOps is only the front-end we could run
> here; GitHub Actions calls the identical scripts, nothing is rewritten."

---

## Close — the forward-looking vision (one slide)

Leave the room with where this goes next, not a config file. Today the framework serves
**developers and workspace users**. The next frontier widens *who gets to contribute* without
changing any of the rails they just watched:

> "Imagine a consumer-role app — a clinician with **no workspace, no table access** describes a
> skill in plain language ('which of my diabetic patients missed their last A1c test'). An agent
> drafts the skill, they test it against a safe dataset, and on approval it enters this **exact**
> pipeline — same gates, same steward sign-off, same tiered reach. The governance you just saw
> doesn't change. We just open the front door to the domain experts who know what the skills
> should *do*."

*(Aspirational only — not built. The consumer entitlement + app-service-principal model makes it
feasible; see the parked design notes. Use it to end on vision, then stop.)*

---

## Verification Checklist ([§12 Success Criteria](specification.md#12-success-criteria))

Run through these before declaring the demo complete:

- [ ] 1. ADO PR triggers Azure Pipelines; lint + validate + skill-tests + ai-review all run and report
- [ ] 2. `scripts/` are vendor-neutral (narrated Step F) — the `github` code paths remain for portability
- [ ] 3. On merge, skill folder appears under `/.assistant/skills/` (STAGING for T2; all three for T3) — written by SP only, `TESTS.yaml` stripped
- [ ] 4. Fresh Genie Code thread auto-loads `pipeline-cost-analyzer` and answers with system table data
- [ ] 5. Deprecation + prune removes skill from its workspace(s); new thread no longer surfaces it
- [ ] 6. Developer direct write denied (test as a non-admin user, or verify via ACL inspection):
       `databricks workspace mkdirs /.assistant/skills/test-direct-write` → Expected: PERMISSION_DENIED
