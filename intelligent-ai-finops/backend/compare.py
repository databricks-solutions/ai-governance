"""Tab 1 - Compare. Fan one prompt out to N models and stream each lane back as
SSE (§6.1, §7). Cost is authored here from token usage, not by the frontend; the
client animates the reveal toward these server-given numbers and only *selects*
the winner (cheapest lane within 1.0 judge point of the best).

One lane == one SSE connection (the client opens them concurrently), which keeps
the streaming simple and survives the Databricks Apps proxy cleanly. For the
"Optimize + Run" flow the client opens two connections per model (the prompt as
typed AND the optimized rewrite) so it can show a true before/after.

Every `done` event carries the FULL tokenomics (input/output/total tokens) and a
`context` block - the exact request payload sent to the model plus the routing
decision (complexity, tier, counterfactual). That powers the per-lane "Show
context" panel and the token-delta story.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator

from . import judge as judge_module
from . import models, routing

# A fixed, honest-sounding answer for demo mode. Live mode streams the real one.
_SAMPLE = (
    "Routing decisions land in inference tables the moment the call completes, so "
    "cost, latency, and the policy that fired are all queryable from Unity Catalog "
    "without any extra instrumentation."
)

# A structured demo answer, returned when the prompt asks for structure (i.e. the
# optimized rewrite) so the before/after output difference is visible offline.
_SAMPLE_STRUCTURED = (
    "Assumptions: routing runs at the gateway, one request at a time.\n\n"
    "Key steps:\n"
    "1. Classify the prompt's complexity.\n"
    "2. Match it to the cheapest tier that clears the quality bar.\n"
    "3. Serve via Model Serving and log the receipt to an inference table.\n\n"
    "Result: cost, latency, and the policy that fired are all queryable from "
    "Unity Catalog with no extra instrumentation. Main risk: a mis-classified "
    "prompt is served too cheaply - the LLM-as-judge guardrail catches it."
)

# Rough token overhead for the (implicit) system framing + chat wrapper, added on
# top of the prompt itself. Demo tokens scale with the real prompt length so the
# optimize/plain delta is honest offline; live mode uses real usage numbers.
_SYS_OVERHEAD_TOK = 40
_CHARS_PER_TOK = 4

# Generous safety ceiling. Reasoning is SUPPRESSED per family in models.live_query
# (Claude thinking disabled, gpt reasoning_effort low), so the whole budget is
# answer text. A multi-part business question (e.g. the M&A valuation prompt has
# ~8 required parts) needs real headroom to cover every part AND finish - a tight
# 300-word / ~1200-token cap made a verbose model truncate mid-table before it
# reached the final parts (recommendation, risks), which the judge then rightly
# penalised as incomplete. 2500 tokens (~1800 words) is far above the ~450-word
# target below, so the model finishes (finish_reason=stop) instead of being cut.
# 4096 gives comfortable headroom over the longest complete answer observed
# (opus-5 on the M&A prompt ~2.4k tokens); if a very verbose model still hits the
# cap, models.live_query continues the answer automatically so it never truncates.
_ANSWER_MAX_TOKENS = 4096

# Every lane gets the SAME instruction (fair comparison). The priority is
# COMPLETENESS + a clean finish, not a hard word count: a hard cap made reasoning
# models allocate their budget poorly and drop the last requested part. Instead we
# ask for every part, in order, always finishing, with a soft length target and no
# giant tables - so a multi-part answer completes cleanly and the judge scores
# quality, not a truncation artefact.
_ANSWER_SYSTEM = (
    "You are answering a business question that may have several parts. Cover EVERY part "
    "that is asked, in order, and ALWAYS finish - never stop mid-sentence, mid-list, or "
    "mid-table, and never drop the final requested part (such as a recommendation or a list "
    "of risks). Be concise and skimmable: aim for about 400-450 words, use short paragraphs "
    "or compact bullets instead of large tables, and if you are running long, tighten the "
    "earlier parts so the whole answer completes cleanly."
)
# How often to emit an SSE keep-alive comment while a slow model is still
# generating, so the Databricks Apps proxy never idles the connection out.
_KEEPALIVE_SECS = 8.0


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _est_tokens(text: str) -> int:
    return max(1, round(len(text) / _CHARS_PER_TOK))


def _demo_answer(prompt: str) -> str:
    """Pick a demo answer that reflects the prompt so an optimized (structured)
    prompt yields a visibly different, structured answer vs the plain one."""
    if "structure" in prompt.lower() or "labelled sections" in prompt.lower():
        return _SAMPLE_STRUCTURED
    return _SAMPLE


def _demo_judge_reason(score: float) -> str:
    """A short, generic rationale for demo mode (live mode returns a real,
    prompt-specific one from the judge model)."""
    if score >= 9.0:
        return "Thorough and precise: fully addresses the question with clear structure and correct detail."
    if score >= 8.3:
        return "Strong and accurate; a little less depth on edge cases than the very best answer."
    return "Solid and on-topic, and clears the quality bar; less exhaustive than the top answer."


def _context(m: models.Model, prompt: str, in_tok: int, out_tok: int) -> dict:
    """The 'Show context' payload: the exact request sent to the model plus the
    routing decision that explains WHY this tier is or isn't a fit."""
    complexity = routing.classify(prompt)
    required = routing.tier_for(complexity)
    frontier = models.frontier_model()
    return {
        "request": {
            "endpoint": m.id,
            "messages": [{"role": "user", "content": prompt}],
            "params": {"max_tokens": _ANSWER_MAX_TOKENS, "temperature": 0.0},
        },
        "decision": {
            "complexity": complexity,
            "tier": m.tier,
            "requiredTier": required,
            "clears": models.TIER_ORDER.index(m.tier) <= models.TIER_ORDER.index(required),
            "priceInPer1m": round(m.price_in_per_1m, 4),
            "priceOutPer1m": round(m.price_out_per_1m, 4),
            "counterfactual": {
                "model": frontier.short,
                "costUsd": round(frontier.cost_usd(in_tok, out_tok), 6),
            },
        },
    }


def stream_lane(model_id: str, prompt: str, demo: bool = True,
                judge_model: str | None = None) -> Iterator[str]:
    """Yield SSE events for one lane: meta → token* → done.

    Live mode calls the real model via FMAPI (real answer/tokens/latency) and
    scores the answer with `judge_model` (a real LLM-as-judge). Demo mode streams
    a placeholder answer and synthesises the numbers so it runs offline.
    """
    m = models.by_id(model_id)
    latency = models.demo_latency_ms(m)
    judge = models.demo_judge(m)
    judge_reason = ""

    yield _sse({
        "type": "meta", "modelId": m.id, "short": m.short, "tier": m.tier,
        "priceIn": m.price_in_per_1m, "priceOut": m.price_out_per_1m,
    })

    if demo:
        answer = _demo_answer(prompt)
        # Tokens scale with the ACTUAL prompt/answer so the optimize-vs-plain
        # token delta is real, not a fixed constant.
        in_tok = _SYS_OVERHEAD_TOK + _est_tokens(prompt)
        out_tok = _est_tokens(answer)
        final_cost = m.cost_usd(in_tok, out_tok)

        words = answer.split(" ")
        delay = 60.0 / m.profile["wpm"]  # latency-shaped pacing
        time.sleep(min(latency, 1500) / 1000 * 0.22)
        acc: list[str] = []
        for i, w in enumerate(words, 1):
            acc.append(w)
            time.sleep(delay)
            yield _sse({"type": "token", "text": " ".join(acc), "costUsd": final_cost * (i / len(words))})
        judge_reason = _demo_judge_reason(judge)
        errored = False
    else:
        # Real FMAPI call for the selected model + prompt, run on a worker thread
        # so we can emit SSE keep-alives while a slow model (e.g. opus) generates.
        box: dict = {}
        in_tok, out_tok = _SYS_OVERHEAD_TOK + _est_tokens(prompt), 0
        final_cost = 0.0

        def _work():
            try:
                box["live"] = models.live_query(m, prompt, max_tokens=_ANSWER_MAX_TOKENS, system=_ANSWER_SYSTEM, temperature=0.0)
            except Exception as e:  # noqa: BLE001 - surface as a lane error, don't hang
                box["err"] = str(e)

        th = threading.Thread(target=_work, daemon=True)
        th.start()
        while th.is_alive():
            th.join(timeout=_KEEPALIVE_SECS)
            if th.is_alive():
                yield ": keepalive\n\n"  # SSE comment - ignored by the client, keeps the proxy warm

        errored = False
        if "err" in box:
            answer = f"[error calling {m.short}: {box['err'][:160]}]"
            final_cost, latency, errored = 0.0, 0, True
        else:
            live = box["live"]
            answer = live.get("answer") or "(no answer returned)"
            final_cost, latency = live["cost_usd"], live["latency_ms"]
            in_tok, out_tok = live["input_tokens"], live["output_tokens"]
        yield _sse({"type": "token", "text": answer, "costUsd": final_cost})
        # Real LLM-as-judge with the chosen judge model: score + one-line reason.
        if errored:
            judge, judge_reason = 0.0, ""
        else:
            judge, judge_reason = judge_module.score_and_reason(prompt, answer, judge_model)

    yield _sse({
        "type": "done", "answer": answer, "costUsd": final_cost, "latencyMs": latency,
        "judgeScore": judge, "judgeReason": judge_reason,
        "inputTokens": in_tok, "outputTokens": out_tok,
        "totalTokens": in_tok + out_tok,
        "context": _context(m, prompt, in_tok, out_tok),
        "error": errored or (demo is False and (answer.startswith("[error") or answer == "(no answer returned)")),
    })
