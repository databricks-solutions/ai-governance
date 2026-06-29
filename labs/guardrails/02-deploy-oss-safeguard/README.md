# Lab 02 — Deploy `gpt-oss-safeguard-20b` as a custom guardrail model

**Category:** Unity AI Gateway · Guardrails · **Status:** 🚧 Built (deploy step needs a GPU + HF token)

Deploy OpenAI's **`gpt-oss-safeguard-20b`** (Apache-2.0, policy-at-inference safety reasoning) as a
**custom model serving endpoint**, then run it **head-to-head against Claude Haiku** on the same
policy + content. This is the recent, jailbreak-capable alternative to the dated Llama Guard line.

## Why this model
- **Policy in the system prompt**: the guardrail logic is a prompt you version/tune, not a retrain —
  same ergonomics as an LLM-judge, but a model fine-tuned for safety classification.
- **Self-hosted**: data stays in your tenancy; fixed cost via provisioned throughput.
- **Strong on adversarial prompts**, where Llama Guard 3/4 are "too permissive."

## What you'll do
1. Log `openai/gpt-oss-safeguard-20b` (transformers flavor, `llm/v1/chat` task) and register to Unity Catalog.
2. Create a provisioned-throughput (or GPU custom) serving endpoint.
3. Define the **jailbreak policy as a system prompt**.
4. Classify probes with **gpt-oss-safeguard** and **`databricks-claude-haiku-4-5`** and compare verdicts + latency.

## Databricks features
- Custom model serving via **MLflow transformers** + Unity Catalog model registry.
- **Provisioned-throughput Foundation Model APIs** (gpt-oss is a supported architecture).
- Apples-to-apples judge comparison against a managed Claude endpoint.

## Prerequisites
- A **GPU cluster** for the logging step (~40 GB weights from Hugging Face).
- HF token secret: `databricks secrets put-secret ai_governance hf_token`.
- GPU / provisioned-throughput serving quota in your region.

## Swap the model
Change `HF_MODEL_ID` to **`ibm-granite/granite-guardian-4.1-8b`** (best GuardBench coverage incl.
hallucination) or a **Qwen3Guard** size (best adversarial / multilingual). The deploy + query flow is identical.

## Files
- `notebook.py` — the lab.

> The full labeled benchmark (precision / recall / FPR across PII redaction, PII blocking, unsafe
> content, jailbreak, hallucination) lives in **Lab 03 — guardrail benchmark**.
