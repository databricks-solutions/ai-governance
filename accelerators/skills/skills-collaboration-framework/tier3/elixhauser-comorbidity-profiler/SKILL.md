---
name: elixhauser-comorbidity-profiler
description: Profile the 31 AHRQ Elixhauser comorbidity flags and van Walraven weighted index
  for any VCH Cerner encounter cohort — the standard risk-adjustment covariate layer for outcome
  and readmission analyses.
---

# elixhauser-comorbidity-profiler

## Overview

A Tier-3 clinical risk-adjustment skill: it exposes the pre-computed AHRQ Elixhauser comorbidity
profile for VCH Cerner encounters and aggregated cohort summaries. It reads three objects in
`greenwood_dbw_catalog.vch_cerner`:

- **`elixhauser_encounter`** — one row per encounter with 31 INT comorbidity flags, a van Walraven
  composite score (`elixhauser_van_walraven_score`), and a raw flag count
  (`elixhauser_comorbidity_count`). This is the encounter-level covariate table.
- **`population_elixhauser_summary`** — pre-aggregated comorbidity statistics by population key,
  including mean and median van Walraven score, burden count, mortality rate, readmission rate,
  ICU rate, average LOS, and average cost. Use this for cross-cohort comparisons without touching
  encounter-level data.
- **`elixhauser_icd10_map`** — the AHRQ mapping from comorbidity category key to ICD-10-CM
  prefixes. Use this to explain which diagnosis codes underpin each flag and to audit the
  classification logic.

**Methodology note.** The 31 flags conform to the AHRQ Elixhauser Comorbidity Software Refined
for ICD-10-CM (v2024.1). The van Walraven composite score applies the integer weights from van
Walraven et al. (Med Care 2009; 47(6):626-633) to each flag; a higher score indicates greater
comorbidity burden and is used as a covariate in GLMM risk-adjusted mortality models. This skill
reads flags that are already computed — it does not recompute them from raw ICD-10 diagnosis rows.

## When to use this skill

Reach for this skill when you need comorbidity burden as a covariate or when comparing cohort
risk profiles:

- "What is the average van Walraven score for the heart-failure cohort?"
- "How does comorbidity burden differ between sepsis and stroke patients?"
- "Show me the distribution of Elixhauser flags for the 30-day readmission cohort."
- "Which comorbidities are most prevalent in patients with ICU use?"
- "What ICD-10 codes map to the `renal` Elixhauser flag?"
- "Compare comorbidity burden and readmission rates across all registered populations."
- "Profile the top comorbidities for high-utilizer encounters."

This skill is typically invoked before or alongside outcome-analysis skills so that comorbidity
burden can be included as a risk-adjustment covariate.

## Instructions

When the user asks a comorbidity-profiling question:

1. **Identify the scope** — is the user asking about encounter-level flags (individual cohort),
   aggregate population statistics, or the ICD-10 classification mapping?
2. **Route to the right table:**
   - Encounter-level comorbidity → query `elixhauser_encounter`, optionally joined to a cohort
     filter via `encntr_id` or `person_id`.
   - Cross-cohort summary statistics → query `population_elixhauser_summary` by `population_key`.
   - Flag-to-ICD-10 mapping → query `elixhauser_icd10_map` by `comorbidity_key`.
3. **Return the van Walraven score** alongside raw flag counts whenever burden quantification is
   requested; both are available on `elixhauser_encounter`.
4. **Aggregate correctly** — use `AVG`, `MEDIAN`, `PERCENTILE_CONT`, or `SUM` over
   `elixhauser_van_walraven_score` and individual flags depending on whether the user wants
   a distribution or a prevalence rate.
5. **Hand off** — once the comorbidity profile is established, name the downstream skill
   (e.g. the GLMM risk-adjusted mortality skill) that consumes van Walraven score as a covariate.

## Examples

### Encounter-level comorbidity flags for a cohort

```sql
SELECT
  e.encntr_id,
  e.person_id,
  e.elixhauser_van_walraven_score,
  e.elixhauser_comorbidity_count,
  e.chf,
  e.renal,
  e.dm_uncomp,
  e.dm_comp,
  e.chronic_pulm,
  e.depression,
  e.solid_tumor,
  e.mets
FROM greenwood_dbw_catalog.vch_cerner.elixhauser_encounter AS e
INNER JOIN greenwood_dbw_catalog.vch_cerner.pop_readmit_30d_tbl AS c
  ON e.encntr_id = c.encntr_id
ORDER BY e.elixhauser_van_walraven_score DESC
LIMIT 1000
```

### Distribution of van Walraven score within a cohort

```sql
SELECT
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY elixhauser_van_walraven_score) AS p25_vw,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY elixhauser_van_walraven_score) AS median_vw,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY elixhauser_van_walraven_score) AS p75_vw,
  AVG(elixhauser_van_walraven_score)                                            AS mean_vw,
  MAX(elixhauser_van_walraven_score)                                            AS max_vw,
  AVG(elixhauser_comorbidity_count)                                             AS avg_flag_count
FROM greenwood_dbw_catalog.vch_cerner.elixhauser_encounter
```

### Prevalence of all 31 flags across a cohort

```sql
SELECT
  COUNT(*)                                     AS n_encounters,
  ROUND(AVG(chf)          * 100, 1)            AS pct_chf,
  ROUND(AVG(arrhythmia)   * 100, 1)            AS pct_arrhythmia,
  ROUND(AVG(valvular)     * 100, 1)            AS pct_valvular,
  ROUND(AVG(pulm_circ)    * 100, 1)            AS pct_pulm_circ,
  ROUND(AVG(pvd)          * 100, 1)            AS pct_pvd,
  ROUND(AVG(htn_uncomp)   * 100, 1)            AS pct_htn_uncomp,
  ROUND(AVG(htn_comp)     * 100, 1)            AS pct_htn_comp,
  ROUND(AVG(paralysis)    * 100, 1)            AS pct_paralysis,
  ROUND(AVG(neuro_other)  * 100, 1)            AS pct_neuro_other,
  ROUND(AVG(chronic_pulm) * 100, 1)            AS pct_chronic_pulm,
  ROUND(AVG(dm_uncomp)    * 100, 1)            AS pct_dm_uncomp,
  ROUND(AVG(dm_comp)      * 100, 1)            AS pct_dm_comp,
  ROUND(AVG(hypothyroid)  * 100, 1)            AS pct_hypothyroid,
  ROUND(AVG(renal)        * 100, 1)            AS pct_renal,
  ROUND(AVG(liver)        * 100, 1)            AS pct_liver,
  ROUND(AVG(pud)          * 100, 1)            AS pct_pud,
  ROUND(AVG(hiv)          * 100, 1)            AS pct_hiv,
  ROUND(AVG(lymphoma)     * 100, 1)            AS pct_lymphoma,
  ROUND(AVG(mets)         * 100, 1)            AS pct_mets,
  ROUND(AVG(solid_tumor)  * 100, 1)            AS pct_solid_tumor,
  ROUND(AVG(rheum)        * 100, 1)            AS pct_rheum,
  ROUND(AVG(coagulopathy) * 100, 1)            AS pct_coagulopathy,
  ROUND(AVG(obesity)      * 100, 1)            AS pct_obesity,
  ROUND(AVG(weight_loss)  * 100, 1)            AS pct_weight_loss,
  ROUND(AVG(fluid_lyte)   * 100, 1)            AS pct_fluid_lyte,
  ROUND(AVG(blood_loss_anemia)    * 100, 1)    AS pct_blood_loss_anemia,
  ROUND(AVG(deficiency_anemia)    * 100, 1)    AS pct_deficiency_anemia,
  ROUND(AVG(alcohol)      * 100, 1)            AS pct_alcohol,
  ROUND(AVG(drug_abuse)   * 100, 1)            AS pct_drug_abuse,
  ROUND(AVG(psychoses)    * 100, 1)            AS pct_psychoses,
  ROUND(AVG(depression)   * 100, 1)            AS pct_depression
FROM greenwood_dbw_catalog.vch_cerner.elixhauser_encounter
```

### Cross-cohort summary comparison from population_elixhauser_summary

```sql
SELECT
  population_key,
  population_label,
  n_encounters,
  n_patients,
  avg_vw_score,
  median_vw_score,
  max_vw_score,
  avg_comorbidity_count,
  mortality_rate,
  readmit_30d_rate,
  icu_rate,
  avg_los,
  avg_cost
FROM greenwood_dbw_catalog.vch_cerner.population_elixhauser_summary
ORDER BY avg_vw_score DESC
```

### Look up ICD-10 prefixes that map to a specific Elixhauser category

```sql
SELECT
  comorbidity_key,
  icd10_prefix
FROM greenwood_dbw_catalog.vch_cerner.elixhauser_icd10_map
WHERE comorbidity_key = 'renal'
ORDER BY icd10_prefix
```

### All ICD-10 prefixes driving the renal and diabetes flags

```sql
SELECT
  comorbidity_key,
  icd10_prefix
FROM greenwood_dbw_catalog.vch_cerner.elixhauser_icd10_map
WHERE comorbidity_key IN ('renal', 'dm_uncomp', 'dm_comp')
ORDER BY comorbidity_key, icd10_prefix
```

## Recommendations framework

After profiling comorbidity burden, always include:

1. **Van Walraven summary** — report mean, median, and IQR of `elixhauser_van_walraven_score`
   for the cohort; this is the key scalar for downstream risk adjustment.
2. **Top-burden flags** — list the three to five most prevalent flags (by `AVG(flag) * 100`) so
   the user understands which conditions dominate the cohort's risk profile.
3. **Cohort comparison** — if the user has a comparison population, reference
   `population_elixhauser_summary` to surface pre-computed mean scores without needing a join.
4. **Risk-model hand-off** — if the user is building an outcome model, name the GLMM skill that
   consumes `elixhauser_van_walraven_score` as a covariate alongside age and ICU use.

## Edge cases

- **Flag interpretation** — each flag is an INT (0 or 1). A value of 1 means the AHRQ algorithm
  found at least one qualifying ICD-10-CM code on the encounter; 0 means none was found. The
  flags reflect secondary diagnoses coded at discharge — they do not confirm clinical severity.
- **Van Walraven score range** — the composite ranges from -19 to +89 in the original weighting
  table. A negative score is valid and expected for low-comorbidity encounters. Do not treat
  negative scores as data quality errors.
- **Pre-computed vs raw ICD-10** — this skill reads flags already computed by the AHRQ algorithm
  pipeline. Do not recompute flags from `diagnosis` or other raw ICD-10 tables; use
  `elixhauser_icd10_map` only to explain or audit which codes feed a given flag.
- **Cohort scope** — `elixhauser_encounter` covers all encounters in scope, not just inpatient.
  Filter on `encntr_type_cd` or join to a population cohort table (e.g. `pop_adult_inpatient_tbl`)
  to restrict to the intended population.
- **population_elixhauser_summary granularity** — rows are keyed on `population_key` only; there
  is no facility or time-period dimension. For facility-stratified or trended comorbidity burden,
  aggregate from `elixhauser_encounter` directly.
- **Missing encounters** — if an encounter has no discharge diagnoses it will be absent from
  `elixhauser_encounter`; a left-join from the cohort table will expose the gap.

## Data scope

- `greenwood_dbw_catalog.vch_cerner.elixhauser_encounter` — encounter-level AHRQ Elixhauser
  comorbidity flags (31 INT columns), van Walraven composite score, and flag count. Contains
  `encntr_id` and `person_id` but no free-text clinical content.
- `greenwood_dbw_catalog.vch_cerner.population_elixhauser_summary` — pre-aggregated comorbidity
  statistics per registered population key: encounter and patient counts, mean/median/max van
  Walraven score, average flag count, and outcome rates (mortality, readmission, ICU, LOS, cost).
  No individual encounter identifiers.
- `greenwood_dbw_catalog.vch_cerner.elixhauser_icd10_map` — reference mapping from AHRQ
  comorbidity category key to ICD-10-CM prefix strings. Classification metadata only; no
  patient data.
- Identifier tables (`person`, `prsnl`, `clinical_note`) are never referenced by this skill.
