---
name: catalog-navigator
description: Discover data across Unity Catalog — find tables by name or topic, inspect columns and comments, and trace where data lives — from system.information_schema. An enterprise-wide skill for locating the right table before you query it, in any workspace.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# catalog-navigator

## Overview

An enterprise-wide (Tier-3) data-discovery skill: it helps a user *find the right table*
across Unity Catalog before they query it. It searches the catalog by table or column name,
lists a table's columns and comments, and summarizes what a schema contains — all from the
live `system.information_schema` metadata views. Because it reads only catalog *metadata*
(names, types, comments, ownership) and never table contents, it is safe to run in every
workspace, which is exactly why it belongs at Tier 3: one discovery skill available org-wide,
regardless of domain.

## When to use this skill

Reach for this skill whenever a user needs to locate or understand data anywhere in the catalog:

- "Which tables have 'billing' in their name?"
- "What columns does `system.billing.usage` have?"
- "Find tables that contain a `customer_id` column."
- "What's in the `system.lakeflow` schema?"
- "Where would I find data about job runs?"

## Instructions

When the user asks a discovery question:

1. **Interpret the target** — a keyword (topic), a specific table, or a column name.
2. **Search `system.information_schema.tables`** for name/schema matches (topic or table lookup).
3. **Query `system.information_schema.columns`** to list a table's columns, or to find tables
   that contain a named column.
4. **Present results** as a compact table, then point the user to the single best-matching
   table and suggest the domain skill (if any) that specializes in it.

## Examples

### Find tables by keyword

```sql
SELECT
  table_catalog,
  table_schema,
  table_name,
  comment
FROM system.information_schema.tables
WHERE LOWER(table_name) LIKE '%billing%'
   OR LOWER(comment)    LIKE '%billing%'
ORDER BY table_catalog, table_schema, table_name
LIMIT 50
```

### Inspect a table's columns

```sql
SELECT
  column_name,
  data_type,
  comment
FROM system.information_schema.columns
WHERE table_catalog = 'system'
  AND table_schema  = 'billing'
  AND table_name    = 'usage'
ORDER BY ordinal_position
```

### Find tables containing a given column

```sql
SELECT
  table_catalog,
  table_schema,
  table_name
FROM system.information_schema.columns
WHERE LOWER(column_name) = 'job_id'
GROUP BY table_catalog, table_schema, table_name
ORDER BY table_catalog, table_schema, table_name
LIMIT 50
```

## Recommendations framework

After presenting matches, always include:

1. **Best match** — the single most relevant table for the user's intent, fully qualified.
2. **Specialist hand-off** — if a domain skill specializes in that table (e.g. billing →
   `pipeline-cost-analyzer`), name it so the user routes there for analysis.
3. **Narrowing tip** — one way to refine if the search returned too many matches (add a schema
   filter, search by column instead of name).

## Edge cases

- **No matches** — if the keyword matches nothing visible, say so and suggest a broader term,
  rather than returning an empty table with no explanation.
- **Permission scope** — `information_schema` only surfaces objects the caller can see; results
  are relative to the user's Unity Catalog grants, not the whole metastore.
- **Discovery, not analysis** — this skill locates and describes tables. Once the right table
  is found, hand off to the specialist domain skill (or a direct query) for the actual analysis;
  it never reads table contents itself.

## Data scope

- `system.information_schema.tables` — table inventory, schema, ownership, and comments
- `system.information_schema.columns` — column names, types, and comments
- No PII or table contents are accessed — this skill reads catalog metadata only.
