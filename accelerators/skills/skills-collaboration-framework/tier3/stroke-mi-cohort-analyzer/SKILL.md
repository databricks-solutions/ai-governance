---
name: stroke-mi-cohort-analyzer
description: Analyze ischemic stroke and acute MI cohort outcomes (30-day mortality, 30-day
  readmission, reperfusion therapy rates) from the Greenwood EHR semantic layer — reusing the
  governed pop_stroke_mi cohort asset and standard clinical endpoints.
---

# stroke-mi-cohort-analyzer

## Overview

A Tier-3 clinical outcome skill: it analyzes ischemic stroke and acute myocardial infarction
(AMI) encounter outcomes across the Greenwood EHR inpatient population using the governed semantic
layer. It reads three objects in `greenwood_dbw_catalog.greenwood_ehr`:

- **`pop_stroke_mi_tbl`** — the materialized stroke/MI cohort table, pre-filtered by the
  governed `pop_stroke_mi()` scalar predicate (`cond_key IN ('stroke','ami')`). This skill
  reuses the existing governed `pop_stroke_mi()` function and its materialized table rather than
  redefining the cohort predicate. Reuse over reinvention: every stroke and MI encounter added
  to the semantic layer is automatically in scope once `pop_stroke_mi_tbl` is refreshed.
  Confirmed columns available: `encntr_id`, `person_id`, `cond_key`, `encntr_type_cd`,
  `admit_dt_tm`, `age_years`, `sex_cd`, `race_cd`, `loc_facility_cd`, `icu_use`,
  `has_surgical_proc`, `readmit_30d`, `length_of_stay_days`, `total_cost`,
  `disch_disposition_cd`, `any_complication`, `elixhauser_van_walraven_score`,
  `elixhauser_comorbidity_count`. Note that `inpatient_mortality`, `admit_month`, and
  reperfusion/treatment flags (`tx_tpa`, `tx_thrombectomy`, `tx_pci`) are NOT on this table —
  use `population_endpoint_features` for those columns.
- **`population_endpoint_features`** — per-encounter feature and outcome table. Key columns for
  this cohort: `tx_tpa` (thrombolysis/tPA for stroke), `tx_thrombectomy` (mechanical
  thrombectomy for stroke), `tx_pci` (percutaneous coronary intervention for AMI),
  `inpatient_mortality`, `readmit_30d`, `icu_use`, `length_of_stay_days`, `admit_month`,
  `loc_facility_cd`, `cond_key`, and `encntr_id`. Use for outcome queries that need the full
  feature set, comorbidity covariates, or cross-condition comparisons.
- **`condition_spec`** — clinical-condition registry. The `stroke` row carries `cond_key =
  'stroke'`, `dx_primary = 'I63.9'` (cerebral infarction, unspecified); the `ami` row carries
  `cond_key = 'ami'`, `dx_primary = 'I21.9'` (acute MI, unspecified). Use to verify canonical
  ICD-10 anchors and read the calibrated probability fields (`severe_p`, `icu_p`, `mort_p`)
  that describe each condition's expected severity profile.

**Clinical framing — ischemic stroke and acute MI.** Ischemic stroke (ICD-10 I63.x) results
from thrombotic or embolic occlusion of a cerebral artery; reperfusion options are intravenous
thrombolysis (tPA, `tx_tpa = 1`) and mechanical thrombectomy (`tx_thrombectomy = 1`). Acute MI
(ICD-10 I21.x) results from coronary artery occlusion; the primary reperfusion therapy is
percutaneous coronary intervention (PCI, `tx_pci = 1`). The two conditions share the same
`pop_stroke_mi()` cohort predicate because they are both high-acuity vascular events with
well-defined reperfusion pathways and time-sensitive quality standards.

Key endpoints tracked by this skill:

- **30-day in-hospital mortality** (`inpatient_mortality`) — the primary survival outcome for
  both conditions.
- **30-day readmission** (`readmit_30d`) — a CMS HRRP-aligned outcome indicating post-discharge
  stability and care continuity.
- **Reperfusion therapy rates** — `tx_tpa` and `tx_thrombectomy` for stroke; `tx_pci` for AMI.
  These flags confirm that an order was placed; they do not carry minute-level timestamps.
  Door-to-needle time analysis (the time between ED arrival and tPA/thrombectomy initiation)
  would require joining to raw order and event timestamp tables, which are outside this skill's
  scope. Document this limitation when reporting on time-to-treatment quality standards.
- **ICU use** (`icu_use`) and **length of stay** (`length_of_stay_days`) as secondary burden
  indicators.

## When to use this skill

Reach for this skill when a question involves stroke or AMI outcomes, reperfusion therapy rates,
or quality metrics for either condition:

- "What is the 30-day mortality rate for ischemic stroke encounters by facility?"
- "How does readmission rate differ between stroke and MI patients?"
- "What proportion of stroke encounters received tPA or mechanical thrombectomy?"
- "Show me PCI rates for the AMI cohort stratified by facility."
- "How has ICU use for the stroke/MI cohort trended over the past 12 months?"
- "What is the average LOS for stroke encounters with and without reperfusion therapy?"
- "Read the condition spec for stroke and AMI to confirm their ICD-10 anchors."
- "Compare 30-day readmission rates between the stroke cohort and the AMI cohort."

## Instructions

When the user asks a stroke or MI analysis question:

1. **Identify the analysis type** — outcome rate (mortality, readmission, ICU, LOS), reperfusion
   therapy rate (tPA, thrombectomy, PCI), facility or temporal trend, or condition-spec lookup.
2. **Choose the right starting table:**
   - Cohort-scoped queries where the stroke/MI filter is already applied → join from or query
     `pop_stroke_mi_tbl` directly. This avoids re-applying the predicate and is the preferred
     path for cohort-level aggregations.
   - Queries that need to compare the stroke/MI cohort against a broader population, or that
     require comorbidity columns not on `pop_stroke_mi_tbl` → query
     `population_endpoint_features` with `cond_key IN ('stroke', 'ami')`.
3. **Split by condition** — always include `cond_key` in GROUP BY when the question compares
   stroke to AMI; the two conditions have different reperfusion pathways and distinct mortality
   profiles. Aggregating them without stratification obscures clinically relevant differences.
4. **Apply the condition spec** — when answering questions about the clinical definition, coding
   anchor, or expected severity distribution, query `condition_spec WHERE cond_key IN ('stroke',
   'ami')` to surface `dx_primary`, `sec_codes`, `severe_p`, `icu_p`, and `mort_p` for both
   conditions.
5. **Reperfusion therapy flags** — use `tx_tpa`, `tx_thrombectomy`, and `tx_pci` from
   `population_endpoint_features` as therapy-ordered flags. Always qualify that these confirm
   order placement only; minute-level door-to-needle or door-to-balloon time analysis requires
   joining to raw order records and event timestamps, which are not in scope here.
6. **30-day readmission framing** — `readmit_30d = 1` aligns with the CMS Hospital Readmissions
   Reduction Program (HRRP) definition: all-cause unplanned readmissions within 30 days of
   discharge. When reporting readmission rates for stroke or MI specifically, note that CMS
   HRRP also applies condition-specific risk adjustment; the `elixhauser_van_walraven_score`
   covariate from `population_endpoint_features` is the appropriate adjustment input.
7. **Stratify** by `loc_facility_cd` and `cond_key` to surface facility-level variation.
   For monthly bucketing on `pop_stroke_mi_tbl` use `DATE_TRUNC('month', admit_dt_tm)`;
   on `population_endpoint_features` use `DATE_TRUNC('month', admit_month)`. Facility
   variation in reperfusion rates is the primary signal for stroke and cardiac quality
   improvement teams.

## Examples

### Readmission, ICU, and LOS rates by condition and facility

```sql
SELECT
  cond_key,
  loc_facility_cd,
  COUNT(*)                                                                 AS n_encounters,
  SUM(readmit_30d)                                                         AS n_readmit_30d,
  ROUND(100.0 * SUM(readmit_30d) / NULLIF(COUNT(*), 0), 2)                AS readmit_30d_rate_pct,
  SUM(icu_use)                                                             AS n_icu,
  ROUND(100.0 * SUM(icu_use) / NULLIF(COUNT(*), 0), 2)                    AS icu_rate_pct,
  ROUND(AVG(length_of_stay_days), 1)                                      AS avg_los
FROM greenwood_dbw_catalog.greenwood_ehr.pop_stroke_mi_tbl
GROUP BY cond_key, loc_facility_cd
ORDER BY cond_key, readmit_30d_rate_pct DESC
```

### Reperfusion therapy rates from population_endpoint_features

```sql
SELECT
  cond_key,
  loc_facility_cd,
  COUNT(*)                                                                  AS n_encounters,
  SUM(tx_tpa)                                                               AS n_tpa,
  ROUND(100.0 * SUM(tx_tpa) / NULLIF(COUNT(*), 0), 2)                      AS tpa_rate_pct,
  SUM(tx_thrombectomy)                                                      AS n_thrombectomy,
  ROUND(100.0 * SUM(tx_thrombectomy) / NULLIF(COUNT(*), 0), 2)             AS thrombectomy_rate_pct,
  SUM(tx_pci)                                                               AS n_pci,
  ROUND(100.0 * SUM(tx_pci) / NULLIF(COUNT(*), 0), 2)                      AS pci_rate_pct,
  SUM(inpatient_mortality)                                                  AS n_deaths,
  ROUND(100.0 * SUM(inpatient_mortality) / NULLIF(COUNT(*), 0), 2)         AS mortality_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE cond_key IN ('stroke', 'ami')
GROUP BY cond_key, loc_facility_cd
ORDER BY cond_key, loc_facility_cd
```

### Monthly trend — ICU use and readmission for the stroke/MI cohort

```sql
SELECT
  cond_key,
  DATE_TRUNC('month', admit_dt_tm)                                         AS month,
  COUNT(*)                                                                 AS n_encounters,
  SUM(icu_use)                                                             AS n_icu,
  ROUND(100.0 * SUM(icu_use) / NULLIF(COUNT(*), 0), 2)                    AS icu_rate_pct,
  SUM(readmit_30d)                                                         AS n_readmit,
  ROUND(100.0 * SUM(readmit_30d) / NULLIF(COUNT(*), 0), 2)                AS readmit_rate_pct,
  ROUND(AVG(length_of_stay_days), 1)                                      AS avg_los
FROM greenwood_dbw_catalog.greenwood_ehr.pop_stroke_mi_tbl
GROUP BY cond_key, DATE_TRUNC('month', admit_dt_tm)
ORDER BY month DESC, cond_key
```

### Reperfusion therapy and outcomes for stroke encounters with ICU use

```sql
SELECT
  encntr_id,
  cond_key,
  tx_tpa,
  tx_thrombectomy,
  tx_pci,
  inpatient_mortality,
  readmit_30d,
  icu_use,
  length_of_stay_days,
  loc_facility_cd,
  admit_month
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE cond_key IN ('stroke', 'ami')
  AND icu_use = 1
ORDER BY admit_month DESC
LIMIT 1000
```

### LOS distribution by condition and reperfusion therapy

```sql
SELECT
  cond_key,
  CASE
    WHEN cond_key = 'stroke' AND (tx_tpa = 1 OR tx_thrombectomy = 1) THEN 'reperfused'
    WHEN cond_key = 'ami'    AND tx_pci = 1                           THEN 'reperfused'
    ELSE 'no-reperfusion'
  END                                                                      AS reperfusion_group,
  COUNT(*)                                                                 AS n_encounters,
  ROUND(AVG(length_of_stay_days), 1)                                      AS avg_los,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY length_of_stay_days)       AS median_los,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY length_of_stay_days)       AS p75_los,
  ROUND(100.0 * SUM(inpatient_mortality) / NULLIF(COUNT(*), 0), 2)        AS mortality_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features
WHERE cond_key IN ('stroke', 'ami')
GROUP BY cond_key, reperfusion_group
ORDER BY cond_key, reperfusion_group
```

### Read the stroke and AMI condition specs

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
FROM greenwood_dbw_catalog.greenwood_ehr.condition_spec
WHERE cond_key IN ('stroke', 'ami')
ORDER BY cond_key
```

## Recommendations framework

After analyzing stroke/MI outcomes, always include:

1. **Mortality and readmission summary** — report overall `inpatient_mortality` rate and
   `readmit_30d` rate for each condition separately (`cond_key`); mixing them without
   stratification obscures the distinct risk profiles of stroke vs. AMI populations.
2. **Reperfusion rate by facility** — report `tx_tpa` and `tx_thrombectomy` rates for the stroke
   cohort, and `tx_pci` rate for the AMI cohort, broken down by `loc_facility_cd`. Facility
   variation in reperfusion rates is the primary signal for stroke and cardiac quality teams.
3. **Door-to-needle / door-to-balloon caveat** — when the user asks about time-to-treatment,
   explicitly note that `tx_tpa`, `tx_thrombectomy`, and `tx_pci` are therapy-ordered flags
   without minute-level timestamps. Door-to-needle and door-to-balloon time analysis requires
   joining to raw order and event timestamp tables outside this skill's scope.
4. **30-day readmission framing** — qualify `readmit_30d` as an all-cause unplanned readmission
   flag; CMS HRRP applies condition-specific risk adjustment for stroke and AMI. Reference the
   `elixhauser-comorbidity-profiler` skill to obtain van Walraven scores as covariates before
   computing risk-adjusted readmission rates.
5. **Facility stratification** — always break down rates by `loc_facility_cd`; unexplained
   facility variation in mortality, readmission, or reperfusion rates is the primary signal for
   quality improvement programs such as Get With The Guidelines (stroke) and ACC/AHA GWTG-CAD
   (MI).
6. **Comorbidity hand-off** — for risk-adjusted analysis, refer to the
   `elixhauser-comorbidity-profiler` skill to obtain van Walraven scores as covariates before
   computing risk-adjusted mortality or readmission rates.

## Edge cases

- **pop_stroke_mi_tbl vs population_endpoint_features** — `pop_stroke_mi_tbl` is a narrower
  materialized snapshot: it carries cohort identifiers and burden columns (`icu_use`,
  `readmit_30d`, `length_of_stay_days`, `total_cost`, `any_complication`, Elixhauser scores)
  but does NOT have `inpatient_mortality`, `admit_month`, or reperfusion/treatment flags
  (`tx_tpa`, `tx_thrombectomy`, `tx_pci`). For any query that needs mortality, month-of-admit
  bucketing, or therapy flags, source from `population_endpoint_features WHERE cond_key IN
  ('stroke', 'ami')` instead. For time-trending on the cohort table, use
  `DATE_TRUNC('month', admit_dt_tm)` — the cohort table has `admit_dt_tm`, not `admit_month`.
  The cohort table may also lag behind `population_endpoint_features` if not recently refreshed.
- **Condition co-occurrence** — an encounter may carry both a stroke and an AMI code if a
  patient had simultaneous events. The `cond_key` column reflects the primary coded condition;
  using it in GROUP BY correctly partitions the two conditions and avoids double-counting.
- **ICD-10 coding breadth** — the `stroke` cond_key anchors on I63.9 (cerebral infarction,
  unspecified) and the `ami` cond_key on I21.9 (acute MI, unspecified). More specific subtypes
  (I63.0–I63.8 for typed cerebral infarctions; I21.0–I21.4 for STEMI/NSTEMI subtypes) may be
  coded as primary diagnoses without the generic unspecified code. The `sec_codes` array in
  `condition_spec` documents supplementary codes; verify coverage before concluding a case is
  not in cohort.
- **Reperfusion flags are order-based** — `tx_tpa`, `tx_thrombectomy`, and `tx_pci` confirm
  order placement only; confirmed-administered rates require the medication-administration table,
  which is not in scope here. Report these as ordering rates and qualify the limitation.
- **Door-to-needle timestamp precision** — `population_endpoint_features` does not carry
  order timestamps. Door-to-needle time (stroke) and door-to-balloon time (AMI) analysis
  requires a join to raw order records with the admission timestamp or ED-arrival timestamp.
  This is a scope note, not a data quality issue.
- **pop_stroke_mi_tbl refresh** — the cohort table is a static snapshot. Schedule periodic
  `CREATE OR REPLACE TABLE` refreshes to keep it current; staleness is the primary data quality
  risk for trending analyses.
- **CMS HRRP risk adjustment** — the `readmit_30d` flag is unadjusted. CMS HRRP applies
  condition-specific hierarchical logistic models with comorbidity, age, and discharge
  disposition as covariates. Unadjusted facility comparisons of readmission rates should be
  interpreted with caution; use van Walraven score from `population_endpoint_features` as a
  proxy adjustment variable.

## Data scope

- `greenwood_dbw_catalog.greenwood_ehr.pop_stroke_mi_tbl` — governed stroke/MI cohort table,
  materialized by the `pop_stroke_mi()` predicate (`cond_key IN ('stroke','ami')`). Confirmed
  columns: `encntr_id`, `person_id`, `cond_key`, `encntr_type_cd`, `admit_dt_tm`, `age_years`,
  `sex_cd`, `race_cd`, `loc_facility_cd`, `icu_use`, `has_surgical_proc`, `readmit_30d`,
  `length_of_stay_days`, `total_cost`, `disch_disposition_cd`, `any_complication`,
  `elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`. Use `admit_dt_tm` for
  monthly bucketing (`DATE_TRUNC('month', admit_dt_tm)`). Does NOT contain `inpatient_mortality`,
  `admit_month`, or reperfusion flags — use `population_endpoint_features` for those. This is
  the preferred join anchor for cohort-scoped queries on the columns it carries.
- `greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features` — per-encounter feature and
  outcome table; key stroke/MI columns: `tx_tpa`, `tx_thrombectomy`, `tx_pci`,
  `inpatient_mortality`, `readmit_30d`, `icu_use`, `length_of_stay_days`, `admit_month`,
  `loc_facility_cd`, `cond_key`, `encntr_id`. Also carries Elixhauser comorbidity covariates
  (`elixhauser_van_walraven_score`, `elixhauser_comorbidity_count`) for risk adjustment.
- `greenwood_dbw_catalog.greenwood_ehr.condition_spec` — clinical-condition registry; the `stroke`
  row (`cond_key = 'stroke'`, `dx_primary = 'I63.9'`) and the `ami` row (`cond_key = 'ami'`,
  `dx_primary = 'I21.9'`) document the ICD-10 anchors, supplementary codes, and calibrated
  severity probabilities (`severe_p`, `icu_p`, `mort_p`).
- Identifier tables (`person`, `prsnl`, `clinical_note`, `clinical_note_flags`) are never
  referenced by this skill.
