---
name: pipeline-cost-analyzer
description: Analyze Databricks DBU cost trends, identify top-spending jobs, and recommend cost optimizations using system.billing.usage and system.lakeflow.jobs. Ask me about spend by SKU, job-level costs, or DBU consumption trends over time.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# pipeline-cost-analyzer

## Overview

Surfaces Databricks cost insights from the billing system tables: it ranks the most
expensive jobs, tracks DBU consumption trends by SKU and product, and turns each result
into concrete optimization actions. Scope is deliberately narrow — cost/usage analysis
from `system.billing.usage` and `system.lakeflow.jobs`, nothing else.

## When to use this skill

Reach for this skill whenever a user asks about Databricks spend, DBU consumption, or
job-level cost attribution. Representative requests:

- "What are my top 10 most expensive jobs in the last 30 days?"
- "Show me DBU consumption by SKU over the last quarter."
- "Which jobs increased their DBU spend the most week-over-week?"
- "What is the cost trend for ALL_PURPOSE compute over the last 6 months?"
- "What is my total DBU spend this month vs. last month?"
- "Compare serverless vs. classic compute spend this quarter."
- "What drove the biggest cost spike last quarter?"

## Instructions

When the user asks a cost or job-performance question:

1. **Identify the time window** (default: last 30 days if not specified).
2. **Query `system.billing.usage`** for DBU consumption.
3. **Join with `system.lakeflow.jobs`** when job-level attribution is needed.
4. **Present results** as a ranked table, then give 2–3 actionable recommendations
   (see the Recommendations framework below).

## Examples

### Top-spending jobs (last 30 days)

```sql
SELECT
  u.usage_metadata.job_id                     AS job_id,
  j.name                                       AS job_name,
  u.sku_name,
  SUM(u.usage_quantity)                        AS total_dbus
FROM system.billing.usage u
LEFT JOIN system.lakeflow.jobs j
  ON u.usage_metadata.job_id = j.job_id        -- both job_id columns are STRING
 AND u.workspace_id = j.workspace_id
WHERE u.usage_date >= DATE_SUB(CURRENT_DATE(), 30)
  AND u.usage_metadata.job_id IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
LIMIT 20
```

### DBU spend by SKU — weekly trend (last 90 days)

```sql
SELECT
  sku_name,
  DATE_TRUNC('week', usage_date)               AS week,
  SUM(usage_quantity)                          AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATE_SUB(CURRENT_DATE(), 90)
GROUP BY 1, 2
ORDER BY 2, total_dbus DESC
```

### Monthly cost trend by product (last 6 months)

```sql
SELECT
  DATE_TRUNC('month', usage_date)              AS month,
  billing_origin_product,
  SUM(usage_quantity)                          AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATE_SUB(CURRENT_DATE(), 180)
GROUP BY 1, 2
ORDER BY 1, total_dbus DESC
```

## Recommendations framework

After presenting results, always include:

1. **Top offender** — the single highest-cost job or SKU and one concrete action
   (e.g. "set a max DBU budget on job X", "switch to job compute from all-purpose for batch jobs").
2. **Trend signal** — is spend rising, flat, or falling? Flag if up >20% month-over-month.
3. **Quick win** — one change achievable in under an hour
   (e.g. enable auto-termination on idle clusters, reduce cluster size on off-peak jobs).

## Edge cases

- **No job attribution** — `usage_metadata.job_id` is NULL for non-job usage (all-purpose
  compute, SQL warehouses). Report those as unattributed rather than dropping them.
- **Sparse windows** — if the requested window has no usage rows, say so explicitly instead
  of returning an empty table with no explanation.
- **STRING join keys** — `job_id` and `workspace_id` are both STRING in these tables; never
  cast them to int for the join.

## Data scope

- `system.billing.usage` — DBU consumption events per workspace/SKU/job/cluster
- `system.lakeflow.jobs` — job definitions (name, owner, schedule, tags)
- No PII or sensitive customer data is accessed.

These two tables are the skill's declared `unity_catalog_scopes` in `registry.yaml` — an optional
data-footprint declaration. Runtime access is governed by Unity Catalog on whoever runs the skill;
CI flags (advisory only) any query here that references a table outside the declared footprint.
