---
name: cost-optimizer
description: Recommend Databricks cost-optimization actions for the FinOps/platform team — commitment/discount coverage, budget variance, and forecast-vs-actual DBU spend from system.billing.usage and system.billing.list_prices.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# cost-optimizer

## Overview

Turns Databricks billing data into finance-facing optimization actions: it measures
commitment/discount coverage, compares actual spend against budget, and forecasts
month-end DBU cost so the FinOps/platform team can act before overruns land. Distinct from
`pipeline-cost-analyzer` (which is engineering-facing job/SKU analysis) — this skill is
scoped to budget governance and dollarized recommendations.

## When to use this skill

When a finance user asks about budget adherence, discount coverage, or spend forecasting:

- "Are we on track against this month's Databricks budget?"
- "What share of our DBUs are covered by our committed-use discount?"
- "Project our month-end spend at the current run rate."
- "Where is spend running over budget by product?"

## Instructions

1. **Establish the budget baseline** — ask for the monthly budget if not supplied; otherwise
   compare against the trailing 3-month average as an implicit baseline.
2. **Dollarize usage** — join `system.billing.usage` to `system.billing.list_prices` to convert
   DBUs to cost; never present raw DBUs alone to a finance audience.
3. **Assess coverage and variance** — compute committed-discount coverage and budget variance.
4. **Forecast** — extrapolate month-to-date run rate to a month-end projection.
5. **Recommend** — give 2–3 dollar-quantified actions, ordered by savings impact.

## Examples

### Month-end spend forecast at current run rate

```sql
WITH mtd AS (
  SELECT
    SUM(u.usage_quantity * p.pricing.default) AS cost_to_date,
    DAY(CURRENT_DATE())                        AS days_elapsed,
    DAY(LAST_DAY(CURRENT_DATE()))              AS days_in_month
  FROM system.billing.usage u
  JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name
  WHERE u.usage_date >= DATE_TRUNC('month', CURRENT_DATE())
)
SELECT
  cost_to_date,
  ROUND(cost_to_date / days_elapsed * days_in_month, 2) AS projected_month_end
FROM mtd
```

### Spend by product vs. trailing average (budget-variance signal)

```sql
SELECT
  billing_origin_product,
  SUM(usage_quantity)                                            AS dbus_this_month
FROM system.billing.usage
WHERE usage_date >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY 1
ORDER BY dbus_this_month DESC
```

## Recommendations framework

Every response ends with dollar-quantified actions:

1. **Biggest variance** — the product/workspace most over baseline, with an estimated
   monthly-dollar impact and one corrective action.
2. **Coverage gap** — uncommitted spend that a committed-use discount would cover, with the
   estimated discount saving.
3. **Quick win** — one action realizable this billing cycle (e.g. move a recurring batch job
   off all-purpose compute).

## Edge cases

- **Missing budget** — if no budget is provided, state the baseline you used (trailing
  3-month average) so the variance is interpretable.
- **Early in the month** — a run-rate forecast on <5 elapsed days is noisy; flag the low
  confidence rather than presenting a point estimate as firm.
- **Price coverage** — if a `sku_name` has no row in `list_prices`, report it as unpriced
  rather than silently dropping its usage from the cost total.

## Data scope

- `system.billing.usage` — DBU consumption events per workspace/SKU/job/cluster
- `system.billing.list_prices` — list prices per SKU (for dollarization)
- No PII or sensitive customer data is accessed.
