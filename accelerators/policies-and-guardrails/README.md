# Accelerator — Policies & Guardrails

Prove guardrails actually *work* — not just that they're on. A ~3-hour deep dive on block vs mask,
how a block is delivered, path coverage, and measured effectiveness.

"Is the guardrail on?" is not "does it work?". This accelerator moves from configuring the safety
filter and PII detection to probing their behavior and measuring effectiveness on a labeled set.

## What you'll prove

Safety & PII guardrail fires on input/output · MASK vs BLOCK · how a block is delivered (4xx error
vs HTTP 200 + reason — the coding-agent "sticky block" gotcha) and that evaluation is fail-closed ·
path coverage across the OpenAI-compatible and provider-native paths · judge/red-team readiness ·
review of guardrail activity in the inference table · a full **effectiveness benchmark**.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`reference_queries.py`](reference_queries.py) | The app's checks for the six behavior/readiness steps — runnable without the app. |
| [`guardrail_benchmark.py`](guardrail_benchmark.py) | The effectiveness benchmark: precision / recall / **FPR** across PII redaction, PII blocking, unsafe content, jailbreak, and hallucination — online guardrails vs managed judges, with DSPy/GEPA alignment. This is what the app's effectiveness step references. |
| [`apply_guardrails.py`](apply_guardrails.py) | Deep dive: apply PII masking, safety, topic moderation, and keyword filtering at the gateway. |

## Prerequisites

- A governed serving endpoint with guardrails configured (safety filter + PII detection), and its
  payload **inference table** enabled (`<catalog>.<schema>.<prefix>_payload`).
- A SQL warehouse; `SELECT` on `system.access` for the readiness step.
- The benchmark is interactive — it streams datasets and calls models — so open it and set the
  `n_examples` widget rather than running it unattended.

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. The probe steps send prompts that
should be blocked; the SQL steps are read-only.
