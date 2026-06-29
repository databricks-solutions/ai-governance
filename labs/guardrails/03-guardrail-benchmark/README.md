# Guardrail Lab · Part 3 — Benchmark

**Category:** Unity AI Gateway · Guardrails · **Status:** 🚧 Built (run on a workspace to populate numbers)

Turn guardrails into a **number**. This lab benchmarks all five categories — **PII redaction, PII
blocking, unsafe content, jailbreak, hallucination** — across two enforcement points on the *same*
labeled data, and reports **precision / recall / false-positive rate** per category, per enforcer.

## What you'll do
1. Build labeled datasets per category (bundled seed + hard negatives; optional JailbreakBench / Dolly).
2. Run two **offline judges** with the policy in the system prompt — **`gpt-oss-safeguard-20b`** (Part 2)
   vs **Claude Haiku** — and score each category.
3. Run the **online** Unity AI Gateway guardrails (safety + PII) over the same data and score.
4. Reproduce the scoring as an **`mlflow.genai.evaluate`** run with a custom scorer.
5. **Align** the jailbreak judge with **DSPy + GEPA** using an FPR-aware metric; compare baseline vs aligned.
6. Read the **category × enforcer** results matrix.

## Why FPR
Recall gets the press; the **false-positive rate** — blocking benign traffic — is what gets a guardrail
switched off. Every category includes **hard negatives** (benign text that looks like a violation) so
the FPR is real.

## Databricks features
- Unity AI Gateway guardrails (online) + model-based judges (offline).
- **MLflow 3 GenAI evaluation** scorers + tracing.
- **DSPy + GEPA** prompt/policy optimization.

## Prerequisites
- **Part 2** deployed `gpt-oss-safeguard-20b` (otherwise that judge is skipped automatically).
- Claude Haiku is a managed endpoint (`databricks-claude-haiku-4-5`).
- The gateway endpoint exists; permission to update its AI Gateway config.

## Extend it
Swap in reputable public sets per category: **HarmBench / garak** (unsafe), **Lakera PINT /
HackAPrompt** (jailbreak), **RAGTruth** (hallucination). Persist the labeled `data` to
`${catalog}.${schema}` and re-run on every policy change as a regression test.

## Files
- `notebook.py` — the lab.
