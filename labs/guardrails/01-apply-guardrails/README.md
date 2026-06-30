# Guardrail Lab · Part 1 — Apply guardrails

**Apply Unity AI Gateway guardrails at the endpoint and watch them enforce policy on every client.**

## What you'll do
1. Apply input + output guardrails in one Gateway update (PII mask, safety, topic allow-list, keyword block).
2. Watch **PII masking** redact contact details before the model sees them.
3. Trip **topic moderation** with an off-topic prompt.
4. Trip **invalid-keyword filtering** with a banned term.
5. Reset guardrails so the endpoint is clean for other labs.

## How it works
Guardrails inspect prompts (input) and completions (output) and act on unsafe or non-compliant
content: PII `MASK`/`BLOCK`, a safety filter, topic moderation (a `valid_topics` allow-list), and
invalid-keyword filtering. They run **at the Gateway**, so every client of the endpoint is protected
uniformly. `MASK` keeps requests flowing while redacting PII; `BLOCK` rejects them outright. Pair
guardrails with payload logging (the Models *Usage tracking* lab / inference tables) to audit what was
blocked and why.

> This is the apply/demo lab. **Part 2 — Benchmark** measures guardrail quality (precision / recall /
> FPR) across all five categories.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_guardrail_labs` job. Requires the bundle
deployed: `databricks bundle deploy -t dev`.
