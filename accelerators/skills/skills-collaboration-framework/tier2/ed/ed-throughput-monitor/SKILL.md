---
name: ed-throughput-monitor
description: Monitor Emergency Department throughput — arrivals, wait times, length-of-stay, and left-without-being-seen rates — from aggregate hourly/daily operational tables. Ask me about ED wait-time trends or throughput bottlenecks; no patient-level data.
---

# ed-throughput-monitor

## Overview

Surfaces Emergency Department operational throughput from **aggregate, time-bucketed** tables:
it reports arrival volumes, median wait times, average length-of-stay, and left-without-being-seen
(LWBS) rates over time. Scope is deliberately operational — hourly/daily aggregates, never
individual patient encounters — which keeps it a Tier-2 (internal) skill rather than a Tier-3
PHI skill.

## When to use this skill

Reach for this skill when an ED operations user asks about throughput:

- "What is the median ED wait time trend over the last 30 days?"
- "Which hours of the day have the worst throughput?"
- "Show me the left-without-being-seen rate by week."
- "How does today's arrival volume compare to the 30-day average?"

## Instructions

When the user asks a throughput or wait-time question:

1. **Identify the time grain and window** (default: daily, last 30 days).
2. **Query `main.ed.throughput_hourly`** for arrivals, wait, and length-of-stay aggregates.
3. **Join `main.ed.daily_summary`** for LWBS and daily rollups when needed.
4. **Present results** as a trend table, then give 2–3 throughput observations
   (see the Recommendations framework).

## Examples

### Median wait-time trend (last 30 days)

```sql
SELECT
  summary_date,
  median_wait_minutes,
  arrivals
FROM main.ed.daily_summary
WHERE summary_date >= DATE_SUB(CURRENT_DATE(), 30)
ORDER BY summary_date
```

### Worst throughput hours (last 7 days)

```sql
SELECT
  hour_of_day,
  AVG(median_wait_minutes) AS avg_wait,
  SUM(arrivals)            AS total_arrivals
FROM main.ed.throughput_hourly
WHERE bucket_date >= DATE_SUB(CURRENT_DATE(), 7)
GROUP BY hour_of_day
ORDER BY avg_wait DESC
```

## Recommendations framework

After presenting results, always include:

1. **Worst bucket** — the hour or day with the longest waits or highest LWBS, named.
2. **Trend signal** — is wait time rising, flat, or falling? Flag if median wait up >15% week-over-week.
3. **Quick action** — one operational lever (e.g. "peak-hour staffing gap at 18:00–22:00 drives LWBS").

## Edge cases

- **Sparse windows** — if the requested window has no rows, say so explicitly instead of
  returning an empty table.
- **Grain mismatch** — hourly questions use `throughput_hourly`; daily/rate questions use
  `daily_summary`. Don't derive daily rates from partial hourly buckets.
- **Aggregate only** — this skill works on time-bucketed aggregates. If asked about a specific
  patient encounter, decline: that is patient-level (PHI) data outside this skill's scope.

## Data scope

- `main.ed.throughput_hourly` — hourly arrival/wait/length-of-stay aggregates
- `main.ed.daily_summary` — daily rollups including LWBS rate (aggregate)
- No PII or patient-encounter data is accessed — metrics are aggregate time buckets only.
