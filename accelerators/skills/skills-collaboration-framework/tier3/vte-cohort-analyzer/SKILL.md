---
name: vte-cohort-analyzer
description: Analyze hospital-acquired VTE (DVT/PE) outcomes, prophylaxis adherence, and PSI-12
  quality metrics from the Greenwood EHR semantic layer — and build the governed pop_vte cohort
  asset when it does not yet exist.
---

# vte-cohort-analyzer

## Overview

A Tier-3 clinical outcome and cohort-governance skill: it analyzes venous thromboembolism (VTE)
events across inpatient encounters using the Greenwood EHR semantic layer, and documents how to
materialize the governed `pop_vte` cohort asset (function, cohort table, and metric view) when
it does not yet exist.

VTE encompasses two conditions:

- **Pulmonary embolism (PE)** — ICD-10 I26.x, represented in `condition_spec` as `cond_key = 'pe'`
  (primary code I26.99). The complication flag `cmp_pe` in `population_endpoint_features` captures
  PE events that arose as in-hospital complications.
- **Deep vein thrombosis (DVT)** — ICD-10 I82.x. DVT does **not** currently exist as a standalone
  `cond_key` in `condition_spec`; this is the gap the asset-generation section resolves.

**Clinical quality context — AHRQ PSI-12.** Hospital-acquired VTE is defined as a VTE event that
occurs on or after hospital day 2 (onset >= day 2 of admission), excluding Present-on-Admission
(POA) diagnoses. This is the AHRQ Patient Safety Indicator 12 (PSI-12) and the CMS hospital-
acquired-condition definition. The primary quality levers are:

- **Pharmacological prophylaxis** — low-molecular-weight heparin (LMWH), unfractionated heparin
  (UFH), or fondaparinux — captured in `tx_anticoag`.
- **Mechanical prophylaxis** — sequential compression devices (SCD) or graduated compression
  stockings (GCS) — represented by order concepts in `orders`.
- **Quality window** — prophylaxis should be ordered within 24-48 hours of admission.
- **ORDERED vs ADMINISTERED distinction** — an order in `orders` (by `catalog_cd`) records that a
  clinician placed the order, not that the patient received it. Adherence analysis must distinguish
  orders placed from administrations recorded; using order data alone overstates prophylaxis rates.

Because this skill reads encounter-level outcome flags and order-level records, it operates on
regulated clinical data and is Tier 3 only.

## When to use this skill

Reach for this skill when a question involves VTE burden, prophylaxis adherence, or PSI-12
quality measurement:

- "What is the in-hospital PE rate by facility for the past 12 months?"
- "How does anticoagulation prophylaxis adherence vary across facilities?"
- "How many patients had VTE as a complication (cmp_pe = 1) but no prior anticoag order?"
- "Show me the monthly trend in PE outcomes stratified by ICU use."
- "What anticoagulant order codes are in use for DVT prophylaxis?"
- "Build the pop_vte cohort asset for the first time."
- "What is the prophylaxis ordering rate within 48 hours of admission for surgical patients?"

This skill also serves as the CEDAR asset-generation exemplar: it shows how a new governed cohort
object (`pop_vte()` function + `pop_vte_tbl` table + `mv_vte_endpoint` metric view) is created
when a condition is not yet registered in the population layer.

## Instructions

When the user asks a VTE analysis question:

1. **Identify the analysis type** — outcome trend, prophylaxis adherence, complication gap, or
   cohort asset creation.
2. **Distinguish PE vs DVT scope:**
   - PE with existing `cond_key` → filter `population_endpoint_features` on `cond_key = 'pe'` or
     `cmp_pe = 1`.
   - DVT or combined VTE → use `cmp_pe` plus awareness that a DVT-specific `cond_key` does not
     exist yet; recommend building `pop_vte_tbl` (see the asset-generation section below) first.
3. **Apply PSI-12 logic:**
   - Hospital-acquired VTE requires onset on or after day 2. There is no pre-computed HAC day-2
     flag in `population_endpoint_features`; use `length_of_stay_days >= 2` as a proxy for
     encounters where a hospital-acquired event is plausible, and note the approximation.
   - The `cmp_pe` flag in `population_endpoint_features` captures PE complications; it is the
     closest available proxy for in-hospital PE.
4. **Prophylaxis adherence — use `tx_anticoag` for the pharmacological summary flag, and query
   `orders` with the relevant `catalog_cd` values when you need ORDERED vs ADMINISTERED
   distinction.** Never report order placement as drug administration without noting the
   distinction explicitly.
5. **Stratify** by `loc_facility_cd`, `admit_month`, and (where appropriate) `icu_use` to surface
   facility-level and temporal variation.
6. **Route to the asset section** if the user needs to build `pop_vte_tbl` or `mv_vte_endpoint`
   for the first time — that write path requires Tier-3 authorization and is documented below.

## Examples

### PE burden by facility — monthly trend

```sql
SELECT
  loc_facility_cd,
  DATE_TRUNC('month', admit_month) AS month,
  COUNT(*)                          AS total_inpatient,
  SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END) AS vte_pe_encounters,
  ROUND(
    100.0 * SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END) / COUNT(*), 2
  )                                 AS pe_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE is_inpatient = 1
  AND length_of_stay_days >= 2
GROUP BY loc_facility_cd, DATE_TRUNC('month', admit_month)
ORDER BY month DESC, loc_facility_cd
```

### Anticoagulation prophylaxis adherence rate

```sql
SELECT
  loc_facility_cd,
  COUNT(*)                                              AS total_inpatient,
  SUM(tx_anticoag)                                      AS anticoag_ordered,
  ROUND(100.0 * SUM(tx_anticoag) / COUNT(*), 2)         AS anticoag_rate_pct,
  SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END) AS vte_events,
  ROUND(
    100.0 * SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END) / COUNT(*), 2
  )                                                     AS vte_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE is_inpatient = 1
GROUP BY loc_facility_cd
ORDER BY anticoag_rate_pct ASC
```

### Prophylaxis gap — VTE events without prior anticoagulation order

```sql
SELECT
  encntr_id,
  cond_key,
  cmp_pe,
  tx_anticoag,
  icu_use,
  length_of_stay_days,
  inpatient_mortality,
  loc_facility_cd,
  admit_month
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE is_inpatient = 1
  AND (cond_key = 'pe' OR cmp_pe = 1)
  AND tx_anticoag = 0
ORDER BY admit_month DESC
LIMIT 500
```

### Look up anticoagulant order concepts by catalog code

```sql
SELECT
  catalog_cd,
  COUNT(DISTINCT encntr_id) AS n_encounters,
  COUNT(*)                  AS n_orders
FROM greenwood_dbw_catalog.greenwood_ehr.orders
WHERE LOWER(catalog_cd) LIKE '%heparin%'
   OR LOWER(catalog_cd) LIKE '%enoxaparin%'
   OR LOWER(catalog_cd) LIKE '%fondaparinux%'
GROUP BY catalog_cd
ORDER BY n_orders DESC
```

### PE outcomes with comorbidity risk adjustment

```sql
SELECT
  f.encntr_id,
  f.loc_facility_cd,
  f.admit_month,
  f.cond_key,
  f.cmp_pe,
  f.icu_use,
  f.inpatient_mortality,
  f.length_of_stay_days,
  f.tx_anticoag,
  f.elixhauser_van_walraven_score,
  f.elixhauser_comorbidity_count
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features AS f
WHERE f.is_inpatient = 1
  AND (f.cond_key = 'pe' OR f.cmp_pe = 1)
ORDER BY f.admit_month DESC
LIMIT 1000
```

### Verify the PE condition spec entry

```sql
SELECT
  cond_key,
  dx_primary,
  dx_severe,
  sec_codes,
  icu_p,
  mort_p,
  severe_p
FROM greenwood_dbw_catalog.greenwood_ehr.condition_spec
WHERE cond_key = 'pe'
```

## Building the governed VTE asset (Tier-3 write pattern)

`pop_vte` does not currently exist as a registered population in the Greenwood EHR semantic layer.
This section provides the full, copy-pasteable DDL to create it, mirroring the existing
`pop_sepsis` / `pop_stroke_mi` pattern from `population_definition`.

**Why Tier 3 is required for this write path.** The framework's write-eligibility gate
(spec §2.2) blocks any `CREATE`, `INSERT`, or DDL statement in a Tier-2 skill. A Tier-2 skill
attempting this DDL would be rejected by the gate. Because `vte-cohort-analyzer` is Tier 3
(regulated PHI + council + security approval), CREATE/write SQL is permitted here.

---

### Step 1 — Create the scalar predicate function

The `pop_<x>()` functions take the columns they test as arguments (scalar predicate pattern).
`pop_vte` tests `cond_key` (for existing `pe` registrations) and `cmp_pe` (for in-hospital PE
complications). DVT is captured via `cmp_pe = 1` until a `dvt` `cond_key` is added.

```sql
CREATE OR REPLACE FUNCTION greenwood_dbw_catalog.greenwood_ehr.pop_vte(
  cond_key STRING,
  cmp_pe   INT
)
RETURNS BOOLEAN
RETURN cond_key IN ('pe', 'dvt') OR cmp_pe = 1
```

---

### Step 2 — Materialize the cohort table

```sql
CREATE OR REPLACE TABLE greenwood_dbw_catalog.greenwood_ehr.pop_vte_tbl AS
SELECT
  encntr_id,
  person_id,
  cond_key,
  encntr_type_cd,
  is_inpatient,
  admit_dt_tm,
  disch_dt_tm,
  admit_month,
  attending_prsnl_id,
  loc_facility_cd,
  is_severe,
  icu_use,
  length_of_stay_days,
  expired,
  inpatient_mortality,
  disch_disposition_cd,
  readmit_30d,
  order_cost,
  bed_cost,
  total_cost,
  any_complication,
  cmp_pe,
  tx_anticoag,
  tx_intubation,
  elixhauser_van_walraven_score,
  elixhauser_comorbidity_count,
  age_years,
  sex_cd,
  race_cd
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE greenwood_dbw_catalog.greenwood_ehr.pop_vte(cond_key, cmp_pe) = true
  AND is_inpatient = 1
```

---

### Step 3 — Create the metric view

The metric view computes prophylaxis rate and VTE outcome rate per month per facility, mirroring
the existing `mv_readmit_endpoint` / `mv_icu_endpoint` shape.

```sql
CREATE OR REPLACE VIEW greenwood_dbw_catalog.greenwood_ehr.mv_vte_endpoint AS
SELECT
  loc_facility_cd,
  DATE_TRUNC('month', admit_month)                              AS month,
  COUNT(*)                                                      AS n_encounters,
  SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END)
                                                                AS n_vte_events,
  ROUND(
    100.0 * SUM(CASE WHEN cond_key = 'pe' OR cmp_pe = 1 THEN 1 ELSE 0 END)
    / NULLIF(COUNT(*), 0), 2
  )                                                             AS vte_rate_pct,
  SUM(tx_anticoag)                                              AS n_anticoag_ordered,
  ROUND(
    100.0 * SUM(tx_anticoag) / NULLIF(COUNT(*), 0), 2
  )                                                             AS prophylaxis_rate_pct,
  AVG(length_of_stay_days)                                      AS avg_los,
  SUM(inpatient_mortality)                                      AS n_deaths,
  ROUND(
    100.0 * SUM(inpatient_mortality) / NULLIF(COUNT(*), 0), 2
  )                                                             AS mortality_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.pop_vte_tbl
GROUP BY loc_facility_cd, DATE_TRUNC('month', admit_month)
```

---

### Step 4 — Register in population_definition

After creating the objects above, insert the registration record so downstream skills and the
CEDAR population catalog recognize `pop_vte` as a governed cohort:

```sql
INSERT INTO greenwood_dbw_catalog.greenwood_ehr.population_definition
  (function_name, population_label, definition_predicate, population_table)
VALUES
  ('pop_vte', 'VTE (DVT/PE)',
   'cond_key IN (''pe'',''dvt'') OR cmp_pe = 1',
   'pop_vte_tbl')
```

---

Once `pop_vte_tbl` is materialized, all SELECT-based skills (including read-only Tier-2 skills
downstream) can join to it without Tier-3 authorization — the governed asset is now part of the
semantic layer.

## Recommendations framework

After analyzing VTE outcomes or building the cohort asset, always include:

1. **PSI-12 scope note** — clarify whether the query covers hospital-acquired VTE only
   (length_of_stay_days >= 2, cmp_pe flag) or all VTE encounters (cond_key = 'pe' OR cmp_pe = 1),
   since the denominator and interpretation differ materially.
2. **ORDERED vs ADMINISTERED caveat** — if the analysis uses `tx_anticoag` or order counts from
   `orders`, note explicitly that these reflect orders placed, not confirmed administrations;
   adherence rates derived from orders alone overstate actual prophylaxis delivery.
3. **Prophylaxis gap** — highlight encounters with VTE events but `tx_anticoag = 0` as the
   actionable quality gap; this is the PSI-12 improvement target.
4. **Facility stratification** — always break down rates by `loc_facility_cd`; facility-level
   variation is the primary signal for quality improvement teams.
5. **Asset-generation hand-off** — if `pop_vte_tbl` does not yet exist and the user needs
   cross-cohort comparisons or `elixhauser-comorbidity-profiler` joins, route to the DDL in the
   asset-generation section above and note that execution requires Tier-3 authorization.

## Edge cases

- **DVT cond_key gap** — DVT (I82.x) has no standalone `cond_key` in `condition_spec`. Until the
  `dvt` row is added, DVT coverage relies on `cmp_pe = 1` (which captures PE complications, not
  pure DVT). When the `dvt` cond_key is added, update the `pop_vte()` predicate function in place
  using `CREATE OR REPLACE`.
- **ORDERED vs ADMINISTERED** — `tx_anticoag` in `population_endpoint_features` is an order-based
  flag. `orders.catalog_cd` enables order-level granularity but does not contain administration
  records. True administration data requires a separate medication-administration table not
  currently in scope.
- **24-48h window** — the 24-48h prophylaxis quality window cannot be computed solely from
  `population_endpoint_features` (no order timestamp is available there). If timestamp-level
  adherence is needed, join to `orders` on `encntr_id` and filter by order time relative to
  `admit_dt_tm`.
- **PSI-12 POA exclusion** — Present-on-Admission exclusion requires the POA indicator from the
  raw diagnosis record; `population_endpoint_features` does not expose this flag. Treat
  `length_of_stay_days >= 2` with `cmp_pe = 1` as the best available proxy and document the
  approximation in any quality report.
- **cmp_pe scope** — `cmp_pe` captures PE as a complication of an admission for another primary
  condition. Encounters where PE is the primary admission diagnosis (cond_key = 'pe') are not
  complications; include both in VTE burden counts but separate them in quality analyses.
- **pop_vte_tbl refresh** — after initial creation, `pop_vte_tbl` is a static snapshot.
  Schedule a periodic `CREATE OR REPLACE TABLE` refresh (e.g. monthly via a Databricks job) to
  keep the cohort current.

## Data scope

- `greenwood_dbw_catalog.greenwood_ehr.condition_spec` — clinical-condition registry; the `pe`
  cond_key (I26.99) exists; DVT cond_key does not (the gap this skill addresses).
- `greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features` — per-encounter feature and
  outcome table; key VTE columns: `cond_key`, `cmp_pe`, `tx_anticoag`, `inpatient_mortality`,
  `icu_use`, `length_of_stay_days`, `admit_month`, `loc_facility_cd`, `encntr_id`.
- `greenwood_dbw_catalog.greenwood_ehr.orders` — order-level records with `catalog_cd` for
  distinguishing pharmacological prophylaxis order concepts (LMWH, UFH, fondaparinux) from
  mechanical (SCD/GCS); order placement only, not administration.
- `greenwood_dbw_catalog.greenwood_ehr.pop_vte_tbl` — governed VTE cohort table (created by the
  asset-generation DDL in this skill when it does not yet exist); joins available to all skills
  once materialized.
- Identifier tables (`person`, `prsnl`, `clinical_note`, `clinical_note_flags`) are never
  referenced by this skill.
