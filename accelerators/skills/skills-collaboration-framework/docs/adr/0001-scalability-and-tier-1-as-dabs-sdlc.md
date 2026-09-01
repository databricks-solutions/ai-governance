# ADR-0001: Scalability to 1000+ users, and Tier 1 as the DABs dev→staging→prod model

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** Platform team (`cedric.boisvert@databricks.com`)
- **Related:** [specification §2](../specification.md#2-tiers),
  [operating-model — Tier-1 sandbox isolation](../operating-model.md#tier-1-sandbox-isolation-deliberate-choice--recorded),
  [adoption-model](../adoption-model.md)

## Context

Two questions surface whenever this framework is shown to a large org:

1. **"What's the scalability of this repo for an organization of 1000 users?"**
2. **"Would you truly have 1000 subfolders in `tier1/`?"**

The second is the sharper one, and it lands on the weakest part of the *current* implementation.
Today Tier 1 is a committed directory: `tier1/{user}/{skill}/`. That is a **demo convenience**,
not a scale design. This ADR records why the demo was built that way, why committed Tier-1
subfolders do not scale, and the target model: **Tier 1 should mirror the Databricks Asset
Bundles (DABs) dev→staging→prod SDLC** — local dev is pushed directly, only staging is automated
for UAT, and prod is reached only through the gated promotion path.

We separate two things that are easy to conflate: the **governance model** (which scales) and a
few **implementation choices** (which are demo-shaped and must change for 1000 users).

## Decision

### 1. Tier 1 follows the DABs SDLC: local dev, automated staging (UAT), gated prod

The tier ladder is the same lifecycle a Databricks engineer already knows from Asset Bundles:

| DABs stage | Skills tier | Who deploys | How |
|------------|-------------|-------------|-----|
| **dev** | **Tier 1** | the developer, from their **local CLI** | direct upload to the dev workspace's `/.assistant/skills/` — **no CI, no commit required** |
| **staging** | **Tier 2** | **CI** on merge | automated sync to the domain's staging workspace for team **UAT / integration** |
| **prod** | **Tier 3** | **CI** on merge, after **council + security** sign-off | fan-out to all enterprise (prod) workspaces |

The governing principle, stated the way a DABs user expects it:

> **Dev is pushed directly from the developer's own local CLI. Only staging is automated (for
> UAT). Prod is never reached except through the gated promotion path.**

This means the **target-state Tier 1 is local-only** — a developer scaffolds a skill and
`databricks workspace import-dir`s it straight to their own dev workspace. It enters Git *only*
when they promote it to Tier 2 (a normal PR into a domain). There are **no committed
`tier1/{user}/` subfolders** in the target model, so the "1000 subfolders" problem does not exist:
the answer to the question is **no**.

### 2. What stays; what changes

**Stays (scales as-is):** tier = reach; promotion-by-PR; config-driven fan-out
(`workspaces.json`); per-domain review via CODEOWNERS; the vendor-neutral `scripts/` layer. None
of these care whether there are 10 users or 10,000.

**Changes for 1000 users:**

| Bottleneck | Why it breaks at scale | Target fix |
|------------|------------------------|------------|
| **Committed `tier1/{user}/` subfolders** | Monorepo churn from throwaway experiments; dead-experiment noise; the CODEOWNERS backstop makes one team nominally review 1000 people's scratch space | **Tier 1 becomes local-only** (DABs dev). It enters Git only on promotion to T2. |
| **Monolithic `registry.yaml`** | *Every* skill PR edits the same file → write contention / merge conflicts; hundreds of entries in one YAML | **Co-locate metadata** as a per-skill `skill.meta.yaml` beside each `SKILL.md`; CI aggregates. Each PR then touches only its own files. |
| **Flat `/.assistant/skills/` namespace** | Genie Code auto-loads by matching *every* skill's description at the top level of a workspace; hundreds in one workspace → routing ambiguity and degraded auto-load | **Deploy the real one-workspace-per-domain topology** (below), so each workspace sees only its domain's T2 skills + the small enterprise T3 set. |

### 3. Namespace math is the real scalability answer

Auto-load quality depends on how many skill descriptions Genie Code must disambiguate **in a
single workspace** — not on the org's total skill count. Tiering is what keeps that number small:

- In the **real** topology, a given workspace holds **its own domain's Tier-2 skills** (a curated
  handful per team) **plus the enterprise Tier-3 set** (which must stay small — dozens, not
  hundreds; council + security approval is exactly what enforces that scarcity).
- So a user in the ED workspace matches against ~15–25 skills, **regardless of how many skills the
  1000-person org has authored in total.** The org scales *horizontally across workspaces*; no
  single namespace saturates.

**Tiering is not only governance — it is the mechanism that keeps each per-workspace namespace
small enough for auto-load to stay accurate.**

## Why the demo was built the way it is

The demo deliberately collapses the model onto **three greenwood workspaces (dev / staging /
prod)** to *teach the tier methodology* with the fewest moving parts:

- **Committed `tier1/{user}/` folder.** Committing Tier 1 lets the demo show the *promotion path*
  (`git mv tier1/… → tier2/…`) and gives T1 its lint + secret-scan gates on-screen. A truly
  local-only Tier 1 has nothing to *show* in a repo walkthrough — so the demo trades the scale
  design for a visible one. This is a **teaching shortcut, recorded as such.**
- **All Tier-2 domains → one staging workspace.** With only three workspaces we cannot give each
  of eleven domains its own, so every domain syncs to STAGING and Tier 3 fans out to all three.
  This models reach as a **dev→staging→prod lifecycle** instead of one-workspace-per-domain — the
  exact DABs framing above — which is *why the SDLC analogy is the demo's backbone*.
- **Single `registry.yaml`.** Fine for ~13 demo skills; it makes the governance metadata legible
  on one screen. It would be a merge-contention hotspot at hundreds of skills.

Each shortcut buys on-screen clarity at the cost of scale. The tier=reach model, the scripts, and
the CI are **identical** in the demo and at scale — **only the topology config (`workspaces.json`)
and the Tier-1 storage location change.**

## Consequences

### Positive

- The honest answer to "1000 subfolders?" is **no** — and the reason (Tier 1 = local DABs dev)
  reinforces the tier methodology rather than apologizing for it.
- The scaling story is concrete: per-workspace namespace stays small because tiering bounds it.
- The migration path is config- and convention-level, not a rewrite: move T1 out of Git, split
  the registry into per-skill files, deploy one-workspace-per-domain. Scripts/CI unchanged.

### Negative / tradeoffs

- **Local-only Tier 1 loses its committed gates.** A skill only gets lint + secret-scan once it is
  promoted to Tier 2. Accepted: at 1000 users, not carrying everyone's sandbox in the monorepo is
  worth more than gating scratch code. (This also *cleanly resolves* the earlier "you are the sole
  owner of Tier 1" tension — it is literally true when T1 never touches the shared repo.)
- **Per-skill metadata files** need a CI aggregation step and a one-time migration from the single
  `registry.yaml`. Not yet built.
- The demo repo will continue to show a committed `tier1/` for teaching; readers must understand
  (via this ADR) that it is not the scale target.

## The one-paragraph answer (for the room)

> The governance model scales — tiering keeps each workspace's skill namespace small, which is
> what Genie Code auto-load needs. Three implementation choices are demo-shaped and I'd change them
> for 1000 users: **Tier 1 should be local-only, exactly like the DABs dev stage — pushed straight
> from the developer's CLI, never committed — so no, you would not have 1000 subfolders**; the
> registry should be per-skill files, not one YAML, to kill merge contention; and you deploy
> one-workspace-per-domain, not the demo's single staging target. Only staging is automated (for
> UAT) and prod is reached only through the gated promotion path — the same dev→staging→prod SDLC
> a Databricks engineer already knows from Asset Bundles. The scripts and CI don't change for any
> of that — only the topology config does.
