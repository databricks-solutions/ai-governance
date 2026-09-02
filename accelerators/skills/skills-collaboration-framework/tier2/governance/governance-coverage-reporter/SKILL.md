---
name: governance-coverage-reporter
description: Report Unity Catalog governance coverage — table comments, ownership, tags, and column documentation — from system.information_schema. Ask me which tables lack owners, descriptions, or classification tags across a catalog.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# governance-coverage-reporter

## Overview

Measures Unity Catalog **governance hygiene** from the live `system.information_schema`
metadata views: it reports which tables lack an owner, a description/comment, or classification
tags, and summarizes documentation coverage across a catalog. This is metadata-only — it reads
the catalog's *structure and annotations*, never the data inside any table — which keeps it a
clean Tier-2 (internal) skill.

## When to use this skill

Reach for this skill when a data-governance or privacy user asks about catalog hygiene:

- "Which tables in the `main` catalog have no description?"
- "How many tables are missing an owner?"
- "Show me governance coverage — what share of tables have comments and tags?"
- "Which schemas have the worst documentation coverage?"

## Instructions

When the user asks a governance-coverage question:

1. **Identify the catalog/schema scope** (default: the `main` catalog).
2. **Query `system.information_schema.tables`** for table inventory, owners, and comments.
3. **Join `system.information_schema.table_tags`** to assess classification-tag coverage.
4. **Present results** as a coverage summary + a ranked list of the least-documented schemas
   (see the Recommendations framework).

## Examples

### Tables missing a description or owner (in `main`)

```sql
SELECT
  table_schema,
  table_name,
  table_owner,
  comment
FROM system.information_schema.tables
WHERE table_catalog = 'main'
  AND (comment IS NULL OR comment = '' OR table_owner IS NULL)
ORDER BY table_schema, table_name
```

### Documentation coverage by schema

```sql
SELECT
  table_schema,
  COUNT(*)                                                        AS total_tables,
  SUM(CASE WHEN comment IS NOT NULL AND comment <> '' THEN 1 ELSE 0 END) AS documented,
  ROUND(
    SUM(CASE WHEN comment IS NOT NULL AND comment <> '' THEN 1 ELSE 0 END) / COUNT(*),
    3
  )                                                               AS doc_coverage
FROM system.information_schema.tables
WHERE table_catalog = 'main'
GROUP BY table_schema
ORDER BY doc_coverage ASC
```

### Classification-tag coverage

```sql
SELECT
  t.table_schema,
  COUNT(DISTINCT t.table_name)                     AS total_tables,
  COUNT(DISTINCT tg.table_name)                    AS tagged_tables
FROM system.information_schema.tables t
LEFT JOIN system.information_schema.table_tags tg
  ON t.table_catalog = tg.catalog_name
 AND t.table_schema  = tg.schema_name
 AND t.table_name    = tg.table_name
WHERE t.table_catalog = 'main'
GROUP BY t.table_schema
ORDER BY tagged_tables ASC
```

## Recommendations framework

After presenting results, always include:

1. **Biggest gap** — the schema with the lowest documentation or tag coverage, named.
2. **Coverage headline** — the overall share of tables with owners / comments / tags.
3. **Quick win** — one prioritized action (e.g. "assign owners to the N ownerless tables in schema X first").

## Edge cases

- **Empty catalog** — if the requested catalog has no tables, say so rather than returning
  a zero-row summary with no context.
- **Permission scope** — `information_schema` only surfaces objects the caller can see; note
  that coverage is relative to visible objects, not necessarily the whole metastore.
- **Metadata only** — this skill never reads table *contents*. If asked about the data inside
  a table, redirect: that is a data-query task, not a governance-coverage task.

## Data scope

- `system.information_schema.tables` — table inventory, owner, and comment metadata
- `system.information_schema.table_tags` — classification/governance tag assignments
- No PII or table contents are accessed — this skill reads catalog metadata only.
