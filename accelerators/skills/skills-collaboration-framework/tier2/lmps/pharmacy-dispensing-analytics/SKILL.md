---
name: pharmacy-dispensing-analytics
description: Analyze Lower Mainland Pharmacy dispensing volumes, formulary utilization, and drug spend from aggregate dispensing tables. Ask me about dispensing volume by drug class, high-cost medication spend, or utilization trends — no patient-level data.
---

# pharmacy-dispensing-analytics

## Overview

Surfaces Lower Mainland Pharmacy Services operational activity from **aggregate dispensing**
tables: it reports dispensing volumes by drug and class, formulary utilization, and medication
spend over time. Scope is operational — drug- and site-level aggregates, never patient
prescriptions — which keeps it a Tier-2 (internal) skill rather than a Tier-3 PHI skill.

## When to use this skill

Reach for this skill when a pharmacy operations or formulary user asks about dispensing:

- "What are the top dispensed drug classes by volume this month?"
- "Which high-cost medications drive the most spend?"
- "Show me dispensing volume trends for antimicrobials over the last quarter."
- "How does site-level dispensing volume compare across the region?"

## Instructions

When the user asks a dispensing or spend question:

1. **Identify the drug/class, site, and window** (default: last 90 days).
2. **Query `main.pharmacy.dispensing`** for dispensed quantities and cost by drug and date.
3. **Join `main.pharmacy.formulary`** for drug class and formulary status when needed.
4. **Present results** as a ranked table, then give 2–3 utilization/spend observations
   (see the Recommendations framework).

## Examples

### Top drug classes by dispensing volume (this month)

```sql
SELECT
  f.drug_class,
  SUM(d.dispensed_quantity) AS total_dispensed
FROM main.pharmacy.dispensing d
JOIN main.pharmacy.formulary f
  ON d.drug_id = f.drug_id
WHERE d.dispense_date >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY f.drug_class
ORDER BY total_dispensed DESC
```

### High-cost medication spend (last 90 days)

```sql
SELECT
  d.drug_name,
  SUM(d.total_cost) AS spend
FROM main.pharmacy.dispensing d
WHERE d.dispense_date >= DATE_SUB(CURRENT_DATE(), 90)
GROUP BY d.drug_name
ORDER BY spend DESC
LIMIT 20
```

## Recommendations framework

After presenting results, always include:

1. **Top driver** — the drug or class with the highest volume or spend, named.
2. **Trend signal** — which classes are rising or falling; flag any change >20% quarter-over-quarter.
3. **Quick action** — one formulary/operational observation (e.g. "high-cost drug X has a formulary-preferred alternative").

## Edge cases

- **Unmapped drug** — if a dispensing row references a `drug_id` with no formulary row, report
  it as off-formulary rather than dropping it.
- **Sparse windows** — if the requested window has no dispensing rows, say so explicitly.
- **Aggregate only** — this skill works at the drug/class/site level. If asked which patients
  received a medication, decline: that is patient-level (PHI) data outside this skill's scope.

## Data scope

- `main.pharmacy.dispensing` — dispensed quantities and cost by drug, site, and date (aggregate)
- `main.pharmacy.formulary` — drug definitions, class, and formulary status
- No PII or patient-prescription data is accessed — figures are aggregate dispensing rollups only.
