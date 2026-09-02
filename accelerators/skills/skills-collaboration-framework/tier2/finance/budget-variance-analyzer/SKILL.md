---
name: budget-variance-analyzer
description: Analyze Financial Applications budget-vs-actual variance by cost center and account from aggregate financial ledger tables. Ask me where spend is over or under budget, variance trends, or the biggest variance drivers.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# budget-variance-analyzer

## Overview

Turns Financial Applications ledger data into **budget-vs-actual variance** insight: it
compares actual spend against budget by cost center and account, ranks the largest variances,
and tracks variance trends over time. It reads aggregate, department-level financial rollups —
no individual transaction PII — keeping it a Tier-2 (internal) finance skill.

## When to use this skill

Reach for this skill when a finance user asks about budget adherence:

- "Which cost centers are over budget this quarter?"
- "What is our budget-vs-actual variance by account?"
- "Show me the biggest budget overruns year-to-date."
- "How has the IT cost center's variance trended over the last 6 months?"

## Instructions

When the user asks a budget or variance question:

1. **Identify the cost center(s), account(s), and period** (default: current fiscal quarter).
2. **Query `greenwood.finance.actuals`** for actual spend by cost center, account, and period.
3. **Join `greenwood.finance.budgets`** on the same keys to compute variance (actual − budget).
4. **Present results** as a ranked variance table, then give 2–3 variance observations
   (see the Recommendations framework).

## Examples

### Budget variance by cost center (current quarter)

```sql
SELECT
  a.cost_center,
  SUM(a.actual_amount)                       AS actual,
  SUM(b.budget_amount)                       AS budget,
  SUM(a.actual_amount) - SUM(b.budget_amount) AS variance
FROM greenwood.finance.actuals a
JOIN greenwood.finance.budgets b
  ON a.cost_center = b.cost_center
 AND a.account     = b.account
 AND a.fiscal_period = b.fiscal_period
WHERE a.fiscal_period = DATE_TRUNC('quarter', CURRENT_DATE())
GROUP BY a.cost_center
ORDER BY variance DESC
```

### Variance trend for a cost center (last 6 periods)

```sql
SELECT
  a.fiscal_period,
  SUM(a.actual_amount) - SUM(b.budget_amount) AS variance
FROM greenwood.finance.actuals a
JOIN greenwood.finance.budgets b
  ON a.cost_center = b.cost_center
 AND a.account     = b.account
 AND a.fiscal_period = b.fiscal_period
WHERE a.cost_center = 'IT'
  AND a.fiscal_period >= ADD_MONTHS(DATE_TRUNC('month', CURRENT_DATE()), -6)
GROUP BY a.fiscal_period
ORDER BY a.fiscal_period
```

## Recommendations framework

After presenting results, always include:

1. **Biggest overrun** — the cost center/account with the largest positive variance, with the dollar impact.
2. **Trend signal** — is the variance widening or closing over the periods shown?
3. **Quick action** — one corrective observation (e.g. "recurring overrun in account X suggests a budget rebaseline").

## Edge cases

- **Unbudgeted actuals** — if an actual row has no matching budget row, report it as
  unbudgeted spend rather than treating budget as zero silently.
- **Sparse periods** — if the requested period has no ledger rows, say so explicitly.
- **Aggregate only** — this skill works at the cost-center/account level. It does not read
  individual transactions, vendor invoices, or payroll detail.

## Data scope

- `greenwood.finance.actuals` — actual spend rolled up by cost center, account, and fiscal period
- `greenwood.finance.budgets` — budget amounts on the same keys
- No PII or transaction-level detail is accessed — figures are aggregate rollups only.
