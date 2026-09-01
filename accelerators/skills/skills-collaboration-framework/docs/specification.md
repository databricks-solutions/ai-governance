# Skills Collaboration Framework — Specification

The normative source of truth for the framework's rules. Prose docs (README, operating-model,
adoption-model) explain and motivate; **this file defines what is enforced**. Where code cites a
section (e.g. `spec §2.2`), it points here.

Section numbers align with the internal design doc this distills; the framework implements the
sections below. Each **normative rule** names the script that enforces it, so the spec and the
gate can never drift.

---

## 1. Purpose & scope

A skill is a folder containing a `SKILL.md` entry point (plus optional supporting files) that
Databricks Genie Code auto-loads by description matching. This framework governs how skills are
authored, reviewed, promoted across reach tiers, synced to workspaces, and retired — using a Git
repository as the single source of truth and CI as the enforcement layer.

**In scope:** skill metadata, tier eligibility, approval authorization, per-skill regression
tests, workspace sync, deprecation/prune, ownership health.
**Out of scope:** judging whether a skill *guides* an agent well (a human reviewer's job — steward
/ council / security sign-off), and any runtime access control (Unity Catalog enforces access on
the executing principal, independent of a skill's declared tier).

---

## 2. Tiers

### 2.1 The tier model

Tier is a **reach** declaration, not a runtime boundary.

| Tier | Folder | Reach | Sync target | Gates |
|------|--------|-------|-------------|-------|
| **1 — Personal** | `tier1/{user}/{skill}/` | Author only | **Never synced** by CI | lint + secret scan |
| **2 — Team** | `tier2/{domain}/{skill}/` | A domain's users | The domain's workspace(s) | + metadata + regression tests + AI review + **steward** approval |
| **3 — Enterprise** | `tier3/{skill}/` | Whole org | All enterprise workspace(s) | + **council + security** approval |

Skills sync **flat** to `skills_path` (`/.assistant/skills/{skill}/`); the tier/domain folder
structure lives only in Git. Promotion is a `git mv` between tier folders plus a `registry.yaml`
edit. *Enforced by:* `_validate_meta.py` (`check_skill_file_convention`), `sync-skills.sh`.

### 2.2 Tier eligibility (normative)

A Tier-2 skill **MUST NOT**:
- declare `pii: true`,
- declare `data_classification: regulated`, or
- contain SQL that runs a **write/mutation** statement — `INSERT`, `UPDATE`, `DELETE`, `MERGE`,
  `TRUNCATE`, `DROP`, `CREATE`, `ALTER`, `REPLACE`, `GRANT`, `REVOKE`, `COPY INTO`.

Any skill meeting one of these conditions **MUST be Tier 3** (enterprise — council + security
approval). Read-only (SELECT-only) skills over non-PII, non-regulated data are eligible for
Tier 2. *Enforced by:* `_validate_meta.py` (`check_write_eligibility`, and the pii/regulated
checks in `validate_skill`).

### 2.3 Domain mapping (normative)

Every non-deprecated Tier-2 skill's `domain` **MUST** be mapped in `workspaces.json` (`tier2`),
and if any Tier-3 skill exists, `tier3.workspaces` **MUST** be non-empty. This guarantees a
merged skill actually reaches a workspace at sync time. *Enforced by:* `_validate_meta.py`
(`check_domain_mapped`), which shares the resolver `_workspaces.py` with sync and prune.

---

## 10. Testing

### 10.1 Framework tests

The framework's own scripts are covered by `tests/test_*.sh` (pure, no workspace/endpoint).

### 10.2 Per-skill regression tests (normative)

A Tier-2/Tier-3 skill **MAY** ship a `TESTS.yaml` beside its `SKILL.md`. Tests assert on what the
skill *does* — the tables its SQL references (`expect_tables`) and the tables it must never touch
(`forbid_tables`) — **not** on the literal wording of any generated natural-language output
(fragile against model drift, explicitly out of scope). Skills without a `TESTS.yaml` are reported
**untested (advisory)**, never failed, so the harness can be adopted incrementally.
*Enforced by:* `_run_skill_tests.py` (static SQL extraction shared with `_validate_meta.py`).

---

## 12. Success criteria

A deployment is correct when:

1. A PR triggers CI; lint + validate-meta + skill-tests + ai-review all run and report.
2. `scripts/` are vendor-neutral — the CI system is a swappable front-end (the `github` code
   paths remain for portability even where only Azure DevOps runs).
3. On merge, the skill folder appears under `skills_path` (DEV for T2, PROD for T3), written by
   the CI service principal only, with `TESTS.yaml` stripped.
4. A fresh Genie Code thread auto-loads the skill and answers from real data.
5. Deprecation + prune removes the skill from its workspace(s); a new thread no longer surfaces it.
6. A developer cannot write to `skills_path` directly (only the SP can) — verified by ACL.

The demo runbook's verification checklist (`docs/demo-runbook.md`) is the operational form of this
section.

---

## 16. Gates & CI

### 16.1 Hard gates (block the build)

Frontmatter is exactly `name` + `description`; folder tier matches registry tier; required
registry fields present; semver `version`; unique skill/folder names; no unfilled `TODO` in a
T2/T3 skill; tier eligibility (§2.2); domain mapping (§2.3); approvals recorded **and authorized**
against `governance.yaml`; a changed skill's version is bumped. *Enforced by:* `_validate_meta.py`.

### 16.2 Advisory checks (report, never block)

Near-duplicate descriptions; missing recommended body sections; weak/short description;
`unity_catalog_scopes` out-of-scope SQL (an optional forward-compat manifest, **not** a runtime
control); skills lacking a `TESTS.yaml`.

### 16.3 AI review — the smart gate (normative)

Changed T2/T3 `SKILL.md` files are scored by an LLM (clarity / safety / format) via the Databricks
AI Gateway. Handling of the result is governed by `EVAL_GATE_MODE`, resolvable per tier:

| Mode | A `verdict: fail` (any dimension < 0.5) | A below-threshold `eval_score` |
|------|------------------------------------------|--------------------------------|
| `advisory` | **blocks** (hard, every mode) | warns only |
| `human-review` | **blocks** | warns + emits a `::needs-human-review::` marker |
| `auto-drop` | **blocks** | **blocks** |

`verdict: fail` is an unconditional hard gate in every mode. The recommended posture is
**advisory at Tier 2, human-review at Tier 3** (`EVAL_GATE_MODE_T2` / `EVAL_GATE_MODE_T3` override
the global default). The `eval_score` is surfaced in the build report and build tags on merge —
**never** written back to `registry.yaml`, because `main` is branch-protected and CI cannot push
to it. *Enforced by:* `ai-review.sh` (`gate_decision`, `resolve_gate_mode`).
