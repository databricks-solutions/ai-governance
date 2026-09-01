---
name: academic-activity-tracker
description: Track Medical Academics & Affairs activity — learner placements, teaching hours, and research-output counts — from aggregate program tables. Ask me about trainee placement volumes, faculty teaching load, or publication counts by department.
---

# academic-activity-tracker

## Overview

Surfaces Medical Academics & Affairs operational activity from **aggregate program** tables:
it reports learner/resident placement volumes, faculty teaching hours, and research-output
counts by department and period. It reads program-level rollups — not individual learner or
faculty records — which keeps it a Tier-2 (internal) skill.

## When to use this skill

Reach for this skill when an academic-affairs or program administrator asks about activity:

- "How many learner placements did each department host this academic year?"
- "What is the faculty teaching-hour load by department?"
- "Show me research-output (publication) counts by department over the last 3 years."
- "Which programs are trending up in placement volume?"

## Instructions

When the user asks a placement, teaching-load, or research-output question:

1. **Identify the department(s) and period** (default: current academic year).
2. **Query `main.maa.placements`** for placement and teaching-hour aggregates by department.
3. **Join `main.maa.research_output`** for publication/output counts when research is asked.
4. **Present results** as a ranked table, then give 2–3 activity observations
   (see the Recommendations framework).

## Examples

### Learner placements by department (current academic year)

```sql
SELECT
  department,
  SUM(placement_count)   AS placements,
  SUM(teaching_hours)    AS teaching_hours
FROM main.maa.placements
WHERE academic_year = YEAR(CURRENT_DATE())
GROUP BY department
ORDER BY placements DESC
```

### Research output by department (last 3 years)

```sql
SELECT
  department,
  output_year,
  SUM(publication_count) AS publications
FROM main.maa.research_output
WHERE output_year >= YEAR(CURRENT_DATE()) - 3
GROUP BY department, output_year
ORDER BY department, output_year
```

## Recommendations framework

After presenting results, always include:

1. **Top contributor** — the department with the most placements, teaching hours, or output, named.
2. **Trend signal** — which departments are rising or falling year-over-year.
3. **Quick observation** — one capacity/planning note (e.g. "teaching load concentrated in department X — succession risk").

## Edge cases

- **Missing year** — if the requested academic year has no rows, say so explicitly rather
  than returning an empty table.
- **Grain mismatch** — placement/teaching questions use `placements`; research questions use
  `research_output`. Don't conflate the two grains.
- **Aggregate only** — this skill works at the department/program level. If asked about a
  specific learner or faculty member, decline: that is individual-level data outside its scope.

## Data scope

- `main.maa.placements` — learner placement counts and teaching hours by department and year (aggregate)
- `main.maa.research_output` — publication/output counts by department and year (aggregate)
- No PII or individual learner/faculty records are accessed — figures are aggregate rollups only.
