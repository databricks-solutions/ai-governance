---
name: quality-indicator-reporter
description: Report Quality Analytics indicators — readmission rates, adverse-event rates, and hand-hygiene compliance — from aggregate quality-measure tables. Ask me about indicator trends, units below target, or benchmark gaps; no patient-level data.
---

# quality-indicator-reporter

## Overview

Surfaces Quality Analytics performance from **aggregate quality-measure** tables: it reports
standard indicators (readmission rate, adverse-event rate, hand-hygiene compliance) by unit
and period, compares them against targets, and tracks trends. It reads pre-aggregated,
de-identified measure rollups — never patient-level clinical records — keeping it a Tier-2
(internal) skill.

## When to use this skill

Reach for this skill when a quality or safety user asks about indicators:

- "What is the 30-day readmission rate trend by unit?"
- "Which units are below the hand-hygiene compliance target?"
- "Show me adverse-event rates against benchmark this quarter."
- "Which indicators have the largest gap to target?"

## Instructions

When the user asks a quality-indicator question:

1. **Identify the indicator(s), unit(s), and period** (default: last 4 quarters).
2. **Query `main.quality.indicator_measures`** for measured values by indicator, unit, and period.
3. **Join `main.quality.targets`** to compute the gap to target when benchmarking is asked.
4. **Present results** as a ranked table (worst gap first), then give 2–3 observations
   (see the Recommendations framework).

## Examples

### Readmission-rate trend by unit (last 4 quarters)

```sql
SELECT
  unit_name,
  measure_period,
  measure_value AS readmission_rate
FROM main.quality.indicator_measures
WHERE indicator_name = 'readmission_30d'
  AND measure_period >= ADD_MONTHS(DATE_TRUNC('quarter', CURRENT_DATE()), -12)
ORDER BY unit_name, measure_period
```

### Largest gaps to target (latest period)

```sql
SELECT
  m.indicator_name,
  m.unit_name,
  m.measure_value,
  t.target_value,
  m.measure_value - t.target_value AS gap_to_target
FROM main.quality.indicator_measures m
JOIN main.quality.targets t
  ON m.indicator_name = t.indicator_name
WHERE m.measure_period = (SELECT MAX(measure_period) FROM main.quality.indicator_measures)
ORDER BY ABS(m.measure_value - t.target_value) DESC
```

## Recommendations framework

After presenting results, always include:

1. **Worst gap** — the indicator/unit furthest from target, named, with the size of the gap.
2. **Trend signal** — is the indicator improving or worsening over the periods shown?
3. **Quick action** — one improvement observation (e.g. "readmission on unit X worsening 3 quarters running — flag for review").

## Edge cases

- **No target row** — if an indicator has measures but no `targets` row, report it as
  untargeted rather than assuming a target of zero.
- **Sparse periods** — if the requested period has no measure rows, say so explicitly.
- **Aggregate only** — this skill reads pre-aggregated measures. If asked which patients were
  readmitted, decline: that is patient-level (PHI) data outside this skill's scope.

## Data scope

- `main.quality.indicator_measures` — measured indicator values by unit and period (aggregate, de-identified)
- `main.quality.targets` — target/benchmark values per indicator
- No PII or patient-level clinical data is accessed — measures are aggregate rollups only.
