---
name: readmission-cohort-analyzer
description: Analyze CMS HWR 30-day all-cause unplanned readmission outcomes and risk-adjusted
  burden from the Greenwood EHR semantic layer — reusing the governed pop_readmit_30d cohort asset
  and mv_readmit_endpoint metric view.
---

# readmission-cohort-analyzer

## Overview

A Tier-3 clinical outcome skill: it analyzes 30-day all-cause unplanned readmission encounters
across the Greenwood EHR inpatient population using the governed semantic layer. It reads two
primary objects in `greenwood_dbw_catalog.greenwood_ehr`:

- **`pop_readmit_30d_tbl`** — the materialized 30-day readmission cohort table, pre-filtered by
  the governed `pop_readmit_30d()` scalar predicate (`readmit_30d = 1`). This skill reuses the
  existing governed `pop_readmit_30d()` function and its materialized table rather than
  redefining the cohort predicate. Reuse over reinvention: every encounter qualifying as a
  30-day readmission is automatically in scope once `pop_readmit_30d_tbl` is refreshed.
  This table is richer than the analogous sepsis/stroke cohort tables and carries demographic,
  utilization, comorbidity, complication, and treatment escalation columns directly.
  Confirmed columns: `encntr_id`, `person_id`, `cond_key`, `encntr_type_cd`, `admit_month`,
  `age_years`, `sex_cd`, `race_cd`, `loc_facility_cd`, `is_inpatient`, `icu_use`,
  `length_of_stay_days`, `total_cost`, `order_count`, `imaging_count`, `procedure_count`,
  `disch_disposition_cd`, `snf_rehab`, `ed_visit`, `died`, `any_complication`, `cmp_aki`,
  `cmp_sepsis`, `cmp_pe`, `cmp_gibleed`, `cmp_arrhythmia`, `tx_vasopressor`, `tx_intubation`,
  `tx_dialysis`, `telemetry_candidate`, `escalated`, `elixhauser_van_walraven_score`,
  `elixhauser_comorbidity_count`. Note: this table uses `admit_month` (not `admit_dt_tm`),
  uses `died` for in-readmission mortality (not `inpatient_mortality`), and does not carry
  a `readmit_30d` column (readmission IS the cohort filter). There is no `tx_tpa`,
  `tx_thrombectomy`, `tx_pci`, `tx_antibiotics`, or `tx_anticoag` column on this table.
- **`mv_readmit_endpoint`** — the governed readmission-rate metric view. Provides pre-aggregated
  readmission counts, patient counts, observed mortality rate, ICU rate, average van Walraven
  score, average LOS, complication rate, and average cost, dimensioned by `Condition` and
  `Facility`. Query this view for facility-level readmission-rate benchmarks and comorbidity
  burden summaries without needing to aggregate the raw cohort table. Measure columns must be
  wrapped in `MEASURE()` per Databricks metric view syntax.

An optional supplementary source is `population_endpoint_features`, which carries the full
per-encounter feature set (including `readmit_30d`, `days_to_next`, and therapy flags not
present on the cohort table) for cross-cohort comparisons.

**Clinical framing — CMS HRRP / HWR 30-day all-cause readmission.** The Centers for Medicare
and Medicaid Services (CMS) Hospital Readmissions Reduction Program (HRRP) measures
all-cause unplanned readmissions within 30 days of discharge for a set of index admission
conditions. The parallel Hospital-Wide Readmission (HWR) measure expands scope to all
inpatient discharges regardless of index condition. Both measures exclude planned readmissions
(e.g., scheduled chemotherapy, elective surgical follow-up) and direct transfers; only
unplanned return admissions count in the numerator. Risk adjustment applies comorbidity
burden (van Walraven composite of the 31 Elixhauser flags) and discharge disposition
(`disch_disposition_cd`, `snf_rehab`) as the primary covariates: higher comorbidity scores
and SNF/rehab discharge dispositions predict higher readmission risk, and unadjusted facility
comparisons are misleading without accounting for these factors.

Key outcomes tracked by this skill:

- **Readmission volume and rate** — the cohort IS the readmitted population; rate denominators
  (all eligible discharges) come from `mv_readmit_endpoint`.
- **In-readmission mortality** (`died`) — mortality occurring during the readmission encounter.
- **Complication burden** (`any_complication`, `cmp_aki`, `cmp_sepsis`, `cmp_pe`,
  `cmp_gibleed`, `cmp_arrhythmia`) — secondary diagnoses arising during the readmission.
- **Escalation and ICU use** (`escalated`, `icu_use`) — intensity-of-care signals.
- **Risk-adjustment covariates** (`elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`,
  `disch_disposition_cd`, `snf_rehab`) — required for CMS-aligned risk-adjusted comparisons.
- **Discharge disposition and SNF/rehab** — `disch_disposition_cd` and `snf_rehab` flag
  encounters discharged to skilled nursing or rehabilitation facilities, which are both a
  readmission risk factor and a transition-of-care quality signal.

## When to use this skill

Reach for this skill when a question involves 30-day readmission burden, post-discharge
stability, or CMS HRRP/HWR quality metrics:

- "What is the readmission rate by facility and condition?"
- "How has 30-day readmission volume trended month over month?"
- "Which comorbidity profile (van Walraven score band) drives the highest readmission burden?"
- "Show me readmission encounters that escalated to ICU, broken down by facility."
- "What proportion of readmitted patients were discharged to SNF or rehab on the index stay?"
- "Which conditions have the highest readmission-associated complication rates?"
- "Compare observed mortality rates across facilities from the mv_readmit_endpoint view."
- "Show me average cost and LOS for readmission encounters stratified by comorbidity band."

## Instructions

When the user asks a readmission analysis question:

1. **Identify the analysis type** — readmission volume/rate trend, comorbidity risk
   stratification, discharge disposition analysis, complication burden, escalation/ICU profile,
   facility benchmark, or mortality in the readmitted population.
2. **Choose the right starting source:**
   - Encounter-level queries requiring demographic, complication, escalation, or treatment
     columns → query `pop_readmit_30d_tbl` directly. This is the governed cohort table with
     the richest per-encounter column set for readmission.
   - Facility-level readmission rate benchmarks and pre-aggregated burden summaries →
     query `mv_readmit_endpoint` with `MEASURE()` wrapping for measure columns.
   - Cross-cohort comparisons or queries needing `days_to_next` or therapy flags not on the
     cohort table → query `population_endpoint_features WHERE readmit_30d = 1`.
3. **Use `admit_month` for time bucketing** — `pop_readmit_30d_tbl` carries `admit_month`
   (TIMESTAMP type, truncated to month) rather than a raw `admit_dt_tm`. Group on `admit_month`
   directly; do not apply `DATE_TRUNC` on top of it.
4. **Risk-adjust by comorbidity and discharge disposition** — include
   `elixhauser_van_walraven_score` as a continuous risk covariate or bin it into bands (e.g.,
   score < 5, 5–10, 10–15, >= 15). Include `disch_disposition_cd` and `snf_rehab` to surface
   disposition-driven readmission risk. Unadjusted readmission rates may reflect case-mix
   differences rather than quality variation.
5. **Exclude planned readmissions** — the governed `pop_readmit_30d()` predicate applies the
   HRRP unplanned-readmission filter at cohort build time. If the user asks about planned
   readmissions separately, route them to `population_endpoint_features` and note that the
   cohort table already excludes planned returns.
6. **Stratify** by `loc_facility_cd` and `cond_key` to surface facility-level and
   condition-specific variation. Facility variation in readmission rates after comorbidity
   adjustment is the primary quality signal for readmission reduction programs.
7. **mv_readmit_endpoint syntax** — all measure columns (`Readmission Encounters`, `Patients`,
   `Observed Mortality Rate`, `Avg van Walraven Score`, `ICU Rate`, `Avg LOS`, `Complication
   Rate`, `Avg Cost`, `Expected Mortality (VW-weighted)`) require `MEASURE(<col>)` wrapping.
   Dimension columns (`Condition`, `Facility`, `Comorbidity Band`, `Age Band`) do not.

## Examples

### Readmission volume and burden by facility and condition — monthly trend

Uses `pop_readmit_30d_tbl` (columns available: `admit_month`, `loc_facility_cd`, `cond_key`,
`icu_use`, `any_complication`, `died`, `length_of_stay_days`, `total_cost`,
`elixhauser_van_walraven_score`).

```sql
SELECT
  loc_facility_cd,
  admit_month,
  cond_key,
  COUNT(*)                                                              AS n_readmissions,
  SUM(icu_use)                                                          AS n_icu,
  ROUND(100.0 * SUM(icu_use) / NULLIF(COUNT(*), 0), 2)                 AS icu_rate_pct,
  SUM(any_complication)                                                 AS n_complications,
  ROUND(100.0 * SUM(any_complication) / NULLIF(COUNT(*), 0), 2)        AS complication_rate_pct,
  SUM(died)                                                             AS n_died,
  ROUND(100.0 * SUM(died) / NULLIF(COUNT(*), 0), 2)                    AS mortality_rate_pct,
  ROUND(AVG(length_of_stay_days), 1)                                   AS avg_los,
  ROUND(AVG(total_cost), 0)                                             AS avg_cost
FROM greenwood_dbw_catalog.greenwood_ehr.pop_readmit_30d_tbl
GROUP BY loc_facility_cd, admit_month, cond_key
ORDER BY admit_month DESC, loc_facility_cd
```

### Risk stratification by comorbidity band and discharge disposition

Risk-adjust by van Walraven score band and discharge disposition to surface case-mix-driven
readmission burden. Uses `disch_disposition_cd`, `snf_rehab`, `died`, `elixhauser_van_walraven_score`.

```sql
SELECT
  CASE
    WHEN elixhauser_van_walraven_score < 5  THEN 'Low (< 5)'
    WHEN elixhauser_van_walraven_score < 10 THEN 'Moderate (5–9)'
    WHEN elixhauser_van_walraven_score < 15 THEN 'High (10–14)'
    ELSE 'Very High (>= 15)'
  END                                                                   AS vw_band,
  disch_disposition_cd,
  snf_rehab,
  COUNT(*)                                                              AS n_readmissions,
  ROUND(AVG(length_of_stay_days), 1)                                   AS avg_los,
  ROUND(AVG(total_cost), 0)                                             AS avg_cost,
  SUM(died)                                                             AS n_died,
  ROUND(100.0 * SUM(died) / NULLIF(COUNT(*), 0), 2)                    AS mortality_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.pop_readmit_30d_tbl
GROUP BY vw_band, disch_disposition_cd, snf_rehab
ORDER BY vw_band, disch_disposition_cd
```

### Facility-level readmission rates from the metric view

Uses `mv_readmit_endpoint` with `MEASURE()` syntax. Returns readmission counts, patient
counts, observed mortality, average van Walraven score, and ICU rate pre-aggregated by
condition and facility.

```sql
SELECT
  `Condition`,
  `Facility`,
  MEASURE(`Readmission Encounters`)                   AS readmission_encounters,
  MEASURE(`Patients`)                                 AS patients,
  MEASURE(`Observed Mortality Rate`)                  AS observed_mortality_rate,
  MEASURE(`Avg van Walraven Score`)                   AS avg_vw_score,
  MEASURE(`ICU Rate`)                                 AS icu_rate,
  MEASURE(`Avg LOS`)                                  AS avg_los,
  MEASURE(`Avg Cost`)                                 AS avg_cost,
  MEASURE(`Complication Rate`)                        AS complication_rate
FROM greenwood_dbw_catalog.greenwood_ehr.mv_readmit_endpoint
GROUP BY `Condition`, `Facility`
ORDER BY readmission_encounters DESC
```

### Complication profile for readmission encounters with escalation

Uses complication flags (`cmp_aki`, `cmp_sepsis`, `cmp_pe`, `cmp_gibleed`, `cmp_arrhythmia`)
and escalation/ICU signals directly from `pop_readmit_30d_tbl`.

```sql
SELECT
  loc_facility_cd,
  cond_key,
  escalated,
  icu_use,
  COUNT(*)                                                              AS n_encounters,
  SUM(cmp_aki)                                                          AS n_cmp_aki,
  SUM(cmp_sepsis)                                                       AS n_cmp_sepsis,
  SUM(cmp_pe)                                                           AS n_cmp_pe,
  SUM(cmp_arrhythmia)                                                   AS n_cmp_arrhythmia,
  ROUND(AVG(elixhauser_van_walraven_score), 2)                          AS avg_vw_score,
  SUM(died)                                                             AS n_died
FROM greenwood_dbw_catalog.greenwood_ehr.pop_readmit_30d_tbl
WHERE escalated = 1 OR icu_use = 1
GROUP BY loc_facility_cd, cond_key, escalated, icu_use
ORDER BY n_encounters DESC
```

### Overall monthly trend — aggregate readmission burden

```sql
SELECT
  admit_month,
  COUNT(*)                                                              AS n_readmissions,
  ROUND(AVG(elixhauser_van_walraven_score), 2)                         AS avg_vw_score,
  ROUND(AVG(length_of_stay_days), 1)                                   AS avg_los,
  SUM(icu_use)                                                          AS n_icu,
  SUM(died)                                                             AS n_died,
  SUM(any_complication)                                                 AS n_complications
FROM greenwood_dbw_catalog.greenwood_ehr.pop_readmit_30d_tbl
GROUP BY admit_month
ORDER BY admit_month DESC
```

## Recommendations framework

After analyzing 30-day readmission outcomes, always include:

1. **Volume and rate context** — report readmission counts from `pop_readmit_30d_tbl` alongside
   facility-level rates from `mv_readmit_endpoint`; raw counts without denominators are
   misleading for facility comparisons. The metric view provides the rate denominator
   (all eligible discharges) in a single query.
2. **Risk-adjustment disclosure** — always report `avg_vw_score` alongside unadjusted rates.
   High van Walraven scores indicate a complex-comorbidity population; unadjusted comparisons
   across facilities may reflect case-mix rather than quality differences. For formal CMS
   HRRP risk adjustment, note that the hierarchical logistic model also incorporates age and
   discharge disposition as covariates.
3. **Discharge disposition breakdown** — include `disch_disposition_cd` and `snf_rehab` in
   any readmission root-cause analysis. A high proportion of SNF/rehab discharges on the index
   stay signals that transition-of-care quality (coordination with receiving facilities) may be
   driving readmission risk.
4. **Complication and escalation flags** — when reporting readmission severity, surface
   `any_complication`, `escalated`, and `icu_use` rates. High complication rates during
   readmission admissions indicate that patients are returning in a deteriorated state and
   may point to under-treatment at discharge or inadequate follow-up instructions.
5. **Mortality caveat** — `died` on `pop_readmit_30d_tbl` reflects mortality during the
   readmission encounter, not the index admission. Report it as in-readmission mortality to
   avoid confusion with the original admission's outcome.
6. **Planned readmission exclusion note** — confirm to the user that `pop_readmit_30d_tbl`
   applies the HRRP unplanned filter at build time. If the question is about planned returns
   (e.g., scheduled chemotherapy cycles), route to `population_endpoint_features` and
   document the exclusion.
7. **Facility stratification** — always break down rates by `loc_facility_cd`; facility
   variation in risk-adjusted readmission rates is the primary signal for readmission
   reduction program prioritization.

## Edge cases

- **`admit_month` type** — `pop_readmit_30d_tbl` carries `admit_month` as a TIMESTAMP value
  truncated to the first of each month (confirmed live: values like `2026-07-01T00:00:00`).
  Group on it directly; do not apply `DATE_TRUNC('month', admit_month)` which would be a
  no-op but adds confusion. Do not compare it to `admit_dt_tm` — there is no `admit_dt_tm`
  column on this table.
- **`died` vs `inpatient_mortality`** — `pop_readmit_30d_tbl` uses `died` for encounter
  mortality; `inpatient_mortality` does not exist on this table. When joining with or comparing
  to `population_endpoint_features`, note that the two columns are semantically equivalent
  but column names differ. Never use `inpatient_mortality` in a query against this table.
- **No `readmit_30d` column** — the table IS the readmission cohort; the filter has already
  been applied. There is no `readmit_30d` column to filter on. If the user asks "filter to
  readmissions only," confirm that the cohort table already applies this filter.
- **mv_readmit_endpoint MEASURE() requirement** — all measure columns (any column that is not
  `Condition`, `Facility`, `Comorbidity Band`, or `Age Band`) must be wrapped in `MEASURE()`.
  Queries that SELECT measure columns without `MEASURE()` will fail with
  `METRIC_VIEW_MISSING_MEASURE_FUNCTION`. Dimension columns do not require wrapping.
- **Planned vs unplanned readmission exclusion** — HRRP excludes planned readmissions (elective
  surgical follow-up, scheduled chemotherapy, planned rehab) and transfers. The governed
  `pop_readmit_30d()` predicate applies this exclusion at build time. If a user believes a
  planned readmission is in the cohort, the appropriate response is to inspect the encounter's
  `disch_disposition_cd` and review the index condition against CMS planned-readmission lists
  rather than re-filtering in SQL.
- **pop_readmit_30d_tbl refresh** — the cohort table is a static snapshot. Schedule periodic
  `CREATE OR REPLACE TABLE` refreshes to keep it current; staleness is the primary data
  quality risk for month-over-month trending analyses.
- **Complication flag scope** — `cmp_aki`, `cmp_sepsis`, `cmp_pe`, `cmp_gibleed`, and
  `cmp_arrhythmia` are binary flags indicating that the complication was coded during the
  readmission encounter. They do not carry severity gradations or onset timing. For AKI
  staging (KDIGO) or sepsis severity (SOFA), a join to `population_endpoint_features` and
  the `elixhauser_encounter` table is required.
- **Treatment flags** — `tx_vasopressor`, `tx_intubation`, and `tx_dialysis` are available
  on `pop_readmit_30d_tbl` and reflect treatment-ordered flags during the readmission encounter.
  There is no `tx_tpa`, `tx_thrombectomy`, `tx_pci`, `tx_antibiotics`, or `tx_anticoag` on
  this table. For anticoagulation or antibiotic ordering analysis during readmissions, source
  from `population_endpoint_features WHERE readmit_30d = 1` instead.
- **CMS risk adjustment model** — CMS HRRP uses hierarchical logistic regression models with
  age, comorbidity, and discharge disposition as covariates; the exact model coefficients are
  not stored in the semantic layer. The `elixhauser_van_walraven_score` is the closest
  available proxy. For formal risk-adjusted comparisons, refer to the
  `elixhauser-comorbidity-profiler` skill.

## Data scope

- `greenwood_dbw_catalog.greenwood_ehr.pop_readmit_30d_tbl` — governed 30-day readmission cohort
  table, materialized by the `pop_readmit_30d()` predicate (`readmit_30d = 1`). All rows are
  readmission encounters; no additional filter needed. Columns: `encntr_id`, `person_id`,
  `cond_key`, `encntr_type_cd`, `admit_month`, `age_years`, `sex_cd`, `race_cd`,
  `loc_facility_cd`, `is_inpatient`, `icu_use`, `length_of_stay_days`, `total_cost`,
  `order_count`, `imaging_count`, `procedure_count`, `disch_disposition_cd`, `snf_rehab`,
  `ed_visit`, `died`, `any_complication`, `cmp_aki`, `cmp_sepsis`, `cmp_pe`, `cmp_gibleed`,
  `cmp_arrhythmia`, `tx_vasopressor`, `tx_intubation`, `tx_dialysis`, `telemetry_candidate`,
  `escalated`, `elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`. Does NOT
  contain `admit_dt_tm`, `inpatient_mortality`, `readmit_30d`, `tx_tpa`, `tx_thrombectomy`,
  `tx_pci`, `tx_antibiotics`, or `tx_anticoag`.
- `greenwood_dbw_catalog.greenwood_ehr.mv_readmit_endpoint` — governed readmission-rate metric
  view. Dimension columns: `Condition`, `Facility`, `Comorbidity Band`, `Age Band`. Measure
  columns (require `MEASURE()` wrapping): `Readmission Encounters`, `Patients`,
  `Observed Mortality Rate`, `Avg van Walraven Score`, `Avg Comorbidity Count`, `Avg LOS`,
  `ICU Rate`, `Complication Rate`, `Avg Cost`, `Expected Mortality (VW-weighted)`. Use for
  facility-level readmission rate benchmarks without aggregating the raw cohort table.
- `greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features` — per-encounter feature
  and outcome table (optional supplementary source). Filter with `readmit_30d = 1` to scope
  to readmissions. Carries `days_to_next`, `tx_antibiotics`, `tx_anticoag`, `tx_tpa`,
  `inpatient_mortality`, and `admit_dt_tm` — columns not present on `pop_readmit_30d_tbl`.
  Use for cross-cohort comparisons or when those specific columns are needed.
- Identifier tables (`person`, `prsnl`, `clinical_note`, `clinical_note_flags`) are never
  referenced by this skill.
