---
name: clinical-code-resolver
description: Resolve clinical free-text concepts ('blood thinners', 'CT PE', 'sepsis bundle') to
  coded values and condition definitions from vch_cerner code_value and condition_spec — the
  foundational vocabulary-resolution step that other clinical skills invoke before cohort queries.
---

# clinical-code-resolver

## Overview

A Tier-3 clinical vocabulary resolver: it translates natural-language clinical concepts into the
coded values and condition definitions that drive cohort queries across the VCH Cerner semantic
layer. It reads two objects in `greenwood_dbw_catalog.vch_cerner`:

- **`code_value`** — the Cerner vocabulary table mapping `code_value` identifiers to
  `display` labels and `code_set_name` groupings (e.g. encounter types, order catalog entries,
  medication concepts, result codes). Use this when a downstream query filters on `catalog_cd`,
  `encntr_type_cd`, or any other coded column.
- **`condition_spec`** — the clinical-condition registry: one row per condition key (`cond_key`)
  with primary ICD-10 codes, severity thresholds, risk probabilities, and related order/diagnosis
  code sets. Use this to map a clinical concept (e.g. `sepsis`, `pe`, `hf_exac`) to its full
  specification before running outcome queries.

Because both tables are classification/reference objects — no patient identifiers, no encounter
content — this skill operates on vocabulary metadata only and never touches identifier or
free-text clinical tables.

## When to use this skill

Reach for this skill when you need to bridge a free-text clinical term to a code before querying
patient-level data:

- "What code_set covers anticoagulant orders?"
- "Show me all encounter-type codes."
- "What is the condition specification for pulmonary embolism?"
- "Which cond_key maps to ICD-10 I26.99?"
- "List all condition_spec entries with ICU probability above 0.3."
- "What display label corresponds to code_value 1234?"

Other clinical skills (cohort builders, outcome analyzers, readmission trackers) call this skill
first to resolve the concept, then apply the resulting codes to population or feature tables.

## Instructions

When the user asks a code-resolution question:

1. **Identify the concept type** — is the user looking for a vocabulary code (order, encounter
   type, result) or a condition definition (ICD-10 anchor, risk parameters, severity thresholds)?
2. **Route to the right table:**
   - Vocabulary lookup → query `code_value` by `display` (partial match) or `code_set_name`.
   - Condition lookup → query `condition_spec` by `cond_key` or scan ICD-10 columns
     (`dx_primary`, `dx_severe`).
3. **Return the full row** for condition_spec lookups so the downstream skill has all thresholds
   (severe_p, icu_p, mort_p, chronic, weight) without a second round-trip.
4. **Resolve ambiguity** — if the free-text term matches multiple `code_set_name` groups or
   multiple `cond_key` rows, list the candidates so the user can narrow before running a
   patient-level query.
5. **Hand off** — once the code is resolved, name the specialist skill that uses it
   (e.g. cohort-builder, readmission-analyzer) so the user routes there for population analysis.

## Examples

### Look up vocabulary codes by display label

```sql
SELECT
  code_value,
  code_set,
  code_set_name,
  display,
  concept_domain
FROM greenwood_dbw_catalog.vch_cerner.code_value
WHERE LOWER(display) LIKE '%anticoagul%'
ORDER BY code_set_name, display
LIMIT 50
```

### Browse a full code set by name

```sql
SELECT
  code_value,
  code_set_name,
  display,
  concept_domain
FROM greenwood_dbw_catalog.vch_cerner.code_value
WHERE code_set_name = 'ENCOUNTER_TYPE'
ORDER BY display
```

### Look up a single condition specification by cond_key

```sql
SELECT
  cond_key,
  dx_primary,
  dx_severe,
  sec_codes,
  order_codes,
  severe_p,
  icu_p,
  mort_p,
  chronic,
  weight,
  specialty_cd
FROM greenwood_dbw_catalog.vch_cerner.condition_spec
WHERE cond_key = 'pe'
```

### Scan condition_spec for high-ICU-risk conditions

```sql
SELECT
  cond_key,
  dx_primary,
  icu_p,
  mort_p,
  severe_p,
  chronic
FROM greenwood_dbw_catalog.vch_cerner.condition_spec
WHERE icu_p >= 0.30
ORDER BY icu_p DESC
```

### Find the condition_spec entry matching an ICD-10 code

```sql
SELECT
  cond_key,
  dx_primary,
  dx_severe,
  icu_p,
  mort_p
FROM greenwood_dbw_catalog.vch_cerner.condition_spec
WHERE dx_primary = 'I26.99'
   OR dx_severe  = 'I26.99'
```

## Recommendations framework

After resolving a code or condition, always include:

1. **Resolved identifier** — the exact `code_value` integer or `cond_key` string, fully quoted,
   ready to paste into a downstream `WHERE` clause.
2. **Scope note** — clarify whether the match came from `code_value` (vocabulary) or
   `condition_spec` (clinical definition), so the user knows which table to join downstream.
3. **Ambiguity flag** — if more than one row matched the free-text term, list all candidates with
   their `code_set_name` or `cond_key` and ask the user to confirm before proceeding.
4. **Specialist hand-off** — name the downstream skill that consumes the resolved code
   (e.g. a cohort builder that filters `population_features` on `cond_key`).

## Edge cases

- **No match on display** — if `LOWER(display) LIKE '%term%'` returns nothing, try a broader
  term or search by `concept_domain`. Do not guess a code_value.
- **Multiple code sets** — a clinical concept (e.g. "glucose") may appear in lab result, order
  catalog, and problem-list code sets. Return all candidate sets; let the user pick the right
  context before applying the code to patient data.
- **Condition not in condition_spec** — `condition_spec` covers the 20 flagship conditions in
  the VCH Cerner semantic layer. If the requested condition is absent, inform the user and suggest
  querying `code_value` for ICD-10 diagnosis codes instead.
- **ICD-10 prefix matching** — `dx_primary` and `dx_severe` store full ICD-10 codes; a prefix
  search (e.g. `dx_primary LIKE 'I26%'`) is appropriate when the user supplies a category range.
- **ORDERED vs ADMINISTERED** — order codes in `condition_spec.order_codes` represent orders
  placed, not medications administered. Make this distinction explicit when the user is building
  quality or adherence queries.

## Data scope

- `greenwood_dbw_catalog.vch_cerner.code_value` — Cerner vocabulary: coded identifiers,
  display labels, code set groupings, and concept domains. No patient data.
- `greenwood_dbw_catalog.vch_cerner.condition_spec` — clinical-condition registry: ICD-10
  anchors, severity thresholds, risk probabilities, and related code sets. No patient data.
- Identifier tables (`person`, `prsnl`, `clinical_note`) are never referenced by this skill.
