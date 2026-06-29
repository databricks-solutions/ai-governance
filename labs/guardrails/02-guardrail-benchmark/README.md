# Guardrail Lab · Part 2 — Benchmark

**Category:** Unity AI Gateway · Guardrails · **Status:** 🚧 Built (run on a workspace to populate numbers)

Turn guardrails into a **number**. This lab benchmarks all five categories — **PII redaction, PII
blocking, unsafe content, jailbreak, hallucination** — across two enforcement points on the *same*
labeled data, and reports **precision / recall / false-positive rate** per category, per enforcer.

## What you'll do
1. Build labeled datasets per category (bundled seed + hard negatives; optional JailbreakBench / Dolly).
2. Run two **managed offline judges** with the policy in the system prompt — open **`databricks-gpt-oss-20b`**
   vs frontier **`databricks-claude-haiku-4-5`** — and score each category. (No model to deploy.)
3. Run the **online** Unity AI Gateway guardrails (safety + PII) over the same data and score.
4. Reproduce the scoring as an **`mlflow.genai.evaluate`** run with a custom scorer.
5. **Align** the jailbreak judge with **DSPy + GEPA** using an FPR-aware metric; compare baseline vs aligned.
6. Read the **category × enforcer** results matrix.

## Why FPR
Recall gets the press; the **false-positive rate** — blocking benign traffic — is what gets a guardrail
switched off. Every category includes **hard negatives** (benign text that looks like a violation) so
the FPR is real.

## Databricks features
- Unity AI Gateway guardrails (online) + managed model-based judges (offline).
- **MLflow 3 GenAI evaluation** scorers + tracing.
- **DSPy + GEPA** prompt/policy optimization.

## Prerequisites
- Both judges are **managed Foundation Model API endpoints** — no GPU, no Hugging Face token, nothing to deploy.
- The gateway endpoint exists; permission to update its AI Gateway config.

> **Note on gotchas:** `gpt-oss` returns harmony-format content as a *list* (reasoning + output) and
> reasoning consumes tokens — the lab's `extract_text()` handles this and uses `max_tokens=2000` /
> `Reasoning: low`. The base `gpt-oss-20b` sometimes *refuses* an attack instead of classifying it; a
> dedicated guard model (optional, below) avoids that.

## Use a dedicated guard model (optional)
For stronger jailbreak/safety detection, deploy a guard model yourself and add it to `JUDGES`:
**`gpt-oss-safeguard-20b`** (policy-at-inference), **Granite Guardian 4.1-8B** (tops GuardBench, covers
hallucination), or **Qwen3Guard** (best adversarial / multilingual). The query + scoring flow is identical.

## Extend it
Swap in reputable public sets per category: **HarmBench / garak** (unsafe), **Lakera PINT /
HackAPrompt** (jailbreak), **RAGTruth** (hallucination). Persist the labeled `data` to
`${catalog}.${schema}` and re-run on every policy change as a regression test.

## Files
- `notebook.py` — the lab.
