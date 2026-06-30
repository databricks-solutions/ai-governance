# 🛡️ Guardrails

Self-contained labs for **evaluating and operating AI guardrails** on Databricks — across the five
categories that matter in production:

**PII redaction · PII blocking · unsafe content · jailbreak / prompt-injection · hallucination**

Where the *Models* track is about general platform governance (rate limits, cost/FinOps, tagging,
resilience), this track is specifically about **stopping bad inputs and outputs** — and, crucially,
**measuring** whether your guardrails actually work.

## Why a separate track

A guardrail you haven't evaluated is a guess. These labs treat guardrails as a measurable control:
run them in **Log mode**, capture decisions in **inference tables**, and score them against labeled
data for **precision, recall, and false-positive rate** — the number that decides whether a guardrail
survives contact with production.

## The labs

| Part | Lab | What it proves |
|------|-----|----------------|
| 1 | [Apply guardrails](01-apply-guardrails) | Turn on the Unity AI Gateway built-ins (PII `MASK`/`BLOCK`, safety, topic moderation, keyword filtering) and watch the gateway enforce them on every client. |
| 2 | [Guardrail benchmark](02-guardrail-benchmark) | The full labeled benchmark: **online** (endpoint guardrails) vs **offline** (two managed judges) across all five categories, scored with MLflow, with **DSPy + GEPA** judge alignment. |

## Two ways to enforce, both covered

- **Online — at the endpoint.** Unity AI Gateway guardrails (safety, PII, keywords) run on every
  request/response. Fast, centralized, no app changes. *(Part 1)*
- **Offline / model-based — a judge.** Any model + a policy in the **system prompt** classifies
  content as allow/block. Flexible on nuanced techniques the endpoint filter doesn't model. We use two
  **managed** judges — open **`databricks-gpt-oss-20b`** and frontier **Claude Haiku** — so there's
  nothing to deploy. *(Part 2)*

Layering both mirrors the gateway's own input/output guardrail split.

## On model choice (jailbreak)

Llama Guard 3/4 is dated for adversarial prompts (high benign accuracy, low harmful detection). The
benchmark uses managed models out of the box. For stronger, dedicated guard detection you can deploy
one yourself and add it to `JUDGES`: **`gpt-oss-safeguard-20b`** (Apache-2.0, reasons over *your* policy
at inference), **Granite Guardian 4.1-8B** (best GuardBench coverage incl. hallucination), or
**Qwen3Guard** (best adversarial / multilingual). The benchmark flow is unchanged.

## Prerequisites
- The bundle deployed so the gateway endpoint exists (see repo root `README.md`).
- Permission to update the endpoint's AI Gateway configuration.
- The offline judges are **managed** Foundation Model API endpoints — no GPU, no Hugging Face token, nothing to deploy.

## Run it
Open each lab's `notebook.py` and run top-to-bottom, or run Part 1 via the `run_guardrail_labs` job.
Part 2 is interactive (and makes model calls) — run it manually.
