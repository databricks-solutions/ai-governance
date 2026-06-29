# Don't Trust Your Guardrail — Benchmark It

*~3.5 min read · short-form draft · backing lab: [`labs/guardrails`](../labs/guardrails)*

Most teams bolt a guardrail onto their LLM app and never measure it. "We turned on a safety filter"
is a vibe, not a control. So we built a lab that turns guardrails into **numbers** on Databricks —
across the five categories that actually matter in production:

**PII redaction · PII blocking · unsafe content · jailbreak / prompt-injection · hallucination**

## Two places a guardrail lives

- **Online — on the endpoint.** Unity AI Gateway runs safety + PII guardrails on every request and
  response. Fast, centralized, no app changes.
- **Offline — a policy + a model.** Put the policy in the **system prompt**, the content in the user
  message, and let a model classify it. Flexible on nuanced techniques the endpoint filter doesn't model.

You want both, and you want to know which wins per category. So we run them head-to-head on the same
labeled data — including **hard negatives**, the benign-but-suspicious inputs ("help me *decimate* my
debt") that drive the metric nobody reports: the **false-positive rate**. Recall gets the press; FPR is
what gets a guardrail switched off in week one.

## The judge: a recent open model, not Llama Guard

Llama Guard 3/4 is dated for adversarial prompts. We deploy **`gpt-oss-safeguard-20b`** (OpenAI,
Apache-2.0) as a **custom serving endpoint** — a *policy-at-inference* model that reasons over the
policy you write — and run it against **Claude Haiku** as a managed baseline. Same policy, same content,
same JSON verdict: an honest open-+-self-hosted vs frontier-+-managed comparison on accuracy, FPR,
latency, and cost. (Swap in Granite Guardian 4.1 or Qwen3Guard — the flow is identical.)

## What running it actually taught us

We ran the harness on a live workspace, and the single biggest gotcha wasn't the policy — it was the
**plumbing**:

> **gpt-oss returns harmony-format content as a *list* of items (reasoning + output), not a string —
> and if your token budget is too low, the reasoning eats it and the JSON verdict never appears.**

A naive `response["choices"][0]["message"]["content"]` parser silently fails on *every* gpt-oss call.
The fix is two lines: extract the output text from the content list, and give reasoning models real
headroom (`max_tokens ≥ 2000`, `Reasoning: low`). Claude Haiku, by contrast, returns a plain string and
parsed cleanly out of the box. That asymmetry — managed model "just works," open model needs format
handling — is the kind of thing you only learn by *running* the benchmark, not reading the model card.

## The loop, made reproducible

1. Labeled datasets per category (bundled seed + hard negatives; optional JailbreakBench / HackAPrompt / RAGTruth).
2. Score **online vs offline (two judges)** — precision / recall / **FPR** per category.
3. Reproduce it as an **MLflow 3 GenAI evaluation** run (trace-linked, versioned per prompt change).
4. **Align** the judge with **DSPy + GEPA** using an FPR-aware metric, so it stops over-blocking.

## Takeaways

- Track **FPR**, not just recall.
- **Layer** endpoint guardrails (PII/safety) with a policy-driven judge (jailbreak) — and the judge is
  the *only* option for hallucination/groundedness.
- For the open judge, handle the **harmony content format** and give reasoning models token headroom.
- **Version** the policy as an MLflow run and regression-test it; **align** it with DSPy/GEPA.

A guardrail you haven't benchmarked is a guess. The lab is the benchmark, end to end →
[`labs/guardrails`](../labs/guardrails).
