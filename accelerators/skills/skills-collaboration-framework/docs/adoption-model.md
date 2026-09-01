# Adoption Model — Crawl, Walk, Run

This framework is meant to be adopted **incrementally and additively**. You do not need the whole
operating model on day one, and you never throw work away to get to the next stage. Each stage is a
**superset** of the one before it: the same Git repo, the same `SKILL.md` folders, the same
`registry.yaml`. What changes between stages is *where skills publish*, *how much is enforced*, and
*how identity is wired* — not the artifacts themselves.

## The ramp

| | **Crawl** — prove the pattern | **Walk** — CI-enforced | **Run** — org-wide serving layer |
|---|---|---|---|
| **Who / trigger** | One team, one champion | Several domains opt in | Standard operating model |
| **Tiers live** | Tier 1 + Tier 2 (one domain) | Tier 1 + Tier 2 (multi-domain) + Tier 3 | All tiers, many domains/workspaces |
| **Gates** | lint + secret scan + metadata validation; manual steward review | + AI review (advisory → binding human gate); CODEOWNERS / branch-policy routing | eval dial tuned per tier (advisory / human-review / auto-drop) |
| **Review / identity** | `governance.yaml` (names + emails) | `governance.yaml` + ADO / Entra groups in branch policy | Groups are the source of truth; `governance.yaml` is the auditable record |
| **Publish** | manual `databricks workspace import-dir` to one workspace | CI syncs on merge to every mapped workspace | Unity AI Gateway becomes the serving source of truth (CI is its supply chain) |
| **Measure** | skills reused vs. rebuilt | time-to-publish, AI-review pass rate, dedupe rate | adoption telemetry (future capability), reuse + incident trend |
| **Effort** | days — one person wearing the Council hat | a steward per active domain (existing people) | standing Council cadence, quarterly review |

## The invariant: never start from scratch

The whole point of the ramp is that **nothing is rebuilt** when you move up a stage:

- **Same artifacts** — the Git repo, the `SKILL.md` folder convention, and `registry.yaml` are
  identical at every stage.
- **`governance.yaml` only grows** — you append stewards/council/security as domains come online;
  you never restructure it.
- **The publish target moves** — manual CLI → CI sync → Unity AI Gateway. Only `sync-skills.sh`'s
  target changes (see [`roadmap-uc-skills.md`](roadmap-uc-skills.md)).
- **The eval dial turns up** — `EVAL_GATE_MODE` goes `advisory` → `human-review` → `auto-drop` as a
  domain matures; the default (`advisory`) preserves day-one behavior.
- **Identity hardens** — string authorization in `governance.yaml` (crawl/walk) gives way to
  Entra / ADO groups wired into branch policy (run); the file stays as the audit record.

## Why additive matters

A governance framework that demands a big-bang rollout stalls. This one lets a single team get
value in days (crawl), proves the gates as more domains join (walk), and only then becomes the
org-wide serving control plane (run). You can **stop at any stage** and still have a governed,
auditable skill library — and you can resume the climb without redoing prior work.
