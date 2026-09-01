---
name: community-service-volumes
description: Report Community Health service volumes, visit counts, and program utilization from aggregate program-level tables. Ask me about home-health visit volumes, program utilization, or referral trends — no client-level data.
---

# community-service-volumes

## Overview

Surfaces Community Health operational activity from **aggregate, program-level** tables: it
reports service-visit volumes, program utilization, and referral trends over time. Scope is
deliberately operational — program- and team-level counts only, never client-level records —
which keeps it Tier-2 (internal) rather than a Tier-3 PHI skill.

## When to use this skill

Reach for this skill when a community-services or program manager asks about volumes:

- "How many home-health visits did we deliver last month by program?"
- "Which community programs are trending up in utilization this quarter?"
- "Show me referral volumes into community services over the last 90 days."
- "What is the visit volume trend for the wound-care program?"

## Instructions

When the user asks a volume or utilization question:

1. **Identify the program(s) and time window** (default: last 90 days).
2. **Query `main.community.service_visits`** for visit counts by program and date.
3. **Join `main.community.programs`** for program names and service categories when needed.
4. **Present results** as a ranked table, then give 2–3 utilization observations
   (see the Recommendations framework).

## Examples

### Visit volume by program (last month)

```sql
SELECT
  p.program_name,
  SUM(v.visit_count) AS total_visits
FROM main.community.service_visits v
JOIN main.community.programs p
  ON v.program_id = p.program_id
WHERE v.visit_date >= DATE_TRUNC('month', DATE_SUB(CURRENT_DATE(), 30))
GROUP BY 1
ORDER BY total_visits DESC
```

### Referral volume trend (last 90 days, weekly)

```sql
SELECT
  DATE_TRUNC('week', referral_date) AS week,
  SUM(referral_count)               AS total_referrals
FROM main.community.referrals
WHERE referral_date >= DATE_SUB(CURRENT_DATE(), 90)
GROUP BY 1
ORDER BY 1
```

## Recommendations framework

After presenting results, always include:

1. **Top program** — the highest-volume program and one capacity observation.
2. **Trend signal** — which programs are rising or falling; flag any change >15% quarter-over-quarter.
3. **Quick action** — one operational observation (e.g. "referral inflow outpacing visit capacity in program X").

## Edge cases

- **Missing program row** — if a visit references a `program_id` with no `programs` row,
  report it as an unmapped program rather than dropping it.
- **Sparse windows** — if the requested window has no visit rows, say so explicitly.
- **Aggregate only** — this skill works at the program/team level. If asked about a specific
  client, decline: that is client-level (PHI) data outside this skill's scope.

## Data scope

- `main.community.service_visits` — visit counts per program and date (aggregate)
- `main.community.programs` — program definitions and service categories
- `main.community.referrals` — referral counts per date (aggregate)
- No PII or client-level data is accessed — volumes are aggregate program-level only.
