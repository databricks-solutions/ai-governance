# Skills Governance — Operating Model

Customer-agnostic charter for who owns the AI-skills framework and how gatekeeping works.
Names roles, not people; the concrete people live in `governance.yaml`.

## Roles

| Role | Accountable for |
|------|-----------------|
| **Platform Team** | The framework itself: the repo, CI, `governance.yaml`, the sync service principal, and branch protection. The single answer to "who owns this?" |
| **Skills Council** | Tier-3 (enterprise) approval; quarterly review of metrics and the framework. |
| **Domain Stewards** | Tier-2 approval for their domain; they know their data and their teams. |
| **Security** | Tier-3 approval alongside Council (the `tier3.security` sign-off); the safety/data-exposure lens on enterprise skills. |
| **Skill Owners** | An individual skill's lifecycle, including review and retirement. |
| **Consumers** | Use skills in Genie Code; provide feedback and usage signal. |

This table is role → *accountability*. For role → *the concrete repo files each maintains*, see
the mapping table in the [README](../README.md#who-maintains-what--mapped-to-the-governance-framework-roles).

## Lifecycle RACI

| Stage | Responsible | Accountable | Consulted | Informed |
|-------|-------------|-------------|-----------|----------|
| Propose | Author | Skill Owner | Steward | Platform Team |
| Build | Author | Skill Owner | — | — |
| Review | Steward / Council | Platform Team | Security | Author |
| Operate | Skill Owner | Platform Team | — | Consumers |
| Retire | Skill Owner / automation | Platform Team | Steward | Consumers |

## What is automated vs. human-reviewed

| Gate | How |
|------|-----|
| Lint + secret scan | CI-automated (`lint-and-scan.sh`) |
| Frontmatter / tier / version / duplicates | CI-automated (`validate-meta`) |
| Unity Catalog data-footprint check (optional scopes; advisory) | CI-automated (`validate-meta`) |
| Tier eligibility (PII / regulated / write → T3) | CI-automated (`validate-meta`) |
| Per-skill regression tests (expect/forbid tables) | CI-automated (`run-skill-tests`) |
| Owner resolves to a real person | CI-automated (`validate-meta` against `governance.yaml`) |
| Approver authorized for tier/domain | CI-automated (`validate-meta` against `governance.yaml`) |
| Branch protection is on | CI-automated (`check-branch-protection.sh`) |
| Stale / ownerless detection | CI-automated, scheduled (`ownership-health.sh`) |
| **Approve a skill for a tier** | **Human review** (steward / council / security) |
| **Approve an auto-deprecation** | **Human review** (the auto-PR rides the same gate) |
| **Judge whether a skill guides an agent well** | **Human review** (deliberately not automated) |

## Ownership model

- The **Platform Team** owns the framework and is named in `governance.yaml.platform_team`.
  It automates most gatekeeping and reviews the rest.
- Each **Skill Owner** owns one skill; an owner who leaves `governance.yaml` makes their
  skills *ownerless*, which the scheduled health check proposes for deprecation (via PR).
- Trunk-based: every change to `main` — including automated deprecations — is a feature
  branch + PR through the binding gate. CI never writes to `main`.

## Tier-1 sandbox isolation (deliberate choice — recorded)

`Tier 1` is a **reach** declaration, not a runtime boundary: Unity Catalog grants attach to the
identity executing a query, not to the tier a skill claims. A Tier-1 skill run under a developer's
own identity can reach anything that identity can — so "Tier 1 = no production data" must be backed
by a deliberate isolation control, not assumed.

**This deployment's choice: a dev→staging→prod SDLC across dedicated workspaces (the strongest
option).** Tier 1 is self-uploaded to the **greenwood DEV workspace** (`dbc-a1b2c3d4-e5f6`) and
dogfooded there; Tier 2 is CI-synced to the **greenwood STAGING workspace** (`dbc-b2c3d4e5-f6a7`)
for team integration; Tier 3 (enterprise) fans out to **all three** workspaces (dev + staging +
`dbc-c3d4e5f6-a7b8` prod) so enterprise skills are available everywhere. Because DEV is a distinct
workspace with its own catalogs and grants, Tier-1 experimentation cannot reach production data
through a developer's identity — the isolation is topological, not merely policy.

This mapping is the single knob (`workspaces.json`): every T2 domain → STAGING, `tier3.workspaces`
→ [dev, staging, prod]. The CI service principal must be entitled in **all three** workspaces
(account-level OAuth M2M) with `CAN_MANAGE` on `skills_path`.

> With only three demo workspaces we model reach as an SDLC lifecycle rather than one-workspace-per-domain.
> In a real Greenwood topology each domain would map to its own workspace(s); only `workspaces.json` changes —
> the scripts and CI do not.

> [!NOTE]
> **At 1000+ users, Tier 1 becomes local-only** — pushed straight from the developer's CLI to
> their dev workspace, like the DABs `dev` stage, and committed to Git only on promotion to Tier 2.
> The committed `tier1/{user}/` folder is a demo teaching choice, not the scale target. See
> [ADR-0001](adr/0001-scalability-and-tier-1-as-dabs-sdlc.md) for the full scalability rationale.

## Identity by maturity

Authorization hardens as adoption climbs the ramp (see [`adoption-model.md`](adoption-model.md)),
but the auditable record never moves:

- **Crawl / Walk — string authorization.** `governance.yaml` lists the actual people (emails) per
  role. `validate-meta` checks every owner/approver against it. Simple, readable, and enough to
  start in days.
- **Run — group authorization.** Wire **Entra / ADO groups** into the branch policy
  (required-reviewer groups) so membership — not a hand-edited list — decides who can approve.
- **`governance.yaml` remains the record of intent** at every stage: it documents who *should* hold
  each role and is what CI validates against, even once group membership is the live gate.

## Protected files (change control)

Some files govern the framework itself: `governance.yaml`, `CODEOWNERS`, `registry.yaml`,
and `workspace-instructions/` (always-on, org-wide Assistant context — highest blast radius,
so council-reviewed).
Git cannot prevent anyone from *editing* a file in their own branch — control is over what
*merges*. These files are protected by **process, not a file lock**:

- **Path-scoped required review.** Any PR touching a protected file must be approved by the
  Platform Team before merge. On GitHub this is `CODEOWNERS` + "Require review from Code
  Owners"; on Azure Repos it is an "Automatically included reviewers" branch policy scoped to
  those paths, marked required. A contributor may *propose* a change; only the Platform Team
  can *approve* it.
- **No self-approval.** Branch protection requires approval from someone other than the
  author (ADO: "Prohibit the most recent pusher from approving") so an author cannot merge
  their own change to a protected file.

This is the same model as every other change — propose by PR, merge only on authorized review —
applied with a named, file-specific reviewer for the files that govern the system.

## Onboarding checklist

1. Name the Platform Team; add them to `governance.yaml.platform_team`.
2. Populate `governance.yaml` (stewards per domain, council, security).
3. Run `scripts/setup-branch-protection.sh` (sets build validation + Code-Owner review on `main`).
4. Open a trivial PR and confirm the `check-branch-protection` job is green and the gate blocks merge until reviewed.
