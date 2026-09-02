---
name: model-performance-tracker
description: Track Advanced Analytics model performance and inference volumes from ML monitoring tables — accuracy/drift metrics by model and version, plus serving request volumes. Ask me which models are degrading or which endpoints are busiest.
---

> **Illustrative example** — demonstrates a well-formed `SKILL.md` for this reference
> implementation. Adapt the content to your own org; do not deploy verbatim.

# model-performance-tracker

## Overview

Surfaces Advanced Analytics ML operational health from **model-monitoring metadata**: it
tracks per-model quality metrics (accuracy, drift) by version, and inference/serving request
volumes over time. It reads aggregate monitoring metrics and request counts — not the scored
records or their features — so it stays a Tier-2 (internal) skill.

## When to use this skill

Reach for this skill when a data-science or MLOps user asks about model health:

- "Which models are degrading in accuracy over the last 30 days?"
- "Show me drift metrics by model version."
- "Which serving endpoints handled the most requests this week?"
- "Is the readmission model's performance trending down?"

## Instructions

When the user asks a model-health or inference-volume question:

1. **Identify the model(s) and time window** (default: last 30 days).
2. **Query `greenwood.analytics.model_metrics`** for quality metrics by model, version, and date.
3. **Join `greenwood.analytics.inference_logs`** for request volumes when throughput is asked.
4. **Present results** as a ranked table, then give 2–3 health observations
   (see the Recommendations framework).

## Examples

### Accuracy trend by model (last 30 days)

```sql
SELECT
  model_name,
  model_version,
  metric_date,
  metric_value AS accuracy
FROM greenwood.analytics.model_metrics
WHERE metric_name = 'accuracy'
  AND metric_date >= DATE_SUB(CURRENT_DATE(), 30)
ORDER BY model_name, metric_date
```

### Busiest serving endpoints (last 7 days)

```sql
SELECT
  model_name,
  COUNT(*) AS request_count
FROM greenwood.analytics.inference_logs
WHERE request_date >= DATE_SUB(CURRENT_DATE(), 7)
GROUP BY model_name
ORDER BY request_count DESC
```

## Recommendations framework

After presenting results, always include:

1. **Biggest degradation** — the model/version with the largest accuracy drop or highest drift, named.
2. **Trend signal** — which models are declining vs stable; flag any accuracy drop >5 points over the window.
3. **Quick action** — one MLOps observation (e.g. "drift on model X exceeds threshold — candidate for retraining").

## Edge cases

- **No metric rows** — if a model has inference logs but no monitoring metrics, report it as
  unmonitored rather than implying healthy.
- **Sparse windows** — if the requested window has no rows, say so explicitly.
- **Aggregate metrics only** — this skill reads monitoring metrics and request counts, never
  the individual scored records or their input features.

## Data scope

- `greenwood.analytics.model_metrics` — per-model, per-version quality metrics by date (aggregate)
- `greenwood.analytics.inference_logs` — serving request counts by model and date (aggregate)
- No PII or scored-record contents are accessed — only aggregate monitoring metrics.
