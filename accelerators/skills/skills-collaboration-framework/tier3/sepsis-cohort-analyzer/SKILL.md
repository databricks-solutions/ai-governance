---
name: sepsis-cohort-analyzer
description: Analyze sepsis cohort outcomes (in-hospital mortality, ICU transfer, LOS) and
  SEP-1 bundle compliance from the VCH Cerner semantic layer — reusing the governed pop_sepsis
  cohort asset and Sepsis-3 / CMS SEP-1 clinical framing.
---

# sepsis-cohort-analyzer

## Overview

A Tier-3 clinical outcome skill: it analyzes sepsis encounter outcomes across the VCH Cerner
inpatient population using the governed semantic layer. It reads three objects in
`greenwood_dbw_catalog.vch_cerner`:

- **`pop_sepsis_tbl`** — the materialized sepsis cohort table, pre-filtered by the governed
  `pop_sepsis()` scalar predicate (`cond_key = 'sepsis' OR cmp_sepsis = 1`). This skill reuses
  the existing governed `pop_sepsis()` function and its materialized table rather than
  redefining the cohort predicate. Reuse over reinvention: every sepsis encounter added to the
  semantic layer is automatically in scope once `pop_sepsis_tbl` is refreshed.
- **`population_endpoint_features`** — per-encounter feature and outcome table. Key sepsis
  columns: `inpatient_mortality`, `icu_use`, `length_of_stay_days`, `cmp_sepsis`, `admit_month`,
  `loc_facility_cd`, `tx_antibiotics`, `tx_vasopressor`, `escalated`, `encntr_id`, `cond_key`.
  Use for outcome queries that need the full feature set, comorbidity covariates, or comparison
  across conditions.
- **`condition_spec`** — clinical-condition registry. The `sepsis` row carries `cond_key =
  'sepsis'`, `dx_primary = 'A41.9'` (sepsis due to unspecified organism). Use to verify the
  canonical ICD-10 anchor and read the calibrated probability fields (`severe_p`, `icu_p`,
  `mort_p`) that describe the population's expected severity profile.

**Clinical framing — Sepsis-3 and CMS SEP-1.** The platform applies the Sepsis-3 consensus
definition (Singer et al., JAMA 2016): life-threatening organ dysfunction caused by a
dysregulated host response to infection, operationalized via SOFA and qSOFA scores.
The CMS SEP-1 Core Measure bundle tracks six-hour compliance for antibiotic administration,
blood cultures, vasopressor initiation, and fluid resuscitation. Explicit ICD-10 coding
(A40.x, A41.x) anchors cohort entry; the R65.2x severe-sepsis/septic-shock codes augment it.
When explicit coding density is low (retrospective or under-coded encounters), the Rhee
surveillance definition (Rhee et al., Clin Infect Dis 2018) — organ dysfunction proxies
(vasopressor initiation, mechanical ventilation, lactate, creatinine rise) without requiring
an explicit sepsis diagnosis code — serves as the retrospective fallback. `cmp_sepsis = 1` in
`population_endpoint_features` captures encounters where sepsis was coded as a complication of
a non-sepsis primary admission.

Key outcomes tracked by this skill: **in-hospital mortality** (`inpatient_mortality`), **ICU
transfer** (`icu_use`), and **length of stay** (`length_of_stay_days`).

## When to use this skill

Reach for this skill when a question involves sepsis burden, outcomes, or SEP-1 bundle
compliance:

- "What is the in-hospital mortality rate for sepsis encounters by facility?"
- "How has ICU transfer rate for sepsis patients trended over the past 12 months?"
- "Show me average LOS for sepsis encounters stratified by vasopressor use."
- "What proportion of sepsis encounters escalated but survived?"
- "How does sepsis complication burden (cmp_sepsis) differ across facilities?"
- "What is the antibiotic and vasopressor ordering rate for the sepsis cohort?"
- "Read the condition spec for sepsis to confirm its ICD-10 anchor and calibrated probabilities."

## Instructions

When the user asks a sepsis analysis question:

1. **Identify the analysis type** — outcome rate (mortality, ICU, LOS), SEP-1 bundle compliance
   (antibiotic/vasopressor ordering), escalation patterns, or temporal/facility trend.
2. **Choose the right starting table:**
   - Cohort-scoped queries where the sepsis filter is already applied → join from or query
     `pop_sepsis_tbl` directly. This avoids re-applying the predicate and is the preferred path
     for cohort-level aggregations.
   - Queries that need to compare sepsis encounters against a broader population, or that require
     comorbidity columns not on `pop_sepsis_tbl` → query `population_endpoint_features` with
     `cond_key = 'sepsis' OR cmp_sepsis = 1`.
3. **Apply the condition spec** — when answering questions about the clinical definition, coding
   anchor, or expected severity distribution, query `condition_spec WHERE cond_key = 'sepsis'`
   to surface `dx_primary`, `sec_codes`, `severe_p`, `icu_p`, and `mort_p`.
4. **Stratify** by `loc_facility_cd` and `icu_use` to surface facility-level variation. For
   time-bucketing, use `DATE_TRUNC('month', admit_dt_tm)` when querying `pop_sepsis_tbl`
   (which carries `admit_dt_tm` but not `admit_month`); use `DATE_TRUNC('month', admit_month)`
   when querying `population_endpoint_features`. Facility variation is the primary signal for
   quality improvement teams.
5. **SEP-1 bundle proxies** — use `tx_antibiotics` and `tx_vasopressor` from
   `population_endpoint_features` as the available proxies for SEP-1 bundle elements. Note that
   these are order-based flags (ordered, not confirmed-administered); report them as ordering
   rates and explicitly qualify the limitation.
6. **Rhee fallback** — if the user asks about retrospective surveillance or under-coded periods,
   note that the Rhee definition can be approximated by combining `cmp_sepsis = 1` with
   `tx_vasopressor = 1` or `tx_antibiotics = 1` as organ-dysfunction proxies, and that a
   dedicated surveillance rule would require validation against raw order timestamps.

## Examples

### Sepsis ICU rate, LOS, and readmission by facility — monthly trend

Uses `pop_sepsis_tbl` (columns available: `icu_use`, `length_of_stay_days`, `readmit_30d`,
`admit_dt_tm`, `loc_facility_cd`). For mortality trends use the `population_endpoint_features`
example below, which carries `inpatient_mortality`.

```sql
SELECT
  loc_facility_cd,
  DATE_TRUNC('month', admit_dt_tm)                                  AS month,
  COUNT(*)                                                          AS n_encounters,
  SUM(icu_use)                                                      AS n_icu_transfers,
  ROUND(100.0 * SUM(icu_use) / NULLIF(COUNT(*), 0), 2)             AS icu_rate_pct,
  ROUND(AVG(length_of_stay_days), 1)                               AS avg_los,
  SUM(readmit_30d)                                                  AS n_readmissions,
  ROUND(100.0 * SUM(readmit_30d) / NULLIF(COUNT(*), 0), 2)         AS readmit_rate_pct
FROM greenwood_dbw_catalog.vch_cerner.pop_sepsis_tbl
GROUP BY loc_facility_cd, DATE_TRUNC('month', admit_dt_tm)
ORDER BY month DESC, loc_facility_cd
```

### Outcomes from population_endpoint_features — sepsis and complication encounters

```sql
SELECT
  encntr_id,
  cond_key,
  cmp_sepsis,
  inpatient_mortality,
  icu_use,
  length_of_stay_days,
  tx_antibiotics,
  tx_vasopressor,
  escalated,
  loc_facility_cd,
  admit_month
FROM greenwood_dbw_catalog.vch_cerner.population_endpoint_features
WHERE cond_key = 'sepsis' OR cmp_sepsis = 1
ORDER BY admit_month DESC
LIMIT 1000
```

### SEP-1 bundle ordering rates by facility

```sql
SELECT
  loc_facility_cd,
  COUNT(*)                                                              AS n_sepsis,
  SUM(tx_antibiotics)                                                   AS n_antibiotics_ordered,
  ROUND(100.0 * SUM(tx_antibiotics) / NULLIF(COUNT(*), 0), 2)          AS antibiotics_rate_pct,
  SUM(tx_vasopressor)                                                   AS n_vasopressor_ordered,
  ROUND(100.0 * SUM(tx_vasopressor) / NULLIF(COUNT(*), 0), 2)          AS vasopressor_rate_pct,
  SUM(inpatient_mortality)                                              AS n_deaths,
  ROUND(100.0 * SUM(inpatient_mortality) / NULLIF(COUNT(*), 0), 2)     AS mortality_rate_pct
FROM greenwood_dbw_catalog.vch_cerner.population_endpoint_features
WHERE cond_key = 'sepsis' OR cmp_sepsis = 1
GROUP BY loc_facility_cd
ORDER BY mortality_rate_pct DESC
```

### Escalation and mortality — survival analysis

`escalated` and `inpatient_mortality` are available on `population_endpoint_features` only
(not on the narrower `pop_sepsis_tbl`).

```sql
SELECT
  escalated,
  icu_use,
  COUNT(*)                                                              AS n_encounters,
  SUM(inpatient_mortality)                                              AS n_deaths,
  ROUND(100.0 * SUM(inpatient_mortality) / NULLIF(COUNT(*), 0), 2)     AS mortality_rate_pct,
  ROUND(AVG(length_of_stay_days), 1)                                   AS avg_los
FROM greenwood_dbw_catalog.vch_cerner.population_endpoint_features
WHERE cond_key = 'sepsis' OR cmp_sepsis = 1
GROUP BY escalated, icu_use
ORDER BY escalated DESC, icu_use DESC
```

### LOS distribution by vasopressor use and facility

```sql
SELECT
  loc_facility_cd,
  tx_vasopressor,
  COUNT(*)                                                             AS n_encounters,
  ROUND(AVG(length_of_stay_days), 1)                                  AS avg_los,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY length_of_stay_days)   AS median_los,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY length_of_stay_days)   AS p75_los
FROM greenwood_dbw_catalog.vch_cerner.population_endpoint_features
WHERE cond_key = 'sepsis' OR cmp_sepsis = 1
GROUP BY loc_facility_cd, tx_vasopressor
ORDER BY loc_facility_cd, tx_vasopressor DESC
```

### Read the sepsis condition spec

```sql
SELECT
  cond_key,
  dx_primary,
  dx_severe,
  sec_codes,
  severe_p,
  icu_p,
  mort_p,
  chronic,
  weight
FROM greenwood_dbw_catalog.vch_cerner.condition_spec
WHERE cond_key = 'sepsis'
```

## Recommendations framework

After analyzing sepsis outcomes, always include:

1. **Mortality and ICU summary** — report overall `inpatient_mortality` rate and `icu_use` rate
   for the cohort period; these are the two primary outcome signals for sepsis quality reviews.
2. **LOS distribution** — report mean and median `length_of_stay_days`; ICU and non-ICU
   subgroups should be reported separately because ICU encounters skew the distribution.
3. **SEP-1 proxy caveat** — when reporting `tx_antibiotics` or `tx_vasopressor` rates, always
   note that these reflect order placement only; confirmed administration rates require the
   medication-administration table which is not in scope here.
4. **Rhee surveillance note** — if the query is from a retrospective period where explicit sepsis
   ICD-10 coding may be sparse (pre-2017 or under-coded encounters), flag that `cmp_sepsis = 1`
   combined with vasopressor or antibiotic ordering provides a retrospective surveillance
   approximation per the Rhee definition (Clin Infect Dis 2018).
5. **Facility stratification** — always break down rates by `loc_facility_cd`; unexplained
   facility variation in mortality or ICU use is the primary signal for quality improvement teams.
6. **Comorbidity hand-off** — for risk-adjusted analysis, refer to the
   `elixhauser-comorbidity-profiler` skill to obtain van Walraven scores as covariates before
   computing risk-adjusted mortality rates.

## Edge cases

- **pop_sepsis_tbl vs population_endpoint_features** — `pop_sepsis_tbl` is a narrow
  materialized snapshot: it carries `icu_use`, `readmit_30d`, `length_of_stay_days`,
  `any_complication`, Elixhauser covariates, and demographics, but does **not** include
  `inpatient_mortality`, `admit_month`, `escalated`, `cmp_sepsis`, or any `tx_*` column.
  Use `pop_sepsis_tbl` for cohort-scoped aggregations over its available columns (preferred,
  governed). Use `population_endpoint_features WHERE cond_key = 'sepsis' OR cmp_sepsis = 1`
  whenever mortality, escalation, bundle compliance (`tx_antibiotics`, `tx_vasopressor`), or
  admit-month time-bucketing is required. `pop_sepsis_tbl` may also lag if not refreshed
  recently; the feature table is always current.
- **cmp_sepsis scope** — `cmp_sepsis = 1` identifies encounters where sepsis arose as a
  complication of an admission with a different primary condition. These encounters are
  included in the governed cohort predicate by design. When reporting pure sepsis-primary
  admissions, filter on `cond_key = 'sepsis'` alone and document the exclusion.
- **ICD-10 coding breadth** — the `sepsis` cond_key anchors on A41.9 (sepsis due to unspecified
  organism). Organism-specific sepsis codes (A40.x for streptococcal, A41.0-A41.5 for
  other organisms) and severe sepsis without shock (R65.20) and septic shock (R65.21) may be coded as
  primary diagnoses without the generic A41.9. The `sec_codes` array in `condition_spec`
  documents the supplementary codes; verify coverage before concluding a case is not in cohort.
- **SEP-1 six-hour window** — CMS SEP-1 compliance requires antibiotic administration within
  three hours and vasopressor initiation within six hours of presentation. `population_endpoint_features`
  does not carry order timestamps; the `tx_antibiotics` and `tx_vasopressor` flags confirm only
  that an order was placed during the encounter. Time-to-treatment analysis requires joining
  to raw order records with admission timestamp.
- **Rhee surveillance vs explicit coding** — the Rhee definition was designed for retrospective
  surveillance when ICD-10 coding is unreliable. Mixing Rhee-identified and ICD-10-identified
  cases without labeling the source creates numerator inconsistency. Choose one identification
  strategy per analysis and document it.
- **pop_sepsis_tbl refresh** — the cohort table is a static snapshot. Schedule periodic
  `CREATE OR REPLACE TABLE` refreshes to keep it current; staleness is the primary data quality
  risk for trending analyses.

## Data scope

- `greenwood_dbw_catalog.vch_cerner.pop_sepsis_tbl` — governed sepsis cohort table, materialized
  by the `pop_sepsis()` predicate (`cond_key = 'sepsis' OR cmp_sepsis = 1`). Available columns:
  `encntr_id`, `person_id`, `cond_key`, `encntr_type_cd`, `admit_dt_tm`, `age_years`, `sex_cd`,
  `race_cd`, `loc_facility_cd`, `icu_use`, `has_surgical_proc`, `readmit_30d`,
  `length_of_stay_days`, `total_cost`, `disch_disposition_cd`, `any_complication`,
  `elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`. This table does **not**
  carry `inpatient_mortality`, `admit_month`, `escalated`, `cmp_sepsis`, or any `tx_*` column —
  use `population_endpoint_features` for those. Preferred join anchor for cohort-scoped
  aggregations over its available columns.
- `greenwood_dbw_catalog.vch_cerner.population_endpoint_features` — per-encounter feature and
  outcome table; key sepsis columns: `inpatient_mortality`, `icu_use`, `length_of_stay_days`,
  `cmp_sepsis`, `admit_month`, `loc_facility_cd`, `tx_antibiotics`, `tx_vasopressor`,
  `escalated`, `encntr_id`, `cond_key`. Also carries Elixhauser comorbidity covariates
  (`elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`) for risk adjustment.
- `greenwood_dbw_catalog.vch_cerner.condition_spec` — clinical-condition registry; the `sepsis`
  row (`cond_key = 'sepsis'`, `dx_primary = 'A41.9'`) documents the ICD-10 anchor, supplementary
  codes, and calibrated severity probabilities (`severe_p`, `icu_p`, `mort_p`).
- Identifier tables (`person`, `prsnl`, `clinical_note`, `clinical_note_flags`) are never
  referenced by this skill.
