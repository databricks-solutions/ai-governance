---
name: risk-adjusted-outcome-analyzer
description: Analyze cross-cohort risk-adjusted mortality (RAMR) and observed-vs-expected (O/E)
  ratios using the Greenwood EHR GLMM machinery — facility random effects, van Walraven adjustment,
  and the governed glmm_predictions table and mv_facility_ramr metric view.
---

# risk-adjusted-outcome-analyzer

## Overview

A Tier-3 clinical analytical skill: it surfaces risk-adjusted mortality rates (RAMR) and
observed-vs-expected (O/E) ratios across any registered inpatient cohort using the Greenwood EHR
GLMM (generalized linear mixed model) infrastructure. It reads two primary objects in
`greenwood_dbw_catalog.greenwood_ehr`:

- **`glmm_predictions`** — the per-encounter GLMM prediction table. Each row represents one
  inpatient encounter, joining the observed mortality outcome with the model-predicted
  probability, facility random intercept, and risk-adjustment covariates. Live-verified columns:
  `encntr_id`, `facility`, `observed`, `predicted_prob`, `linear_pred`,
  `facility_random_intercept`, `vw_score`, `age_years`, `icu_use`. The
  `facility_random_intercept` column is the GLMM-estimated facility-level random effect —
  positive values indicate a facility-level excess mortality risk not explained by patient
  case-mix; negative values indicate protective effects. This table does not carry a date
  column or a population/cohort identifier — use the `predict_glmm_cohort` TVF for
  time-bounded or cohort-scoped queries.

- **`mv_facility_ramr`** — the governed RAMR metric view. Provides pre-aggregated
  facility-level risk-adjusted mortality statistics dimensioned by `Facility`, `Condition`,
  and `Comorbidity Band`. Dimension columns (no `MEASURE()` needed): `Facility`, `Condition`,
  `Comorbidity Band`. Measure columns (require `MEASURE()` wrapping): `Encounters`,
  `Observed Deaths`, `Expected Deaths`, `Observed Rate`, `OE Ratio`,
  `Risk-Adjusted Mortality Rate`, `Avg van Walraven Score`. Query this view for facility
  benchmarking and RAMR comparisons without aggregating the raw prediction table.

Two table-valued functions (TVFs) are also available for dynamic cohort scoping:

- **`predict_glmm_cohort(population_csv STRING, lookback_years INT)`** — accepts a
  **single** registered condition key and a lookback window (in years); to analyze multiple
  cohorts, UNION ALL across separate calls — a comma-separated multi-key string returns zero
  rows (see Edge cases). Live-verified return columns: `encntr_id`, `person_id`, `cond_key`,
  `facility`, `observed`, `predicted_prob`, `linear_pred`, `vw_score`, `age_years`, `icu_use`.
  Call as `SELECT ... FROM greenwood_dbw_catalog.greenwood_ehr.predict_glmm_cohort('sepsis', 2)`.
- **`facility_ramr_lookback(lookback_years INT)`** — returns facility-level RAMR summary
  for the lookback window. Live-verified return columns: `facility`, `n_encounters`,
  `observed_deaths`, `expected_deaths`, `observed_rate`, `expected_rate`, `oe_ratio`,
  `risk_adjusted_mortality_rate`, `overall_crude_rate`, `avg_vw_score`.

**Clinical framing — risk-adjusted mortality rate (RAMR) and O/E ratios.**

The RAMR methodology answers: "Given this facility's patient mix, how many deaths would the
national model predict — and did the facility perform better or worse?" It separates true
quality variation from case-mix confounding.

The model uses a **generalized linear mixed model (GLMM)** with a logit link for
in-hospital mortality. Fixed effects include patient-level risk factors (van Walraven
weighted Elixhauser composite `vw_score`, `age_years`, and `icu_use`). A facility-level
**random intercept** (`facility_random_intercept`) absorbs unobserved systematic differences
across facilities (staffing, protocols, patient flow), preventing them from inflating apparent
patient-level risk. The van Walraven score is the AHRQ-validated 31-category Elixhauser
comorbidity composite (van Walraven et al., Med Care 2009) — a single continuous risk weight
pre-computed in `glmm_predictions.vw_score`.

**Interpreting O/E ratios:**

- **O/E ratio = 1.0** — facility observed the number of deaths the model predicted;
  performance aligns with expectations given the cohort's comorbidity burden.
- **O/E ratio > 1.0** — facility had more deaths than expected; may signal quality concerns,
  coding under-capture, or case-mix factors the model did not fully adjust for.
- **O/E ratio < 1.0** — facility had fewer deaths than expected; suggests better-than-expected
  performance on the risk-adjusted scale.

RAMR is derived from the O/E ratio: `RAMR = (Observed Deaths / Expected Deaths) × Overall
Crude Rate`. It expresses the facility's risk-adjusted mortality on the same scale as the
overall crude rate, enabling direct comparison across facilities.

**Cross-cohort generalization.** The GLMM infrastructure is cohort-agnostic. The
`predict_glmm_cohort(population_csv, lookback_years)` TVF accepts any registered population
key (e.g., `'sepsis'`, `'stroke_mi'`, `'adult_inpatient'`), and the TVF's `cond_key` return
column identifies the condition per row. To compare multiple cohorts in one result set, use
UNION ALL across separate TVF calls (see Example 3). RAMR analysis therefore applies equally
to sepsis, stroke/MI, readmission, ICU, heart failure, or the full adult inpatient population
— with no per-cohort model changes.

## When to use this skill

Reach for this skill when a question involves risk-adjusted mortality benchmarking, O/E
analysis, or GLMM-based quality reporting:

- "Which facilities have the highest O/E mortality ratios this year?"
- "What is the risk-adjusted mortality rate for each facility, adjusted for comorbidity burden?"
- "Show me RAMR and expected deaths by facility from the metric view."
- "Which encounters had predicted mortality above 20% but survived — high-risk survivors?"
- "How does van Walraven score distribution vary across facilities in the GLMM predictions?"
- "Compare observed vs expected deaths for the sepsis cohort across the past two years."
- "Show me the facility random intercept to identify systematic facility-level mortality risk."
- "Run the GLMM prediction function for the sepsis cohort over the past two years."

## Instructions

When the user asks a risk-adjusted mortality or O/E analysis question:

1. **Identify the analysis type** — facility RAMR benchmark, O/E outlier detection,
   encounter-level risk profiling, cross-cohort comparison, calibration check,
   high-risk survivor analysis, or facility random intercept inspection.
2. **Choose the right source:**
   - Facility-level RAMR benchmarks and pre-aggregated O/E statistics → query
     `mv_facility_ramr` with `MEASURE()` wrapping for all measure columns.
   - Encounter-level O/E analysis, outlier detection, calibration, or facility intercept
     inspection → query `glmm_predictions` directly.
   - Cohort-scoped or time-bounded queries → use the TVF
     `predict_glmm_cohort(population_csv, lookback_years)`.
   - Facility-level RAMR for a custom lookback period → use the TVF
     `facility_ramr_lookback(lookback_years)`.
3. **Wrap mv_facility_ramr measures in MEASURE()** — all columns except `Facility`,
   `Condition`, and `Comorbidity Band` are measure columns and require `MEASURE()`. Queries
   omitting `MEASURE()` will fail with `METRIC_VIEW_MISSING_MEASURE_FUNCTION`.
4. **Use predict_glmm_cohort for cohort-scoped queries** — `glmm_predictions` has no
   population/cohort identifier column and no date column. For queries scoped to a specific
   condition (sepsis, stroke, etc.) or a lookback window, use the TVF. The TVF returns
   `cond_key` per row for condition-level aggregation.
5. **Interpret O/E with comorbidity context** — always report `vw_score` (mean or
   distribution) alongside O/E ratios. Facilities with higher average van Walraven scores
   carry heavier comorbidity burden; the GLMM adjusts for this via the fixed effects, but
   reporting the covariate confirms to reviewers that case-mix is accounted for.
6. **Distinguish RAMR from crude mortality rate** — crude rate (observed deaths / encounters)
   ignores case-mix; RAMR corrects for it. Always label which metric you are reporting and
   why they may diverge for a given facility.
7. **Flag O/E outliers for follow-up** — O/E ratios deviating more than ±20% from 1.0 warrant
   clinical review (coding audit, protocol review, or cross-facility case comparison) before
   asserting a quality signal. The GLMM is a statistical screening tool, not a causal
   determination.

## Examples

### Facility RAMR benchmark from the metric view

Uses `mv_facility_ramr` with `MEASURE()` syntax. Returns risk-adjusted mortality rate,
observed rate, O/E ratio, expected deaths, and average van Walraven score pre-aggregated
by facility and condition.

```sql
SELECT
  `Facility`,
  `Condition`,
  MEASURE(`Encounters`)                          AS encounters,
  MEASURE(`Observed Deaths`)                     AS observed_deaths,
  MEASURE(`Expected Deaths`)                     AS expected_deaths,
  MEASURE(`Observed Rate`)                       AS observed_rate,
  MEASURE(`OE Ratio`)                            AS oe_ratio,
  MEASURE(`Risk-Adjusted Mortality Rate`)        AS ramr,
  MEASURE(`Avg van Walraven Score`)              AS avg_vw_score
FROM greenwood_dbw_catalog.greenwood_ehr.mv_facility_ramr
GROUP BY `Facility`, `Condition`
ORDER BY oe_ratio DESC
```

### O/E ratio by facility from glmm_predictions — all encounters in the table

Aggregates observed deaths, sum of predicted probabilities (= expected deaths), and O/E ratio
directly from `glmm_predictions`. Uses only confirmed live columns: `facility`, `observed`,
`predicted_prob`, `vw_score`.

```sql
SELECT
  facility,
  COUNT(*)                                                          AS n_encounters,
  SUM(observed)                                                     AS observed_deaths,
  ROUND(SUM(predicted_prob), 2)                                     AS expected_deaths,
  ROUND(SUM(observed) / NULLIF(SUM(predicted_prob), 0), 3)          AS oe_ratio,
  ROUND(AVG(vw_score), 2)                                           AS avg_vw_score,
  ROUND(100.0 * SUM(observed) / NULLIF(COUNT(*), 0), 2)             AS crude_mortality_rate_pct
FROM greenwood_dbw_catalog.greenwood_ehr.glmm_predictions
GROUP BY facility
ORDER BY oe_ratio DESC
```

### Cross-cohort O/E by condition using the predict_glmm_cohort TVF

Uses UNION ALL across two TVF calls to compare sepsis and stroke/MI O/E ratios in one result
set. The TVF is invoked once per cohort; `cond_key` per row enables condition-level grouping.

```sql
SELECT
  cond_key,
  facility,
  COUNT(*)                                                          AS n_encounters,
  SUM(observed)                                                     AS observed_deaths,
  ROUND(SUM(predicted_prob), 2)                                     AS expected_deaths,
  ROUND(SUM(observed) / NULLIF(SUM(predicted_prob), 0), 3)          AS oe_ratio,
  ROUND(AVG(vw_score), 2)                                           AS avg_vw_score,
  ROUND(AVG(age_years), 1)                                          AS avg_age,
  ROUND(AVG(CAST(icu_use AS DOUBLE)), 3)                            AS icu_rate
FROM (
  SELECT * FROM greenwood_dbw_catalog.greenwood_ehr.predict_glmm_cohort('sepsis', 2)
  UNION ALL
  SELECT * FROM greenwood_dbw_catalog.greenwood_ehr.predict_glmm_cohort('stroke_mi', 2)
)
WHERE cond_key IN ('sepsis', 'stroke', 'ami')
GROUP BY cond_key, facility
ORDER BY cond_key, oe_ratio DESC
```

### High-risk survivors — predicted probability above 20%, observed = 0

Identifies encounters where the GLMM assigned high mortality risk but the patient survived.
Useful for auditing model calibration and understanding rescue cases. Includes
`facility_random_intercept` to show the facility-level component of each encounter's risk.

```sql
SELECT
  encntr_id,
  facility,
  ROUND(predicted_prob, 4)                                          AS predicted_prob,
  ROUND(linear_pred, 4)                                             AS linear_pred,
  ROUND(facility_random_intercept, 6)                               AS facility_random_intercept,
  vw_score,
  age_years,
  icu_use
FROM greenwood_dbw_catalog.greenwood_ehr.glmm_predictions
WHERE predicted_prob >= 0.20
  AND observed = 0
ORDER BY predicted_prob DESC
LIMIT 200
```

### Dynamic cohort RAMR using the predict_glmm_cohort TVF

Invokes the TVF for the sepsis population over a 2-year lookback and computes O/E ratios.

```sql
SELECT
  facility,
  cond_key,
  COUNT(*)                                                          AS n_encounters,
  SUM(observed)                                                     AS observed_deaths,
  ROUND(SUM(predicted_prob), 2)                                     AS expected_deaths,
  ROUND(SUM(observed) / NULLIF(SUM(predicted_prob), 0), 3)          AS oe_ratio,
  ROUND(AVG(vw_score), 2)                                           AS avg_vw_score
FROM greenwood_dbw_catalog.greenwood_ehr.predict_glmm_cohort('sepsis', 2)
GROUP BY facility, cond_key
ORDER BY oe_ratio DESC
```

### Facility RAMR lookback using the facility_ramr_lookback TVF

```sql
SELECT
  facility,
  n_encounters,
  observed_deaths,
  ROUND(expected_deaths, 2)                                         AS expected_deaths,
  ROUND(observed_rate, 4)                                           AS observed_rate,
  ROUND(expected_rate, 4)                                           AS expected_rate,
  ROUND(oe_ratio, 3)                                                AS oe_ratio,
  ROUND(risk_adjusted_mortality_rate, 4)                            AS ramr,
  ROUND(overall_crude_rate, 4)                                      AS overall_crude_rate,
  ROUND(avg_vw_score, 2)                                            AS avg_vw_score
FROM greenwood_dbw_catalog.greenwood_ehr.facility_ramr_lookback(2)
ORDER BY oe_ratio DESC
```

## Recommendations framework

After surfacing RAMR or O/E results, always include:

1. **RAMR vs crude rate disclosure** — report both metrics side by side. Facilities serving
   higher-acuity or more comorbid populations typically show crude rates exceeding RAMR; the
   gap is evidence that risk adjustment is doing meaningful work. Flag cases where RAMR and
   crude rate diverge substantially.
2. **O/E ratio interpretation** — label O/E > 1.0 as "worse than expected" and O/E < 1.0 as
   "better than expected," and always attach the absolute counts (observed vs expected deaths)
   so readers understand the scale. An O/E of 1.5 on 2 expected deaths is very different from
   1.5 on 200 expected deaths.
3. **Van Walraven context** — include `avg_vw_score` for each facility. Consistently higher
   scores at one site confirm a heavier comorbidity burden and reassure reviewers that the
   model's expected-deaths estimate is case-mix-adjusted; consistently low scores at a
   high-O/E site strengthen the quality-concern hypothesis.
4. **Outlier follow-up protocol** — for any facility with O/E > 1.2 or O/E < 0.8, recommend
   a clinical coding audit (are deaths coded consistently?) before asserting a performance
   signal. The GLMM is a statistical screen; root cause requires case review.
5. **Facility random intercept** — `facility_random_intercept` in `glmm_predictions` is the
   GLMM-estimated facility-level effect after controlling for patient case-mix. Positive values
   indicate residual facility-level excess mortality risk. Include it in facility deep-dive
   analyses to show the structural (not case-mix-driven) component of each facility's mortality
   profile.
6. **Random intercept caveat** — the facility random intercept absorbs facility-level
   unobserved heterogeneity. It means that a facility's O/E ratio reflects residual variation
   after adjusting for age, comorbidity, and ICU use, not total unadjusted mortality difference.
   Describe this to clinical stakeholders to avoid over-interpretation.
7. **Calibration check** — for any cohort where the model is new or recently retrained, plot
   or tabulate predicted_prob deciles vs observed mortality rates (Hosmer-Lemeshow style) using
   `glmm_predictions` before presenting RAMR as final. A well-calibrated model will show
   close alignment between predicted and observed rates across risk bands.

## Edge cases

- **mv_facility_ramr MEASURE() requirement** — all columns other than `Facility`, `Condition`,
  and `Comorbidity Band` are measure columns and must be wrapped in `MEASURE()`. Omitting
  wrapping raises `METRIC_VIEW_MISSING_MEASURE_FUNCTION`. The exact measure column names
  (live-verified): `Encounters`, `Observed Deaths`, `Expected Deaths`, `Observed Rate`,
  `OE Ratio`, `Risk-Adjusted Mortality Rate`, `Avg van Walraven Score`.
- **glmm_predictions column set (live-verified)** — only the following columns exist:
  `encntr_id`, `facility`, `observed`, `predicted_prob`, `linear_pred`,
  `facility_random_intercept`, `vw_score`, `age_years`, `icu_use`. There is NO `population_key`
  column, NO `loc_facility_cd` (use `facility`), NO `cond_key` (use the TVF for
  condition-level analysis), NO `inpatient_mortality` (use `observed`), NO `admit_dt_tm`
  or `admit_month`. For time-bounded or cohort-scoped queries, use `predict_glmm_cohort`.
- **predict_glmm_cohort vs glmm_predictions columns** — the TVF returns `person_id` and
  `cond_key` in addition to the core prediction columns, and does NOT return
  `facility_random_intercept`. Do not attempt to mix columns from the two sources in a single
  query without a join on `encntr_id`.
- **Expected deaths = sum of predicted_prob** — the GLMM predicts P(death) per encounter.
  Sum of predicted probabilities across encounters is the statistically expected number of
  deaths. Compute O/E as `SUM(observed) / SUM(predicted_prob)`, not as a ratio of rates.
  Dividing observed rate by expected rate introduces a denominator inconsistency when
  encounter counts differ across facilities.
- **O/E ratio instability for small facilities** — facilities with fewer than ~30 encounters
  in the analysis window produce O/E ratios with wide confidence intervals. Flag small-N
  facilities explicitly and avoid ranking them alongside high-volume sites.
- **RAMR formula** — `RAMR = (Observed / Expected) × Overall Crude Rate`. The overall crude
  rate denominator is available in `facility_ramr_lookback` as `overall_crude_rate`. When
  computing RAMR manually from `glmm_predictions`, note that the overall crude rate must be
  computed across the same population scope as the model was trained on; using a facility
  subset as the denominator produces a biased RAMR.
- **Facility random intercept interpretation** — `linear_pred` on `glmm_predictions` equals
  the sum of the fixed-effect linear predictor plus `facility_random_intercept`. A
  consistently negative `facility_random_intercept` at a facility (controlling for `vw_score`
  and `age_years`) indicates a protective structural facility effect; consistently positive
  indicates residual excess risk. Do not conflate the random intercept with the O/E ratio —
  they capture related but distinct aspects of facility performance.
- **predict_glmm_cohort population_csv format** — pass a single registered condition key per
  call, e.g., `'sepsis'`, `'stroke_mi'`, or `'adult_inpatient'`. To combine multiple cohorts,
  use UNION ALL across separate TVF invocations (live-verified: comma-separated multi-key
  strings return zero rows). Unregistered keys return zero rows without an error; always
  confirm row counts before interpreting empty results as evidence of no mortality.

## Data scope

- `greenwood_dbw_catalog.greenwood_ehr.glmm_predictions` — per-encounter GLMM prediction table
  (live-verified columns): `encntr_id`, `facility`, `observed`, `predicted_prob`,
  `linear_pred`, `facility_random_intercept`, `vw_score`, `age_years`, `icu_use`. Covers
  all encounters with GLMM predictions. No date column, no cohort identifier column — use
  `predict_glmm_cohort` TVF for time-bounded or cohort-scoped queries.
- `greenwood_dbw_catalog.greenwood_ehr.mv_facility_ramr` — governed RAMR metric view (columns
  live-verified). Dimension columns (no `MEASURE()` needed): `Facility`, `Condition`,
  `Comorbidity Band`. Measure columns (require `MEASURE()`): `Encounters`, `Observed Deaths`,
  `Expected Deaths`, `Observed Rate`, `OE Ratio`, `Risk-Adjusted Mortality Rate`,
  `Avg van Walraven Score`. Use for facility benchmarking and pre-aggregated RAMR comparison.
- `greenwood_dbw_catalog.greenwood_ehr.predict_glmm_cohort(population_csv, lookback_years)` —
  TVF (live-verified) returning encounter-level GLMM predictions for specified cohort(s) and
  lookback window. Return columns: `encntr_id`, `person_id`, `cond_key`, `facility`,
  `observed`, `predicted_prob`, `linear_pred`, `vw_score`, `age_years`, `icu_use`.
- `greenwood_dbw_catalog.greenwood_ehr.facility_ramr_lookback(lookback_years)` — TVF
  (live-verified) returning facility-level RAMR summary: `facility`, `n_encounters`,
  `observed_deaths`, `expected_deaths`, `observed_rate`, `expected_rate`, `oe_ratio`,
  `risk_adjusted_mortality_rate`, `overall_crude_rate`, `avg_vw_score`.
- `greenwood_dbw_catalog.greenwood_ehr.population_endpoint_features` — optional supplementary
  source for encounter-level outcome columns not in `glmm_predictions` (e.g., `admit_month`,
  `loc_facility_cd`, `inpatient_mortality`, complication flags). Join on `encntr_id` when
  clinical context beyond the GLMM columns is needed.
- Identifier tables (`person`, `prsnl`, `clinical_note`, `clinical_note_flags`) are never
  referenced by this skill.
