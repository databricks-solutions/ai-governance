---
name: bed-capacity-monitor
description: Monitor Acute Care bed occupancy, unit capacity, and census trends from aggregate ward-level tables. Ask me about occupancy rates by unit, capacity pressure, or census trends over time — no patient-level data.
---

# bed-capacity-monitor

## Overview

Surfaces Acute Care operational capacity from **aggregate, ward-level** census tables: it
reports bed occupancy rates by unit, flags units under capacity pressure, and tracks census
trends over time. Scope is deliberately operational — unit-level counts only, never
patient-level records — which is what keeps it a Tier-2 (internal) skill rather than a
Tier-3 PHI skill.

## When to use this skill

Reach for this skill when an operations or bed-management user asks about acute capacity:

- "What is the current bed occupancy rate by unit?"
- "Which acute units are over 90% occupancy right now?"
- "Show me the census trend for the ICU over the last 30 days."
- "Which units are under the most capacity pressure this week?"

## Instructions

When the user asks a capacity or census question:

1. **Identify the unit(s) and time window** (default: latest snapshot, or last 30 days for trends).
2. **Query `main.acute.bed_census`** for occupied-bed counts by unit and date.
3. **Join `main.acute.unit_capacity`** to compute occupancy as occupied ÷ staffed beds.
4. **Present results** as a ranked table, then flag any unit above the pressure threshold
   (see the Recommendations framework).

## Examples

### Current occupancy rate by unit

```sql
SELECT
  c.unit_name,
  c.occupied_beds,
  u.staffed_beds,
  ROUND(c.occupied_beds / u.staffed_beds, 3) AS occupancy_rate
FROM main.acute.bed_census c
JOIN main.acute.unit_capacity u
  ON c.unit_id = u.unit_id
WHERE c.census_date = (SELECT MAX(census_date) FROM main.acute.bed_census)
ORDER BY occupancy_rate DESC
```

### Census trend for a unit (last 30 days)

```sql
SELECT
  census_date,
  occupied_beds
FROM main.acute.bed_census
WHERE unit_name = 'ICU'
  AND census_date >= DATE_SUB(CURRENT_DATE(), 30)
ORDER BY census_date
```

## Recommendations framework

After presenting results, always include:

1. **Pressure flag** — any unit above 90% occupancy, with the single most-pressured unit named.
2. **Trend signal** — is occupancy rising, flat, or falling over the window? Flag if up >10% week-over-week.
3. **Quick action** — one operational lever (e.g. "review discharge readiness on the two highest-occupancy units").

## Edge cases

- **Missing capacity row** — if a unit has census but no `unit_capacity` row, report it as
  unrated rather than dividing by NULL.
- **Sparse windows** — if the requested window has no census rows, say so explicitly instead
  of returning an empty table with no explanation.
- **Aggregate only** — this skill works at the unit level. If asked about a specific patient,
  decline: that is patient-level (PHI) data outside this skill's scope.

## Data scope

- `main.acute.bed_census` — daily occupied-bed counts per unit (aggregate, no patient identifiers)
- `main.acute.unit_capacity` — staffed-bed capacity per unit
- No PII or patient-level data is accessed — occupancy is aggregate ward-level only.
