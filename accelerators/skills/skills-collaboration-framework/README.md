# Skills Collaboration Framework

A governance **methodology** for AI skills on Databricks, with **one reference implementation**
(this repo) — an example of the pattern, not a product to adopt verbatim. It targets Databricks
**Genie Code** (Assistant Agent Mode): a skill travels from a developer's Git branch — via
**Azure Pipelines** here, though the CI logic is vendor-neutral and ports to GitHub Actions or any
CI (see [CI wiring](#ci-wiring)) — through CI gates and a human approval, and into every
user's Genie Code session. Adopt it incrementally (crawl → walk → run; see
[`docs/adoption-model.md`](docs/adoption-model.md)); it is an open, roadmap-aligned bridge toward
**Unity AI Gateway** skills ([`docs/roadmap-uc-skills.md`](docs/roadmap-uc-skills.md)).

**The core insight:** the runtime "allowlist" of skills a user can invoke is **not a separate
system** — it is literally a folder (`/.assistant/skills/`) inside each Databricks workspace,
and **the CI service principal is the only writer** to that folder. Git defines *what exists*;
the workspace folder defines *what users can use*; CI is the bridge between them.

```text
Developer → feature branch → PR (Azure DevOps; portable to GitHub)
  → CI gates:  lint + secret scan + metadata validation + AI review
  → human approval (steward / council) — the binding gate
  → merge to main
  → sync-skills.sh → /.assistant/skills/{skill}/
  → Genie Code auto-loads the skill via description matching
```

Nothing reaches a shared workspace without passing CI **and** a human approver. CI never
writes to `main`; every change — including automated deprecations — is a PR through the gate.

---

## Tier model

| Tier | Folder | Reach | Sync target | Gates |
|------|--------|-------|-------------|-------|
| **1 — Personal** | `tier1/{username}/{skill}/` | Author only | Never synced | lint + secret scan |
| **2 — Team** | `tier2/{domain}/{skill}/` | A domain's users | Domain workspace(s) | + metadata + AI review + **steward** approval |
| **3 — Enterprise** | `tier3/{skill}/` | Whole org | All workspaces | + **council + security** approval |

Tier = intended **reach**, declared by the author; a skill may be born at any tier. Skills
always land **flat** at `/.assistant/skills/{skill}/` in the workspace — the tier/domain folder
structure exists only in this Git repo. Team-to-team isolation is by **separate workspaces**
(mapped in `workspaces.json`), never by subfolders, because Genie Code only auto-loads from the
top level of the skills path.

The tier-2 domains in this reference are four neutral, cross-industry examples: `platform`
(infrastructure/cost engineering), `analytics` (BI & data science), `finance` (financial planning
& analysis), and `governance` (data governance & catalog stewardship). Swap them for your own org's
domains in `governance.yaml`, `CODEOWNERS`, and `workspaces.json`.

---

## Repository map — every file and its value

### Configuration — the source of truth (maintained by humans)

| File | Value it provides |
|------|-------------------|
| [`config/registry.yaml`](config/registry.yaml) | The **skill inventory + governance metadata** for every T2/T3 skill. Drives validation, sync, and pruning. One discoverable answer to "what skills exist, who owns them, what data do they touch?" |
| [`config/governance.yaml`](config/governance.yaml) | The **people-and-roles directory**: platform team, domain stewards, council, security. Doubles as the **owner allowlist** — only emails listed here are valid `owner`s or approvers. CI checks every sign-off against it. |
| [`config/workspaces.json`](config/workspaces.json) | The **routing table**: maps each tier/domain to the list of workspace URLs to sync to, plus the `skills_path`. The only file that changes when your workspace topology changes. |
| [`CODEOWNERS`](CODEOWNERS) | **Review routing**: sends each PR to the right reviewer by path, and protects the governance files (changes to them require platform-team review). |
| [`workspace-instructions/`](workspace-instructions/) | **Always-on, org-wide Assistant context** per workspace (the sibling of skills). Canonical text governed in Git, council-reviewed; **applied manually** today — see [its README](workspace-instructions/README.md). |

### Skills — the content

| Path | Value |
|------|-------|
| `tier1/{user}/{skill}/SKILL.md` | Personal sandbox skill. Never synced. |
| `tier2/{domain}/{skill}/SKILL.md` | Team skill. `SKILL.md` frontmatter is exactly `name` + `description`; the body is the agent guidance (instructions, example questions, SQL patterns). |
| `tier3/{skill}/SKILL.md` | Enterprise skill, available org-wide. |
| `archive/` | Where deprecated skills are retained for audit after removal. |

A skill is a **folder** whose required entry point is `SKILL.md` (the convention Genie Code
loads). The folder may also bundle **supporting files** referenced by the skill — e.g.
`patterns.md`, `scripts/deploy.py` — beside the `SKILL.md`; those are part of the one skill,
not separate skills. `validate-meta` enforces this: a loose markdown with no `SKILL.md` in its
folder is rejected (it would otherwise sync as an ungoverned skill).

### Automation — the CI logic (`scripts/`, maintained by the Platform Team)

All CI logic lives here; the CI YAML files are thin wrappers that call these. This is what
makes the framework **vendor-neutral** — the same scripts run under GitHub Actions or ADO.

| Script | Value |
|--------|-------|
| `new-skill.sh` | Scaffolds a new skill — arrow-key prompts for tier, domain, owner, classification, PII; writes a best-practice `SKILL.md` template (overview / when-to-use / instructions / examples / edge cases / data scope, per [Genie Code skill guidance](https://docs.databricks.com/aws/en/genie-code/skills#best-practices)) + a `registry.yaml` entry. |
| `lint-and-scan.sh` | Markdown + YAML + JSON lint and **gitleaks** secret scan. Runs at every tier. |
| `validate-meta.sh` / `_validate_meta.py` | The **hard metadata gate**: frontmatter shape, tier↔folder match, semver + bump-on-change, duplicate detection, **tier eligibility** (PII / regulated / write-mutation skills must be T3), **no leftover `TODO` placeholders in a T2/T3 skill**, and owner/approver authorization against `governance.yaml`. Advisory nudges: missing best-practice sections and weak descriptions. (`unity_catalog_scopes` is optional and cross-checked advisory-only — see below.) |
| `run-skill-tests.sh` / `_run_skill_tests.py` | **Per-skill regression tests**: static, behavior-oriented assertions from a `TESTS.yaml` beside each skill — `expect_tables` (deterministic) and `forbid_tables` (negative guardrail) checked against the skill's declared SQL. Skills without a `TESTS.yaml` are advisory-untested (never a hard fail), so it adopts incrementally. |
| `ai-review.sh` | **AI Skill Review**: an LLM scores the skill (clarity/safety/format) and posts a PR comment / build report. Hard-fails on a `fail` verdict; the numeric score is a **configurable dial** via `EVAL_GATE_MODE` (`advisory` / `human-review` / `auto-drop`, default `advisory`), with **per-tier overrides** `EVAL_GATE_MODE_T2` / `EVAL_GATE_MODE_T3` (ships advisory@T2, human-review@T3). |
| `sync-skills.sh` | Publishes changed skills to the workspace `skills_path` via `databricks workspace import-dir`. The **only writer** to the allowlist. |
| `prune-deprecated.sh` | Scheduled: removes skills whose registry entry is `deprecated` and past `removed_after` from every workspace. |
| `ownership-health.sh` / `_ownership_health.py` | Scheduled: flags **stale** skills (no commits within the tier's review interval) and **ownerless** skills (owner no longer in `governance.yaml`). |
| `open-deprecation-pr.sh` | For ownerless skills, opens an **automated, trunk-based deprecation-proposal PR** (CI never commits to `main`; the PR rides the same human gate). |
| `setup-branch-protection.sh` | One-time: configures the binding branch policy on `main` (build validation + Code-Owner review). |
| `check-branch-protection.sh` | CI self-check that **fails if the gate is off** — gatekeeps the gatekeeper. |

### CI wiring

| File | Value |
|------|-------|
| [`azure-pipelines.yml`](azure-pipelines.yml) | **The CI** (the live demo runs here). Stages: *Validate* (lint, metadata, per-skill regression tests, AI review, gate self-check), *Sync* (on merge to `main`), *OwnershipHealth* (scheduled). |

> **Why only Azure Pipelines?** The framework is vendor-neutral by design — all CI logic lives in
> `scripts/`, and both `check-branch-protection.sh` and `ai-review.sh` still carry a `github`
> code path (set `CI_SYSTEM=github`). A GitHub Actions port is a thin set of workflow YAMLs that
> call the same scripts. We don't ship them here because this org's GitHub (EMU) blocks hosted
> runners and environment connections, so a GitHub demo can't run — Azure DevOps is the live CI.
> The portability is real; only the second vendor's wiring is omitted for lack of a place to run it.

### Lint config & tests

| File | Value |
|------|-------|
| `.markdownlint.yaml`, `.yamllint.yaml` | Lint rules used by `lint-and-scan.sh`. |
| `.gitignore` | Ignores generated artifacts (e.g. the ownership-health report). |
| `tests/` | Bash test suites for the gate scripts (`test_validate_meta.sh`, `test_run_skill_tests.sh`, `test_ownership_health.sh`, `test_lint_and_scan.sh`, `test_ai_review_gate.sh`) + fixtures. Run them with `bash tests/test_validate_meta.sh`. |
| `tier{2,3}/…/TESTS.yaml` | Optional per-skill regression tests beside a `SKILL.md` — `expect_tables` / `forbid_tables` assertions run by `run-skill-tests.sh`. |

### Docs

| File | Value |
|------|-------|
| [`docs/specification.md`](docs/specification.md) | **Normative source of truth** — the rules CI enforces (tier eligibility, gates, testing, success criteria). Code cites its sections (`spec §2.2` etc.). |
| [`docs/operating-model.md`](docs/operating-model.md) | The customer-agnostic governance charter: roles, RACI, automate-vs-human, protected files, onboarding, identity-by-maturity. |
| [`docs/adoption-model.md`](docs/adoption-model.md) | The **crawl → walk → run** additive ramp — adopt incrementally, never rebuild. |
| [`docs/value-model.md`](docs/value-model.md) | A blank ROI **worksheet** the client fills in with their own rates/volumes. |
| [`docs/demo-runbook.md`](docs/demo-runbook.md) | Step-by-step script for demoing the live T1→T3 flow. |
| [`docs/roadmap-uc-skills.md`](docs/roadmap-uc-skills.md) | Three horizons → native UC Skills / Unity AI Gateway; only the publish target moves. |

---

## The recommended T1 → T3 workflow

1. **Build in Tier 1 (personal sandbox).** `bash scripts/new-skill.sh` → choose tier 1.
   Drop the folder into your own `/Users/<you>/.assistant/skills/` to dogfood it in Genie Code.
   No review; it reaches no one else. (In a dev → stg → prod topology, this is your **dev**
   workspace, where you may self-upload; stg/prod only ever receive CI-synced T2/T3 skills.)

2. **Promote to Tier 2 (team).** Open a PR moving the folder to `tier2/<domain>/<skill>/` and
   add/curate its `registry.yaml` entry. CI runs lint + metadata validation + AI review; the
   **domain steward approves** (the binding gate). On merge, `sync-skills.sh` publishes it to
   that domain's workspace(s); it appears in those users' Genie Code allowlist.

3. **Promote to Tier 3 (enterprise).** Open a PR moving it to `tier3/<skill>/`. Now
   **council + security** must approve, and `validate-meta` requires `approvals.council` and
   `approvals.security` to be recorded and authorized. On merge it syncs to **every** workspace.

4. **Maintain.** Any change to a skill requires a **version bump** (provenance). The scheduled
   ownership-health job flags stale skills so owners review-and-refresh them.

5. **Deprecate.** Set `deprecated: true` + `removed_after: <date>` in `registry.yaml` via a PR.
   `prune-deprecated.sh` removes it from every workspace after the date. If a skill becomes
   **ownerless** (owner leaves `governance.yaml`), the health job opens a deprecation PR
   automatically — a human still merges it.

---

## YAML config reference — what to set

### `registry.yaml` (per T2/T3 skill — maintained by the **Skill Owner**)

```yaml
skills:
  - name: pipeline-cost-analyzer        # must match SKILL.md frontmatter name
    tier: 2                             # must match folder placement
    version: 1.2.1                      # semver; MUST bump when SKILL.md changes
    owner: dana.lee@greenwood.example      # must be listed in governance.yaml
    domain: platform                    # one of the governance.yaml tier-2 domains (must be mapped in workspaces.json)
    description: Analyze DBU cost trends and job costs; recommend optimizations.
    data_classification: internal
    pii: false
    unity_catalog_scopes:               # OPTIONAL — forward-compat manifest for future UC Skills grants; advisory only, not a gate
      - system.billing.usage
      - system.lakeflow.jobs
    approvals:
      steward: dana.lee@greenwood.example         # T2: a steward for this domain
      council: ""                       # T3: a council member (date or email)
      security: ""                      # T3: a security reviewer
    deprecated: false
    removed_after: null                 # YYYY-MM-DD once deprecated
```

### `governance.yaml` (maintained by the **Platform Team**, per below)

```yaml
platform_team:
  - dana.lee@greenwood.example
tier2:
  stewards:                             # one steward list per domain
    platform:   [dana.lee@greenwood.example, sam.rivera@greenwood.example]
    analytics:  [dana.lee@greenwood.example, sam.rivera@greenwood.example]
    # platform, analytics, finance, governance
tier3:
  council:  [dana.lee@greenwood.example, sam.rivera@greenwood.example]
  security: [dana.lee@greenwood.example, sam.rivera@greenwood.example]
```

> In this demo every domain (and both T3 roles) is stewarded by the same real people so any skill
> can be signed off. In production each domain names its own steward and council ≠ security.

The **owner-eligible set** is the union of every email anywhere in this file.

### `workspaces.json` (maintained by the **Platform Team**)

```json
{
  "skills_path": "/.assistant/skills",
  "tier2": { "infrastructure": ["https://<staging>.cloud.databricks.com"], "...": [] },
  "tier3": { "workspaces": ["https://<dev>...", "https://<staging>...", "https://<prod>..."] }
}
```

> This demo maps tiers to a dev→staging→prod SDLC: every T2 domain → the staging workspace, T3 →
> all three. In a one-workspace-per-domain topology each domain lists its own workspace(s) instead.

A domain may list multiple workspace URLs (one per environment or region).

---

## Who maintains what — mapped to the Governance Framework roles

The roles from the Governance Framework deck map directly onto concrete files/values in
this repo. This is the operational answer to "what does each team own?" (role → *accountability*
lives in [`docs/operating-model.md`](docs/operating-model.md#roles); this table is role → *files*.)

| Role (deck) | Files & values they maintain |
|-------------|------------------------------|
| **Platform Team** | The framework itself: `scripts/`, `azure-pipelines.yml`, `CODEOWNERS`, `workspaces.json`, the `platform_team` list in `governance.yaml`, branch protection (`setup-branch-protection.sh`), and the sync service principal. Also **applies** approved `workspace-instructions/` to each workspace (manual step today). The single answer to "who owns this?" |
| **Skills Council** | The `tier3.council` list in `governance.yaml`; records `approvals.council` on T3 skills; reviews `workspace-instructions/` (always-on, org-wide context); quarterly review of the framework and metrics. |
| **Domain Stewards** | Their own domain's list under `tier2.stewards` in `governance.yaml`; records `approvals.steward` on T2 skills in their domain. |
| **Security** | The `tier3.security` list in `governance.yaml`; records `approvals.security` on T3 skills. |
| **Skill Owners** | Their skill's `registry.yaml` entry (the `version` bump, `description`, `unity_catalog_scopes`, `data_classification`, and deprecation fields) and the `SKILL.md` content. |
| **Consumers** | No files — they use skills in Genie Code and provide feedback / usage signal. |

See [`docs/operating-model.md`](docs/operating-model.md) for the full RACI and the
protected-files change-control model.

---

## Validation checks (`validate-meta.sh` — hard, fails the build)

- Frontmatter is exactly `name` + `description`; folder tier matches `registry.yaml`.
- Every T2/T3 skill has a semver **`version`**, and a skill whose `SKILL.md` changed in a PR must
  **bump** it (author-set provenance — CI never pushes back).
- **No duplicate** skill names or folders (they would collide in the flat allowlist).
- **Approvals are recorded *and* authorized** against `governance.yaml` — sign-offs can't be
  self-attested with an arbitrary string.
- Every T2/T3 skill's **`owner`** is listed in `governance.yaml`.
- **Tier eligibility** ([spec §2.2](docs/specification.md#22-tier-eligibility-normative)): a Tier-2 skill may **not** declare `pii: true` or
  `data_classification: regulated`, and its SQL may **not** run a write/mutation statement
  (`INSERT`/`UPDATE`/`DELETE`/`MERGE`/DDL/`GRANT`/…). Those must be **Tier 3** (enterprise gate).
- **No unfilled `TODO` placeholders** in a T2/T3 `SKILL.md` — a scaffold must be authored before it
  ships. (Tier 1 sandbox skills are exempt — advisory only there.)

Advisory (printed, never blocks): highly similar descriptions (possible duplication); a T2/T3 skill
**missing recommended best-practice sections** (overview / when-to-use / instructions / examples —
matched by concept, so a well-authored skill in its own wording passes clean); a **very short
description** (weak Genie Code auto-load signal); SQL that couldn't be parsed; and — when a skill
declares **`unity_catalog_scopes`** — any SQL table outside that declared footprint.

> **`unity_catalog_scopes` is optional, and never a runtime access control.** A skill's data
> footprint is documented in prose in its `SKILL.md`; **runtime access is enforced by Unity Catalog
> grants on the executing principal** — the user or service principal running Genie Code — not by
> the skill. A skill cannot grant itself access its principal lacks. The field is therefore *not*
> required at authoring time and the scaffolder does not prompt for it. When an author *does* declare
> scopes, it serves as the **forward-compat manifest** for future **UC Skills** grants (when UC
> Skills ships, these become the actual `GRANT READ ON SKILL … TO <group>` grants and
> `registry.yaml` is the provisioning manifest — zero rework; see
> [`docs/roadmap-uc-skills.md`](docs/roadmap-uc-skills.md)), and CI cross-checks the declared list
> against the `SKILL.md` SQL as an **advisory** warning only.

> **What CI does *not* do:** judge whether a skill *guides an agent well*. That is deliberately a
> human reviewer's job. CI verifies the artifacts are well-formed and in-bounds; the **governance
> layer** (steward / council / security) judges quality. Automated accuracy eval is **off by
> default** — it is a configurable dial (`EVAL_GATE_MODE`), not a fixed stance: start `advisory`,
> turn it up to `human-review` or `auto-drop` per domain as you mature. Per-skill **usage
> telemetry** is a future capability (the `system.access.assistant_events` table records adoption
> today, but not per-skill attribution).

---

## CI/CD & secrets

CI runs on **Azure Pipelines** (all logic in `scripts/`, so it ports to any CI — see
[CI wiring](#ci-wiring)). Auth is **OAuth M2M** (service-principal client credentials) — PATs are
disabled on the demo workspace.

**Azure DevOps** — a `databricks-skills` variable group (Pipelines → Library) holds
`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `AI_ENDPOINT_NAME`, and the secret-flagged
`DATABRICKS_SECRET` (mapped to `DATABRICKS_CLIENT_SECRET` per step). PR comments use
`$(System.AccessToken)`; on merge the `eval_score` is surfaced in the build's
"AI Skill Review" summary and as a build tag — **never** committed back to protected `main`.

A **Build Validation** branch policy on `main` (pointing at `azure-pipelines.yml`) makes the
gate binding. `AI_ENDPOINT_NAME` defaults to a small model (e.g. `databricks-claude-haiku-4-5`).

**Eval gate dial.** `MIN_EVAL_SCORE` (default `0.8`) sets the threshold; `EVAL_GATE_MODE` decides
what a below-threshold score does:

| `EVAL_GATE_MODE` | Below-threshold `eval_score` | Blocks merge? |
|------------------|------------------------------|---------------|
| `advisory` (default) | warns in the report/PR comment | no |
| `human-review` | warns **and** emits a `::needs-human-review::` marker for a steward | no |
| `auto-drop` | fails the build | yes |

A `fail` **verdict** (any dimension < 0.5) is a hard gate that blocks in **every** mode. Set
`EVAL_GATE_MODE` in the pipeline env (ADO `databricks-skills` variable group)
— it defaults to `advisory`, preserving today's behavior.

**Per-tier gate ([spec §16.3](docs/specification.md#163-ai-review--the-smart-gate-normative)).** The recommended posture is *advisory at Tier 2, blocking at
Tier 3*. Set `EVAL_GATE_MODE_T2` / `EVAL_GATE_MODE_T3` to override the mode per tier; each falls
back to the global `EVAL_GATE_MODE` when unset. The pipeline ships with `EVAL_GATE_MODE_T2=advisory`
and `EVAL_GATE_MODE_T3=human-review` — a Tier-3 skill below threshold flags for a steward while a
Tier-2 one only warns. The `fail`-verdict hard gate still applies at every tier regardless.

---

## Approval enforcement (branch protection)

`CODEOWNERS` only *requests* reviewers; the **binding** gate is the branch policy on `main`
(ADO Build Validation + required reviewers / GitHub *Require review from Code Owners*).
`check-branch-protection.sh` runs in CI and fails if the policy is missing — so the gate can't
be silently switched off. Tier-3 council/security approvals are additionally enforced by
`validate-meta.sh`.

> The recommended model (see `operating-model.md`) prohibits the author from self-approving
> protected-file changes — in a multi-person org a second reviewer is required. This single-
> maintainer demo relaxes that one policy so the author can merge.

---

## Onboarding a new org

1. Name the Platform Team → add them to `governance.yaml.platform_team`.
2. Populate `governance.yaml` (stewards per domain, council, security) and the matching
   `CODEOWNERS` / `workspaces.json` domains.
3. `bash scripts/setup-branch-protection.sh` (sets build validation + Code-Owner review on `main`).
4. Open a trivial PR; confirm `check-branch-protection` is green and the gate blocks merge until reviewed.

## Scope — in, and deliberately out

This is a governance **methodology** with one **reference implementation** (this repo) — not a
product to adopt verbatim. What it governs, and what it intentionally does not:

**In scope:** AI skills as governed artifacts (AI Dev Kit skills, custom agents / MCP outputs,
Genie Code & Genie Spaces outputs, prompt libraries); their lifecycle (propose → build → review →
publish → operate → retire); reusability, safety (data classification + UC), and quality gates.

**Out of scope — by design (stated, not apologized for):**

- **MCP server governance.** Databricks MCP is Managed Apps / external-via-UC-connection and is
  already guarded by Unity Catalog. The ungoverned surface this framework addresses is the **skill
  artifact**, not MCP.
- **Multi-metastore / data residency.** A customer deployment detail (`workspaces.json` topology),
  not a concern of the framework itself.
- **Automated accuracy eval as a default.** It's a configurable dial (`EVAL_GATE_MODE`), **off by
  default** — see *Eval gate dial* above. Turn it up as a domain matures.

Two honesty notes carried throughout: (1) a skill **documents intent** — Unity Catalog grants on
the executing principal enforce data access at runtime; (2) this is an open, roadmap-aligned
**bridge** to Unity AI Gateway skills (below), designed to converge with it, not replace it.

## UC Skills roadmap

See [`docs/roadmap-uc-skills.md`](docs/roadmap-uc-skills.md). The authoring + governance layer
migrates cleanly to native UC Skills / Unity AI Gateway — only the `sync-skills.sh` publish target
changes. Adopt it incrementally via the [adoption model](docs/adoption-model.md).
