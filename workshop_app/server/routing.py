"""Cost-routing ROI: measure what routing actually saves on token spend.

A simplified port of the internal app's Routing Impact demo, kept to one file because the
workshop only needs the measurable-ROI story, not the full three-tab demo. Three router
options are framed for the customer (Cost pillar):

  a) Smart router  — Databricks-managed routing. Roadmap; nothing to run here yet.
  b) Omnigent      — partner routing layer in front of the models.
  c) Custom router — a cheap classifier picks the cheapest model that meets the bar.

Only (c) executes: it is the one a customer can stand up today, and it is what produces a
defensible number. (a) and (b) are described in config/steps.yaml so the workshop can
position them honestly without pretending to demo them.

COST MODEL — READ BEFORE QUOTING THE DOLLARS
--------------------------------------------
Foundation Model APIs bill open-weight models in DBUs/MTok; Anthropic/OpenAI models on
Databricks bill against their own SKUs. We convert DBU->USD with `cost.dbu_to_usd` from
config/workshop.yaml, which defaults to a LIST-PRICE PLACEHOLDER. Until a customer sets
their negotiated rate, every dollar figure here is illustrative and the API says so via
`pricing_note` — surface it in the UI, don't hide it.

The savings figure is a COUNTERFACTUAL: what the same token volume would have cost on the
frontier model, minus what the route actually cost (classifier overhead included). It is
an honest per-request delta, not an annualized promise.
"""
from __future__ import annotations

import concurrent.futures
import json
import time

from .config import get_config, get_workspace_client

# Per-request cost attribution. The caller supplies a JSON object of string->string and it
# lands in `request_tags` in system.ai_gateway.usage, which is how per-project chargeback
# works without a server-side tag on every service.
#
# Why this module calls the gateway path directly instead of w.serving_endpoints.query():
# the SDK's query() is hard-wired to the LEGACY /serving-endpoints/{name}/invocations path and
# exposes no way to set headers, so it cannot carry the request-tag header at all. The gateway
# path accepts a plain endpoint name in `model`, so no config change was needed.
#
# Request tags are CALLER-supplied: an attribution signal, never an enforcement boundary.
# Server-side (endpoint/service) tags are the trustworthy ones for a budget filter.
#
# NOTE on verifying this: system.ai_gateway.usage lags real time by many minutes — on a
# reference workspace max(event_time) stayed 13-21 minutes behind wall clock across a 20-minute
# window. An empty result right after a call means "not ingested yet", NOT "the tag was
# dropped". Always compare max(event_time) to current_timestamp() before concluding anything;
# reading that lag as a dropped tag is an easy and expensive mistake.
REQUEST_TAGS_HEADER = "Databricks-Ai-Gateway-Request-Tags"
GATEWAY_CHAT_PATH = "/ai-gateway/mlflow/v1/chat/completions"

# Fallback panel, used when config/workshop.yaml has no `cost.routing` block. Prices are
# public list rates per million tokens; `unit` says how to convert. Endpoints are the
# pay-per-token FMAPI names available on most workspaces.
_DEFAULT_MODELS = {
    "frontier": {
        "endpoint": "databricks-claude-sonnet-4-5",
        "label": "Claude Sonnet 4.5",
        "tier": "frontier",
        "price": {"unit": "usd", "in": 3.0, "out": 15.0},
        "oneliner": "Frontier model — highest quality, highest cost. Reserve it for genuinely hard work.",
    },
    "mid": {
        "endpoint": "databricks-meta-llama-3-3-70b-instruct",
        "label": "Llama 3.3 70B",
        "tier": "strong-oss",
        "price": {"unit": "dbu", "in": 14.286, "out": 42.857},
        "oneliner": "Strong open-weight model — near-frontier on many tasks at a fraction of the cost.",
    },
    "cheap": {
        "endpoint": "databricks-meta-llama-3-1-8b-instruct",
        "label": "Llama 3.1 8B",
        "tier": "small-oss",
        "price": {"unit": "dbu", "in": 2.143, "out": 6.429},
        "oneliner": "Small open-weight model — cheapest and fastest; fine for simple, well-defined tasks.",
    },
}

PANEL_ORDER = ["frontier", "mid", "cheap"]

# Complexity 1..3 -> which model answers. Deliberately only three levels: a workshop room
# can reason about three, and the classifier is more reliable with a coarse scale.
COMPLEXITY_TO_MODEL = {1: "cheap", 2: "mid", 3: "frontier"}

COMPLEXITY_DEFS = {
    1: "Simple: a factual lookup or a direct calculation, a one-line definition, or a "
       "quick comparison to a target. If the answer is retrieval or plugging numbers "
       "into a formula, it is Simple.",
    2: "Medium: a bounded task with a mostly-correct answer that needs more than one "
       "step — explaining a concept, drafting a short document, comparing a few "
       "options, or the trade-offs of a single decision.",
    3: "Complex: reserve ONLY for open-ended, high-stakes work with multiple competing "
       "constraints — strategy, root-cause diagnosis across interacting factors, or "
       "rigorous architecture and financial-model design. If a competent analyst could "
       "answer it well in a few paragraphs, it is NOT Complex.",
}

# The classifier runs on the cheapest model — its cost is real overhead and is counted.
CLASSIFIER_KEY = "cheap"
CLASSIFIER_MAX_TOKENS = 200
DEFAULT_MAX_TOKENS = 512

# List-price placeholder. Override with `cost.routing.dbu_to_usd` (your negotiated rate).
DEFAULT_DBU_TO_USD = 0.070


def _routing_cfg() -> dict:
    return (get_config().get("cost", {}) or {}).get("routing", {}) or {}


def dbu_to_usd() -> float:
    return float(_routing_cfg().get("dbu_to_usd", DEFAULT_DBU_TO_USD))


def models() -> dict:
    """The model panel, with per-key endpoint overrides from config/workshop.yaml."""
    overrides = _routing_cfg().get("endpoints", {}) or {}
    out = {}
    for key, m in _DEFAULT_MODELS.items():
        entry = dict(m)
        if key in overrides:
            entry["endpoint"] = overrides[key]
        out[key] = entry
    return out


def price_per_mtok_usd(model_key: str) -> tuple[float, float]:
    """(input, output) USD per million tokens."""
    p = models()[model_key]["price"]
    if p["unit"] == "usd":
        return float(p["in"]), float(p["out"])
    rate = dbu_to_usd()
    return float(p["in"]) * rate, float(p["out"]) * rate


def cost_usd(model_key: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = price_per_mtok_usd(model_key)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def pricing_note() -> str:
    return (
        f"Open-weight models are billed in DBU/MTok and converted at ${dbu_to_usd()}/DBU; "
        "frontier models are billed in USD/MTok at list price. Set "
        "`cost.routing.dbu_to_usd` in config/workshop.yaml to your negotiated rate — "
        "until then these dollar figures are illustrative, though the token counts are real."
    )


def _extract_text(content) -> str:
    """FMAPI returns a string for chat models and a list of blocks for reasoning models."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(t for t in texts if t).strip()
    return str(content) if content is not None else ""


def request_tags() -> dict:
    """The project tags this workshop attaches to every model call it makes.

    Same values as the server-side tags in the Cost pillar, so a customer can compare the
    two paths in `system.ai_gateway.usage` — `request_tags` (these) vs `endpoint_tags`.
    """
    proj = get_config().get("project", {}) or {}
    keys = ("name", "cost_center", "environment", "use_case")
    tags = {("project" if k == "name" else k): str(proj[k]) for k in keys if proj.get(k)}
    return tags


def query(model_key: str, prompt: str, max_tokens: int | None = None) -> dict:
    """Call one model and return the answer plus measured tokens, latency, and cost.

    Calls the Gateway path (`/ai-gateway/mlflow/v1/chat/completions`) with an FQN or endpoint
    name in `model`, rather than the SDK's `serving_endpoints.query()`, because query() targets
    the legacy invocations path and cannot set the request-tag header.

    Never raises: an endpoint that is missing or throttled becomes an `error` field so a
    live workshop shows a clear message on one card instead of failing the whole step.
    """
    m = models()[model_key]
    max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    w = get_workspace_client()
    tags = request_tags()
    start = time.monotonic()
    base = {"model_key": model_key, "label": m["label"], "tier": m["tier"],
            "endpoint": m["endpoint"], "request_tags": tags,
            "gateway_path": GATEWAY_CHAT_PATH}
    try:
        resp = w.api_client.do(
            "POST", GATEWAY_CHAT_PATH,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     REQUEST_TAGS_HEADER: json.dumps(tags)},
            body={"model": m["endpoint"],
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens},
        )
        duration = time.monotonic() - start
        usage = (resp or {}).get("usage") or {}
        in_tok = usage.get("prompt_tokens") or 0
        out_tok = usage.get("completion_tokens") or 0
        choices = (resp or {}).get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        return {
            **base,
            "answer": _extract_text(content),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "duration_s": round(duration, 2),
            "cost_usd": cost_usd(model_key, in_tok, out_tok),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 — surface endpoint errors per-card, don't fail the step
        return {**base, "answer": None, "input_tokens": 0, "output_tokens": 0,
                "duration_s": round(time.monotonic() - start, 2), "cost_usd": 0.0,
                "error": str(e)[:300]}


def compare(prompt: str) -> dict:
    """Send one prompt to every model in parallel — the raw cost/latency/quality spread.

    This is the step that makes the ROI argument concrete before any routing exists: the
    same question, three price points, and the answers side by side so the room can judge
    whether the cheap model was actually good enough.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(PANEL_ORDER)) as ex:
        results = list(ex.map(lambda k: query(k, prompt), PANEL_ORDER))
    priced = [r for r in results if not r["error"]]
    spread = None
    if len(priced) > 1:
        costs = [r["cost_usd"] for r in priced]
        hi, lo = max(costs), min(costs)
        spread = {"max_usd": hi, "min_usd": lo,
                  "ratio": round(hi / lo, 1) if lo > 0 else None}
    return {"results": results, "spread": spread, "pricing_note": pricing_note()}


def _classifier_prompt(prompt: str) -> str:
    lines = "\n".join(f"{n} = {COMPLEXITY_DEFS[n]}" for n in sorted(COMPLEXITY_DEFS))
    return (
        "You are a routing classifier. Rate the COMPLEXITY of the user's request on a 1-3 "
        "scale to choose which LLM should answer it, using EXACTLY these definitions:\n"
        f"{lines}\n"
        "Be conservative and cost-aware: assign the LOWEST level whose definition the "
        "request clearly meets. Do NOT round up. When torn between two levels, pick the "
        "lower one.\n"
        'Respond with ONLY a JSON object: {"complexity": <1-3>, "reason": "<short>"}\n\n'
        f"Request to classify:\n{prompt}"
    )


def classify(prompt: str) -> dict:
    """Score complexity with the cheap model. Its cost counts as routing overhead.

    Fails SAFE: if the classifier errors or returns unparseable output we route to the
    frontier model. A router that silently downgrades on failure would trade correctness
    for cost, which is the opposite of what a governance workshop should demonstrate.
    """
    result = query(CLASSIFIER_KEY, _classifier_prompt(prompt), max_tokens=CLASSIFIER_MAX_TOKENS)

    complexity, reason = 3, "defaulted to frontier (classifier unavailable)"
    if result["answer"]:
        text = result["answer"]
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            try:
                parsed = json.loads(text[i:j + 1])
                complexity = min(3, max(1, int(parsed.get("complexity", 3))))
                reason = str(parsed.get("reason", ""))[:200]
            except (ValueError, TypeError):
                reason = "defaulted to frontier (classifier returned unparseable JSON)"
    return {
        "complexity": complexity,
        "reason": reason,
        "classifier_model": models()[CLASSIFIER_KEY]["label"],
        "classifier_cost_usd": result["cost_usd"],
        "classifier_duration_s": result["duration_s"],
        "classifier_error": result["error"],
    }


def route(prompt: str) -> dict:
    """Classify, dispatch to the cheapest sufficient model, and price the counterfactual.

    `savings_usd` compares the routed cost (classifier + chosen model) against what the
    SAME token volume would have cost on the frontier model. That is an approximation:
    the frontier model would likely emit a different number of output tokens for the same
    prompt. It is the honest, cheap comparison — one extra call, not two — and the API
    labels it so the workshop can state the caveat out loud.
    """
    c = classify(prompt)
    chosen_key = COMPLEXITY_TO_MODEL.get(c["complexity"], "frontier")
    answer = query(chosen_key, prompt)

    routed_cost = c["classifier_cost_usd"] + answer["cost_usd"]
    frontier_cost = cost_usd("frontier", answer["input_tokens"], answer["output_tokens"])
    savings = frontier_cost - routed_cost
    savings_pct = round(savings / frontier_cost * 100, 1) if frontier_cost > 0 else 0.0

    return {
        "classification": c,
        "chosen": answer,
        "routed_cost_usd": routed_cost,
        "routed_duration_s": round(c["classifier_duration_s"] + answer["duration_s"], 2),
        "always_frontier_cost_usd": frontier_cost,
        "savings_usd": savings,
        "savings_pct": savings_pct,
        "counterfactual_note": (
            "Frontier cost is priced on the ROUTED response's token counts. The frontier "
            "model would emit a different number of output tokens for the same prompt, so "
            "treat this as a close estimate of the per-request delta, not an exact figure."
        ),
        "pricing_note": pricing_note(),
    }


def panel() -> dict:
    """The model panel + routing policy, for the UI to render before anything is run."""
    M = models()
    out = []
    for key in PANEL_ORDER:
        m = M[key]
        in_usd, out_usd = price_per_mtok_usd(key)
        out.append({
            "key": key, "label": m["label"], "tier": m["tier"], "endpoint": m["endpoint"],
            "oneliner": m["oneliner"], "price_unit": m["price"]["unit"],
            "usd_in_per_mtok": round(in_usd, 4), "usd_out_per_mtok": round(out_usd, 4),
        })
    return {
        "models": out,
        "dbu_to_usd": dbu_to_usd(),
        "request_tags": request_tags(),
        "request_tags_header": REQUEST_TAGS_HEADER,
        "attribution_note": (
            f"Every model call below is sent through {GATEWAY_CHAT_PATH} with the "
            f"{REQUEST_TAGS_HEADER} header, so its tokens attribute to this project in "
            "system.ai_gateway.usage.request_tags. Request tags are caller-supplied — use "
            "them for attribution, never as an enforcement boundary."),
        "classifier_model": M[CLASSIFIER_KEY]["label"],
        "routing_map": {str(k): M[v]["label"] for k, v in COMPLEXITY_TO_MODEL.items()},
        "complexity_defs": {str(k): v for k, v in COMPLEXITY_DEFS.items()},
        "pricing_note": pricing_note(),
    }
