---
name: bi-adoption-analyzer
description: Analyze Enterprise Analytics & BI adoption from system.query.history — active users, query volumes, warehouse utilization, and slow-query hotspots. Ask me which dashboards/warehouses are busiest or where query performance is degrading.
---

# bi-adoption-analyzer

## Overview

Surfaces Enterprise Analytics & BI platform adoption from the live `system.query.history`
table: it reports active-user and query volumes, warehouse utilization, and slow-query
hotspots over time. It reads query *metadata* (who ran what, when, how long) — never the
query results or the underlying business data — so it stays a Tier-2 (internal) skill.

## When to use this skill

Reach for this skill when a BI-platform or analytics-enablement user asks about adoption:

- "How many active BI users did we have last month?"
- "Which SQL warehouses are the busiest by query volume?"
- "Show me the slowest queries over the last 7 days."
- "Is query volume trending up quarter-over-quarter?"

## Instructions

When the user asks an adoption, utilization, or performance question:

1. **Identify the window and dimension** (default: last 30 days).
2. **Query `system.query.history`** for query counts, distinct users, and durations.
3. **Aggregate by the requested dimension** (warehouse, user, day) — never return raw query text.
4. **Present results** as a ranked table, then give 2–3 adoption observations
   (see the Recommendations framework).

## Examples

### Active users and query volume by month (last 6 months)

```sql
SELECT
  DATE_TRUNC('month', start_time)        AS month,
  COUNT(*)                               AS query_count,
  COUNT(DISTINCT executed_by)            AS active_users
FROM system.query.history
WHERE start_time >= ADD_MONTHS(DATE_TRUNC('month', CURRENT_DATE()), -6)
GROUP BY 1
ORDER BY 1
```

### Busiest warehouses (last 30 days)

```sql
SELECT
  compute.warehouse_id,
  COUNT(*)                               AS query_count,
  ROUND(AVG(total_duration_ms) / 1000.0, 1) AS avg_seconds
FROM system.query.history
WHERE start_time >= DATE_SUB(CURRENT_DATE(), 30)
  AND compute.warehouse_id IS NOT NULL
GROUP BY compute.warehouse_id
ORDER BY query_count DESC
```

### Slowest queries (last 7 days)

```sql
SELECT
  statement_id,
  executed_by,
  ROUND(total_duration_ms / 1000.0, 1)   AS seconds,
  start_time
FROM system.query.history
WHERE start_time >= DATE_SUB(CURRENT_DATE(), 7)
ORDER BY total_duration_ms DESC
LIMIT 20
```

## Recommendations framework

After presenting results, always include:

1. **Top consumer** — the busiest warehouse or heaviest user, named, with its share of volume.
2. **Trend signal** — is adoption (active users / query volume) rising, flat, or falling?
3. **Quick action** — one enablement or performance observation (e.g. "one slow query dominates
   warehouse X — candidate for tuning").

## Edge cases

- **Sparse windows** — if the requested window has no query rows, say so explicitly.
- **Null warehouse** — some queries have no `warehouse_id` (non-warehouse compute); report
  those as unattributed rather than dropping them.
- **Metadata only** — this skill reads query history metadata, never the query *results* or
  the business tables those queries touched.

## Data scope

- `system.query.history` — query execution metadata (user, warehouse, duration, timestamps)
- No PII or query-result data is accessed — this skill reads execution metadata only.
