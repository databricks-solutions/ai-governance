# Accelerator — Agent Skills

Build, govern, and deploy Agent Skills in Genie Code as a runtime allowlist and tiered registry. A ~3-hour deep dive that transforms ad-hoc prompt instructions into registered, versioned, security-reviewed skills with owners, data scope, and evals.

Agent Skills are markdown files in `~/.assistant/skills/` that extend the Databricks Assistant with custom instructions and examples. The **allowlist is the governance enforcement point** — what's in the folder is invokable; what's not, isn't. This is hard enforcement: no admin can override, no user can circumvent. Tier 1 (personal) stays zero-friction so teams don't route around governance; friction scales with risk as you move to Tier 2 (peer-reviewed, limited data scope) and Tier 3 (security-reviewed, full audit, regulated data).

## What you'll prove

Understand the three-layer instruction model (user instructions, workspace instructions, Agent Skills) and the allowlist enforcement point · build and place a minimal skill in `~/.assistant/skills/` · verify it loads in the Agent Skills settings and test the allowlist · classify it into a tier + write a registry.yaml entry · understand the GitHub PR-gate workflow (lint, secret scan, eval suite) · build a minimal eval with golden Q&A + LLM judge · understand data classification and secret-scan gates · understand deployment via GitHub Action import-dir and retirement.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`build_a_skill.py`](build_a_skill.py) | Hands-on lab: scaffold a skill.md, write a registry.yaml entry, run a minimal eval (3–5 golden Q&A scored by an LLM-as-judge), and a simple secret-scan over the skill text. |

## The production framework (submodule)

This repo vendors the real, batteries-included implementation as a submodule at the repo root:
[`skills-collaboration-framework/`](../../skills-collaboration-framework). It ships the tiered
registry (`tier1/`, `tier2/`, `tier3/`, `config/registry.yaml`), the CI gates
(`scripts/lint-and-scan.sh`, `validate-meta.sh`, `run-skill-tests.sh`, `ai-review.sh`), the
allowlist sync (`scripts/sync-skills.sh`), ownership-health tooling, and a
[`docs/demo-runbook.md`](../../skills-collaboration-framework/docs/demo-runbook.md). Clone it
(`git submodule update --init`) and open a PR to watch the gates fire — that is the non-app,
production route. The notebook below is the lightweight hands-on primer that teaches the same
concepts before you adopt the framework.

## Prerequisites

- A SQL warehouse and an existing Unity Catalog catalog + schema.
- Write permission to create files in your home directory (`~/.assistant/skills/`).
- Access to a Databricks foundation-model endpoint for the eval step.
- Basic familiarity with YAML and markdown.

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open `build_a_skill.py`, set the widgets at the top to your workspace, and run top to bottom. The skill creation and eval steps make workspace changes; everything else is read-only.

The `example_skill.md` file shows a real Agent Skill that queries Unity Catalog. Adapt it to your domain and iterate through the lab.
