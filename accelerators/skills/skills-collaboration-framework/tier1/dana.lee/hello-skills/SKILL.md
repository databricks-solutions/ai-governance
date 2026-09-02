---
name: hello-skills
description: A personal sandbox skill used as the annotated authoring template for this reference implementation. It shows the agentskills.io-recommended SKILL.md structure. Use it when learning how to author a new skill.
---

> **Annotated template (Tier 1 sandbox).** This file is the canonical starting point for a new
> skill. Each section below names an [agentskills.io](https://agentskills.io) best-practice category
> and explains what to put there. Replace every `TODO:` with real content, then promote via
> `scripts/new-skill.sh` / a PR. Tier-1 skills are never synced and are exempt from the no-`TODO`
> gate — a promoted (T2/T3) skill must have all `TODO`s filled.

# hello-skills

## Overview

TODO: One paragraph — the single task this skill handles and WHEN the agent should reach for it.
Keep scope narrow (one skill, one job); overlapping skills cause mis-routing. Frontmatter
`description` = what it does + when to use it + trigger keywords (this drives auto-load).

## When to use this skill

TODO: Real phrasings a user might say — these calibrate description-based auto-load:
- "TODO: an example request that should load this skill"

## Instructions

TODO: Explicit, ordered steps. Calibrate control to fragility: be prescriptive for fragile or
must-be-exact sequences; give the agent freedom (explain *why*, not rigid steps) where multiple
approaches are valid. Provide a default, not a menu of equal options.
1. TODO: first step
2. TODO: next step

## Examples

TODO: Concrete input → output. Agents pattern-match against examples better than prose.
**Request:** "TODO: a sample question a user would ask"
**Expected behavior:** TODO: what the skill does — the SQL it runs and/or the shape of the answer.

## Edge cases

TODO: Common variations/exceptions and how to handle them.
- TODO: an edge case

## Gotchas

TODO: Environment-specific facts the agent would get WRONG without being told — not general
advice. Highest-value content in many skills.
- TODO: e.g. "table X uses soft deletes; filter WHERE deleted_at IS NULL"

## Data scope

TODO: The skill's data footprint, in prose. Runtime access is governed by Unity Catalog on
whoever runs the skill — this documents intent, it is NOT an access control.
- `catalog.schema.table` — what it is read for
- No PII or regulated data is accessed.   <!-- if false, the skill must be Tier 3 -->

<!-- Progressive disclosure: keep SKILL.md under ~500 lines / 5000 tokens. For depth, add sibling
     files (references/patterns.md, scripts/foo.py) and tell the agent WHEN to load each. -->
