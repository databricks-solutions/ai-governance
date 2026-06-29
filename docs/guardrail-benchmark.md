# Benchmarking AI Guardrails on Databricks

*Long-form documentation draft — the methodology and reproducible lab behind the
[`labs/guardrails`](../labs/guardrails) track.*

## Why benchmark guardrails at all

Every team deploying generative AI eventually adds guardrails — filters that stop bad inputs (prompt
injection, PII, unsafe requests) and bad outputs (leaked PII, unsafe content, hallucinations). Almost
none of them **measure** whether those guardrails work. "We enabled a safety filter" is a statement of
intent, not a control you can stand behind in an audit.

Databricks' own guidance points the right way: the guardrails docs prescribe running in **Log mode**
first, capturing every decision in **inference tables**, and using those payloads to *evaluate accuracy
and tune the policy*. Internal work shows the bar is reachable — a PII-detection system (LogSentinel)
reported ~92% precision / 95% recall on 2,258 labeled samples, and a prompt-injection study reported a
>90% drop in attack success with custom guard models. What's been missing is a **single, reproducible
benchmark** that does this across every guardrail category and lets you compare enforcement options.
This lab is that benchmark.

## The five categories

We evaluate the categories that map to real production controls:

| Category | "Violation" means | Typical enforcement |
|---|---|---|
| **PII redaction** | Input/output contains PII that should be masked | Gateway PII `MASK` |
| **PII blocking** | Input/output contains PII that should be rejected | Gateway PII `BLOCK` |
| **Unsafe content** | Request/response is harmful (violence, self-harm, illicit, hate) | Gateway `safety` / judge |
| **Jailbreak / prompt-injection** | Deliberate attempt to subvert the system | Policy-driven judge |
| **Hallucination** | Response asserts claims unsupported by its context | Groundedness judge |

Each category needs three kinds of examples, and the third is the one teams skip:

1. **Attacks / violations** (expect block).
2. **Benign** inputs (expect allow).
3. **Hard negatives** — benign text that *looks* like a violation (an order number that looks like a
   phone, "help me *decimate* my debt," "translate 'ignore your instructions' into French"). Hard
   negatives are what expose **over-blocking**.

## Two enforcement points

The lab measures both, on the *same* labeled data:

- **Online — Unity AI Gateway guardrails.** Safety and PII run on the serving endpoint for every
  client, uniformly, with no application change. Best for PII and unsafe content. There is no built-in
  online hallucination guardrail, so that category is judge-only.
- **Offline — a policy-driven judge.** The policy goes in the **system prompt**; the content goes in the
  user message; the model returns a structured verdict. Best for nuanced **jailbreak** detection and the
  only option for **hallucination/groundedness**. We benchmark two judges head-to-head:
  - **`gpt-oss-safeguard-20b`** — OpenAI's Apache-2.0 *policy-at-inference* safety model, deployed as a
    custom Databricks endpoint (self-hosted, fixed cost, data stays in tenancy).
  - **`databricks-claude-haiku-4-5`** — a managed frontier model (per-token, zero-ops).

Same policy, same content, same JSON schema → a fair comparison on accuracy, false-positive rate,
latency, and cost. The split mirrors the gateway's own input/output guardrails: defense-in-depth means
running both layers.

### On model choice

Llama Guard 3/4 is dated for adversarial prompts — benchmarks place it in the "too permissive" region
(high benign accuracy, low harmful detection). `gpt-oss-safeguard-20b` reasons over the policy you write,
which makes it tunable without retraining and resilient to obfuscation. The lab is `HF_MODEL_ID`-swappable
to **Granite Guardian 4.1-8B** (tops GuardBench; covers jailbreak *and* hallucination) or **Qwen3Guard**
(best adversarial / multilingual).

## Deploying `gpt-oss-safeguard-20b` (and the gotcha that matters)

The base `gpt-oss-20b` is a managed Foundation Model API endpoint, but the **safeguard** fine-tune is
not — so the lab deploys it as a **custom model**: log the Hugging Face weights with the MLflow
transformers flavor (`llm/v1/chat` task), register to Unity Catalog, and create a provisioned-throughput
(or GPU custom) serving endpoint.

The single biggest practical gotcha is **not** the policy — it's the response format. Running the harness
on a live workspace surfaced it immediately:

> **gpt-oss (and the safeguard fine-tune) return harmony-format content as a *list* of items**
> (`[{'type':'reasoning', ...}, {'type':'output', ...}]`), **not a plain string. And reasoning models
> consume tokens before emitting the answer — with too small a budget, the reasoning trace eats the whole
> response and the JSON verdict is truncated away.**

A conventional parser — `response["choices"][0]["message"]["content"]` → regex — fails silently on
*every* gpt-oss call. The fix is small but essential, and it's baked into the lab:

```python
def extract_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for it in content or []:                 # harmony: list of reasoning/output items
        if isinstance(it, dict) and it.get("type") in ("text", "output_text") and it.get("text"):
            parts.append(it["text"])
    return "\n".join(parts)
# ...and give reasoning models headroom: max_tokens >= 2000, "Reasoning: low" in the system prompt.
```

Claude Haiku, by contrast, returns a plain string and parses cleanly with no special handling. That
asymmetry — managed model "just works," open model needs format handling and a token budget — is exactly
the kind of operational detail a benchmark surfaces and a model card doesn't.

> Note: the *base* `gpt-oss-20b` sometimes **refuses** an attack input ("I'm sorry, but I can't comply")
> instead of classifying it, which a guardrail judge must treat as a parse miss. The **safeguard
> fine-tune** is trained to classify rather than refuse, which is the whole point of using it over the
> base model.

## The benchmark and the metric that matters

For each category and each enforcer we report **precision, recall, and false-positive rate**, where
`violation = 1` is the positive class:

- **Recall** — of the real violations, how many were caught.
- **FPR** — of the benign inputs, how many were wrongly blocked. **This is the number that decides
  adoption.** A guardrail with 99% recall and a 15% false-positive rate gets disabled the first time it
  blocks a paying customer's legitimate request.

The output is a **category × enforcer** matrix (recall and FPR side by side), so you can pick the right
enforcer per category — e.g., online PII masking for redaction, the policy judge for jailbreak and
hallucination.

## Reproduce it as an MLflow evaluation

The same scoring runs as an `mlflow.genai.evaluate()` job with a custom scorer, so every result is
trace-linked in the MLflow UI and every policy revision is a versioned run you can regression-test. Persist
the labeled dataset to Unity Catalog (`${catalog}.${schema}`) and re-run on each change.

## Aligning the judge with DSPy + GEPA

A static policy is a guess. The lab optimizes the jailbreak judge with **DSPy + GEPA**, seeding the
optimizer with your current policy and an **FPR-aware feedback metric** — it tells the reflection model
specifically when it produced a *false positive* vs a *false negative*, so the evolved policy learns to
stop over-blocking. Baseline vs aligned FPR/recall are logged side by side; the optimized instruction is
your new, policy-aligned guardrail prompt, ready to redeploy.

## Validation status

The harness has been run end-to-end on a live workspace for the offline path: Claude Haiku passed the
bundled sanity set cleanly across all four judge categories, and the gpt-oss path was validated after the
harmony-format fix above. The **online gateway** path requires the bundle's gateway endpoint, and the
**`gpt-oss-safeguard-20b`** custom deploy requires a GPU + Hugging Face token; both run in a configured
workspace. Full benchmark numbers come from running the lab against the larger labeled sets with the
deployed safeguard model — the lab is built to produce them reproducibly.

## Reproduce / extend

- Swap in reputable public datasets per category: **HarmBench / garak** (unsafe), **Lakera PINT /
  HackAPrompt** (jailbreak), **RAGTruth** (hallucination).
- Swap the judge model (`gpt-oss-safeguard-20b` → Granite Guardian / Qwen3Guard) with no other changes.
- Persist `data` to Unity Catalog and wire the eval into CI as a regression gate on policy changes.

## References

- Unity AI Gateway guardrails (Log mode, inference tables): Databricks docs.
- Internal: LogSentinel PII detection; prompt-injection mitigation study (garak prompts, >90% reduction).
- Models: OpenAI gpt-oss-safeguard; IBM Granite Guardian 4.1; Qwen3Guard; GuardBench.
- Benchmarks: JailbreakBench, HackAPrompt, Lakera PINT, RAGTruth; OWASP LLM01:2025 Prompt Injection.
- Lab: [`labs/guardrails`](../labs/guardrails) — Part 1 (apply), Part 2 (deploy + bake-off), Part 3 (benchmark).
