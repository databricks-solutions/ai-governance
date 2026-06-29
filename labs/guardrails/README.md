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
| 2 | [Deploy `gpt-oss-safeguard-20b`](02-deploy-oss-safeguard) | Deploy a recent, **policy-driven** open safety model as a custom endpoint and run it **head-to-head against Claude Haiku** on the same policy + content. |
| 3 | [Guardrail benchmark](03-guardrail-benchmark) | The full labeled benchmark: **online** (endpoint guardrails) vs **offline** (two judges) across all five categories, scored with MLflow, with **DSPy + GEPA** judge alignment. |

## Two ways to enforce, both covered

- **Online — at the endpoint.** Unity AI Gateway guardrails (safety, PII, keywords) run on every
  request/response. Fast, centralized, no app changes. *(Lab 01)*
- **Offline / model-based — a judge.** Any model + a policy in the **system prompt** classifies
  content as allow/block. Flexible on nuanced techniques the endpoint filter doesn't model. We use a
  self-hosted **`gpt-oss-safeguard-20b`** and **Claude Haiku** as the two judges. *(Labs 02–03)*

Layering both mirrors the gateway's own input/output guardrail split.

## On model choice (jailbreak)

Llama Guard 3/4 is dated for adversarial prompts (high benign accuracy, low harmful detection). The
labs use **`gpt-oss-safeguard-20b`** (Apache-2.0, reasons over *your* policy at inference) and are
`HF_MODEL_ID`-swappable to **Granite Guardian 4.1-8B** (best GuardBench coverage incl. hallucination)
or **Qwen3Guard** (best adversarial / multilingual).

## Prerequisites
- The bundle deployed so the gateway endpoint exists (see repo root `README.md`).
- Permission to update the endpoint's AI Gateway configuration.
- For Lab 02: a **GPU cluster** + a Hugging Face token secret (`ai_governance/hf_token`) and
  GPU/provisioned-throughput serving quota.

## Run it
Open each lab's `notebook.py` and run top-to-bottom, or run Lab 01 via the `run_guardrail_labs` job.
Labs 02–03 are GPU-heavy / interactive and are run manually.

> See also: repo [`docs/`](../../docs) for architecture and getting-started.
