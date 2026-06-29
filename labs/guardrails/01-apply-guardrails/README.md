# Guardrail Lab · Part 1 — Apply guardrails

**Category:** Unity AI Gateway · Guardrails · **Status:** ✅ Built

Inspect and act on prompts and completions to enforce safety and compliance policy at the endpoint.

## What you'll do
1. Apply input + output guardrails in one Gateway update.
2. Watch **PII masking** redact contact details before the model sees them.
3. Trip **topic moderation** with an off-topic prompt.
4. Trip **invalid keyword filtering** with a banned term.

## Databricks features
- Unity AI Gateway **guardrails**: `pii` (`MASK`/`BLOCK`), `safety`, `valid_topics`, `invalid_keywords`.

## Prerequisites
- The bundle deployed so the gateway endpoint exists.
- Permission to update the endpoint's AI Gateway configuration.

## Run it
Open `notebook.py` and run top-to-bottom, or via the `run_guardrail_labs` job.
