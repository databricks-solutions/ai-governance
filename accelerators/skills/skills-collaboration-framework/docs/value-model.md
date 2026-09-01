# Value Model — A Worksheet the Client Fills In

This framework's ROI is **the client's number, not ours.** A self-computed figure from the
customer's own rates and volumes is far more credible than a vendor ROI slide. This document gives
the **levers and formulas**; every value is left blank for the client to fill in with their data.

> How to use: walk these with the customer's data/platform lead. Pull volumes from
> `system.access.assistant_events` (adoption) and their own time-tracking / incident data. Keep the
> numbers theirs.

## Lever 1 — Duplication cost (work rebuilt because it couldn't be found)

```
duplication_cost_per_year
  = (# duplicate or near-duplicate skills)      [ ____ ]
  × (avg hours to rebuild one)                  [ ____ ]
  × (loaded $/hr of the analyst/engineer)       [ ____ ]
  × (rebuilds per year)                         [ ____ ]
```

The registry's mandatory dupe-check at *Propose* is what this lever measures the avoidance of.

## Lever 2 — Low-quality-skill cost (re-prompting and fixing)

```
low_quality_cost_per_year
  = (skill invocations / month)                 [ ____ ]
  × (share that re-prompt or need fixing)       [ ____ ]
  × (minutes lost per occurrence ÷ 60)          [ ____ ]
  × (loaded $/hr)                               [ ____ ]
  × 12
```

A reviewed, tiered skill reduces the re-prompt/fix rate. The AI review + human gate is the lever.

## Lever 3 — Accuracy-driven rework (downstream corrections)

```
accuracy_rework_cost_per_year
  = (downstream corrections / month)            [ ____ ]
  × (hours to correct each)                     [ ____ ]
  × (loaded $/hr)                               [ ____ ]
  × 12
```

Plausible-but-wrong outputs from an ungoverned skill create silent rework. Tiering high-impact
skills to Tier 3 (full review + security) is the lever.

## Lever 4 — Quality lever (qualitative)

Not a dollar line — the **mechanism** that moves Levers 1–3:

- SME / governance-council attention applied **at the right tier** (more for Tier 3, none for Tier 1).
- Reuse incentives tied to team OKRs so discovery beats rebuild.
- Safe self-service: consumers trust what's in the allowlist, so they use it instead of rolling their own.

## Soft value (name it, don't price it)

Trust in AI outputs · auditability for regulators · faster onboarding (new hires inherit governed
skills) · no shadow-IT cleanup · a defensible "who can touch what data" story.

## Fill-in worksheet

| Lever | Input | Client value | Annualized $ |
|-------|-------|--------------|--------------|
| Duplication | # dup skills × hrs × $/hr × rebuilds/yr | | |
| Low-quality | invocations × re-prompt% × min/60 × $/hr × 12 | | |
| Accuracy rework | corrections × hrs × $/hr × 12 | | |
| **Total avoidable cost / year** | | | **$ ______** |
| One-time + run cost (Platform Team effort, see adoption-model.md) | | | $ ______ |
| **Net / payback** | | | **______** |

> No fabricated benchmarks live in this repo on purpose. If you want ranges to seed a conversation,
> source them from the customer's own pilot or a named internal study — never invent them.
