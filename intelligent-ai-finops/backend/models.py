"""Model registry + invocation.

Registry (id, short, tier, prices) is loaded from config/models.yaml - never
hardcoded (§4). Demo timing/quality characteristics per model live here (they are
demo-only, not part of the price rate card). Live invocation goes through
Databricks Model Serving; demo mode synthesises realistic numbers so the app
works on venue wifi (§7).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .appconfig import load_config

# Per-tier demo characteristics: (latency_ms_lo, hi), (judge_lo, hi), words/min.
# Frontier is slow/expensive/best; small OSS is fast/cheap/good-enough.
_TIER_PROFILE = {
    "frontier": {"ms": (2400, 5200), "judge": (8.5, 9.4), "wpm": 175},
    "large-oss": {"ms": (1200, 2400), "judge": (8.1, 9.0), "wpm": 280},
    "small-oss": {"ms": (400, 1200), "judge": (7.4, 8.7), "wpm": 400},
}

# Tier ordering for downgrades/fallbacks (0 = most capable/expensive).
TIER_ORDER = ["frontier", "large-oss", "small-oss"]


@dataclass(frozen=True)
class Model:
    id: str
    short: str
    tier: str
    dbu_in_per_1m: float   # official FMAPI DBU rate card (input, per 1M tokens)
    dbu_out_per_1m: float  # official FMAPI DBU rate card (output, per 1M tokens)

    def _d2u(self) -> float:
        return load_config()["dbuToUsd"]  # $ per DBU (real list/negotiated rate)

    @property
    def price_in_per_1m(self) -> float:
        return self.dbu_in_per_1m * self._d2u()

    @property
    def price_out_per_1m(self) -> float:
        return self.dbu_out_per_1m * self._d2u()

    def cost_usd(self, in_tok: int, out_tok: int) -> float:
        d2u = self._d2u()
        return (in_tok / 1e6) * self.dbu_in_per_1m * d2u + (out_tok / 1e6) * self.dbu_out_per_1m * d2u

    @property
    def profile(self) -> dict:
        return _TIER_PROFILE[self.tier]


# ---- shared demo token estimation (used by compare.py + gateway.py) ---------
_CHARS_PER_TOK = 4
SYS_OVERHEAD_TOK = 40  # system prompt / chat scaffolding overhead


def est_tokens(text: str) -> int:
    """Rough token estimate for demo-mode cost (chars / 4)."""
    return max(1, round(len(text or "") / _CHARS_PER_TOK))


def demo_token_counts(prompt: str | None, complexity: int) -> tuple[int, int]:
    """Illustrative (input, output) token counts for demo-mode cost. Input scales
    with the actual prompt length (same formula as the Compare tab, so the two
    tabs line up); output grows with complexity - a harder question warrants a
    longer answer (~120 tokens simple → ~600 complex)."""
    in_tok = SYS_OVERHEAD_TOK + est_tokens(prompt or "")
    out_tok = round(120 + (max(0, min(100, complexity)) / 100) * 480)
    return in_tok, out_tok


def router_overhead_usd(prompt: str | None, include_optimizer: bool = False,
                        model_id: str | None = None) -> tuple[float, str]:
    """The add-on cost of the SMALL LLM that does the routing (and, optionally,
    the prompt optimization) - so the demo can show that even after paying for
    the router/optimizer, routing to a cheaper model still costs far less than
    always calling the frontier. Priced on the chosen routing model (defaults to
    the cheapest small-OSS). Returns (cost_usd, router_short)."""
    r = None
    if model_id:
        try:
            r = by_id(model_id)
        except KeyError:
            r = None
    if r is None:
        r = cheapest_of_tier("small-oss")
    in_tok = SYS_OVERHEAD_TOK + est_tokens(prompt or "")
    # Classifier reads the prompt and emits a tiny score (~a few tokens).
    cost = r.cost_usd(in_tok, 8)
    if include_optimizer:
        # Optimizer reads the prompt and emits a rewrite of similar length.
        cost += r.cost_usd(in_tok, max(1, in_tok - SYS_OVERHEAD_TOK))
    return cost, r.short


def registry() -> list[Model]:
    """Curated models from config/models.yaml - every one carries a real
    published FMAPI DBU rate card (no illustrative prices, no auto-discovery of
    unpriced endpoints)."""
    return [Model(**m) for m in load_config()["models"]]


def registry_dicts() -> list[dict]:
    """Serialised registry for /api/config - DBU rates plus the computed $/1M."""
    d2u = load_config()["dbuToUsd"]
    return [
        {
            "id": m.id, "short": m.short, "tier": m.tier,
            "dbu_in_per_1m": m.dbu_in_per_1m, "dbu_out_per_1m": m.dbu_out_per_1m,
            "price_in_per_1m": round(m.dbu_in_per_1m * d2u, 4),
            "price_out_per_1m": round(m.dbu_out_per_1m * d2u, 4),
        }
        for m in registry()
    ]


def by_id(model_id: str) -> Model:
    for m in registry():
        if m.id == model_id:
            return m
    raise KeyError(model_id)


def cheapest_of_tier(tier: str) -> Model:
    """The cheapest model in a tier - the router picks this once it lands a tier."""
    tier_models = [m for m in registry() if m.tier == tier]
    if not tier_models:  # fall back to any model if a tier is unconfigured
        tier_models = registry()
    return min(tier_models, key=lambda m: m.price_out_per_1m)


def frontier_model() -> Model:
    return cheapest_of_tier("frontier")


# ---- demo timing helpers ------------------------------------------------
def demo_latency_ms(m: Model) -> int:
    lo, hi = m.profile["ms"]
    return round(random.uniform(lo, hi))


def demo_judge(m: Model) -> float:
    lo, hi = m.profile["judge"]
    return round(random.uniform(lo, hi), 1)


class GuardrailBlocked(Exception):
    """Raised when a serving endpoint's AI Gateway INPUT guardrail (safety/PII)
    rejects the prompt before the model runs (HTTP 400, finishReason=
    input_guardrail_triggered). Not retryable and not our bug - surfaced to the UI
    as a clear per-lane reason (often a false positive) instead of a generic error,
    so one guarded endpoint never turns into an endless retry loop."""


# ---- live invocation ----------------------------------------------------
# Reasoning models spend most of their latency (and token budget) on hidden
# thinking tokens, so max_tokens directly drives BOTH how slow a call is AND
# whether it truncates: too high = slow, too low = the thinking eats the whole
# budget and no answer block is emitted. Callers pass an explicit budget tuned
# for the surface (Compare answer / judge / optimizer); this default is a
# conservative fallback for any other caller.
_MAX_TOKENS = 1500


def _extract_answer(content) -> str:
    """Normalise string-or-blocks content into the final answer text.

    Reasoning models return a list of blocks; the answer is the text block(s).
    If the model hit the token limit before emitting a text block (all budget
    spent thinking), fall back to the reasoning summary so the UI shows
    something useful and the truncation is explicit, not an empty box."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()
    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
    if texts:
        return "\n".join(texts).strip()
    # Reasoning-only (truncated): the model used its entire max_tokens budget on
    # thinking and never emitted a final answer block. Surface the reasoning
    # summary and say so, rather than showing an empty box.
    summary: list[str] = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "reasoning":
            for s in (b.get("summary") or []):
                if isinstance(s, dict) and s.get("text"):
                    summary.append(s["text"])
    if summary:
        return ("[Truncated - this reasoning model used its whole token budget thinking and "
                "never emitted a final answer. Raise max_tokens or pick a faster model.]\n\n"
                + "\n".join(summary))
    return ""


def _reasoning_suppression(model_id: str) -> dict:
    """Family-specific request field that stops a REASONING model from spending
    its whole `max_tokens` budget on hidden thinking - which returns an EMPTY
    answer (reasoning-only, no text block) and takes far longer.

    Verified live on Databricks FMAPI (2026-09):
      - Claude (opus/sonnet/fable): `thinking={"type":"disabled"}` - only 'disabled'
        is accepted (bounded budgets and 'enabled' are rejected for opus-5).
      - OpenAI family (gpt-*) AND Kimi/GLM/DeepSeek flagships: `reasoning_effort="low"`.
        Kimi-K3 verified live: plain calls spend ~2x the tokens on verbose thinking
        and can overrun a tight budget (breaking the JSON judge); `reasoning_effort=low`
        keeps it terse and clean. `thinking` is Anthropic-only.
    Everything else (gemini/llama/qwen/gemma) gets nothing. If a param turns out
    unsupported the caller retries without it (see live_query), so listing an extra
    family here is safe - a model that rejects the knob just gets a clean retry."""
    mid = model_id.lower()
    if "claude" in mid:
        return {"thinking": {"type": "disabled"}}
    if any(k in mid for k in ("gpt", "kimi", "glm", "deepseek")):
        return {"reasoning_effort": "low"}
    return {}


def live_query(m: Model, prompt: str, max_tokens: int = _MAX_TOKENS, system: str | None = None,
               temperature: float | None = None) -> dict:
    """Call a real serving endpoint. Returns answer + token usage + latency.

    Posts directly to the endpoint's /invocations so we can pass the per-family
    reasoning-suppression field (see _reasoning_suppression) - without it a
    reasoning model (opus-5, gpt-oss, the opus judge) burns the entire token
    budget thinking and returns no answer. `system` prepends a system message
    (Compare uses it to ask for a complete-but-concise answer that finishes inside
    the token budget instead of truncating). `temperature` (when set) makes the
    call deterministic - passed as 0.0 for both answers and the LLM-as-judge so
    scores are stable run-to-run instead of drifting with the endpoint default.
    Imported lazily so demo mode never needs the SDK/credentials. On a 400 that
    rejects an optional knob (reasoning field OR temperature - some reasoning
    models only allow the default temperature), retry once without those optional
    knobs so an unexpected model family still returns.

    ROBUST COMPLETION: a fixed max_tokens ceiling truncates a long multi-part
    answer (e.g. the M&A prompt) mid-thought - the model stops with
    finish_reason == "length" before the last requested parts. To make the result
    robust regardless of how verbose a model is, when a response is cut for length
    we ask the model to continue from where it left off and stitch the parts
    together, up to a few rounds. With a generous budget this almost never fires,
    but it guarantees the final parts (recommendation, risks) are never lost."""
    convo = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return _run_chat(m, convo, max_tokens, temperature)


def live_chat(m: Model, messages: list[dict], max_tokens: int = _MAX_TOKENS,
              temperature: float | None = None, continue_on_length: bool = True) -> dict:
    """Proxy path: serve a full OpenAI-style `messages` array (multi-turn, with an
    optional system message) rather than a single prompt string. Reuses the exact
    same reasoning-suppression + 400-retry + length-continuation machinery as
    live_query (see _run_chat), so a call routed through the /v1/chat/completions
    proxy behaves identically to a Compare lane. Returns answer + token usage +
    latency + cost. `continue_on_length=False` disables the continuation rounds so a
    deliberate output cap (output-shaping) actually bites instead of being 3x'd."""
    return _run_chat(m, list(messages), max_tokens, temperature, continue_on_length)


def _run_chat(m: Model, convo: list[dict], max_tokens: int, temperature: float | None,
              continue_on_length: bool = True) -> dict:
    """Shared serving core for live_query (prompt) and live_chat (messages): POST to
    the endpoint's /invocations with per-family reasoning suppression, retry once
    without an optional knob a family rejects (400), and continue a length-truncated
    answer across a few rounds. Single source of truth for how a real model call is
    made, so both the Compare path and the proxy path stay consistent."""
    import time

    import requests
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    host = w.config.host.rstrip("/")
    auth = w.config.authenticate()  # {"Authorization": "Bearer <token>"}
    url = f"{host}/serving-endpoints/{m.id}/invocations"
    reasoning = _reasoning_suppression(m.id)

    # Transient statuses worth a retry (endpoint briefly overloaded / cold / gateway hiccup).
    _TRANSIENT = {429, 500, 502, 503, 504}

    def _post(body: dict):
        """POST with a generous timeout + transient retry so a slow (long multi-part
        answer) or briefly-overloaded endpoint doesn't fail the whole call. 240s covers
        a verbose completion; 2 retries with backoff ride out a 429/5xx or a connection
        blip. Non-transient statuses (incl. 400) return immediately for the caller's
        knob-drop / guardrail handling."""
        last_exc = None
        for attempt in range(3):  # 1 try + 2 retries
            try:
                r = requests.post(url, headers=auth, json=body, timeout=240)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exc = e
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
            if r.status_code in _TRANSIENT and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return r
        raise last_exc  # pragma: no cover - loop either returns or raises above

    def _one(msgs: list[dict]) -> dict:
        body = {"messages": msgs, "max_tokens": max_tokens}
        if temperature is not None:
            body["temperature"] = temperature
        body.update(reasoning)
        resp = _post(body)
        # Many reasoning models (e.g. claude-opus-5) reject a non-default `temperature`
        # with a 400 whose message does NOT reliably name the parameter (it can come back
        # conflated with a guardrail/other message). So on ANY 400, drop temperature and
        # retry - it's an optional tuning knob, always safe to omit - keeping the faster
        # `thinking:disabled`/`reasoning_effort` suppression in place.
        if resp.status_code == 400 and "temperature" in body:
            body.pop("temperature", None)
            resp = _post(body)
        # If it STILL 400s because the family rejects the reasoning knob, drop that too.
        if resp.status_code == 400 and any(k in resp.text for k in ("thinking", "reasoning_effort")):
            for k in ("thinking", "reasoning_effort"):
                body.pop(k, None)
            resp = _post(body)
        # A 400 from the endpoint's INPUT GUARDRAIL (safety/PII) is not retryable and not
        # our bug: the platform flagged the prompt before the model ran (often a false
        # positive on a benign business prompt). Surface a clear, human reason so the lane
        # explains itself and the comparison moves on gracefully - never an endless retry.
        low = resp.text.lower()
        if resp.status_code == 400 and ("input_guardrail" in low or "guardrail" in low):
            raise GuardrailBlocked(
                f"{m.short}: the prompt was blocked by this endpoint's safety/PII guardrail before "
                f"the model ran (input flagged - often a false positive). Pick another model, or "
                f"remove the guardrail on this endpoint."
            )
        resp.raise_for_status()
        return resp.json()

    _CONTINUE = ("Continue exactly where you left off. Do not repeat anything already "
                 "written; finish the remaining parts and end cleanly.")
    convo = list(convo)
    parts: list[str] = []
    in_tok = out_tok = latency = 0
    max_rounds = 3
    for r in range(max_rounds):
        start = time.monotonic()
        data = _one(convo)
        latency += round((time.monotonic() - start) * 1000)
        choice = data["choices"][0]
        part = _extract_answer(choice["message"]["content"])
        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        if r == 0:
            in_tok = usage.get("prompt_tokens") or 0  # real input, counted once
        out_tok += usage.get("completion_tokens") or 0
        if part:
            parts.append(part)
        # Stop when the model finished naturally, returned nothing, hit the cap, or
        # when continuation is disabled (a deliberate output cap must not be 3x'd).
        if finish != "length" or not part or r == max_rounds - 1 or not continue_on_length:
            break
        convo = convo + [{"role": "assistant", "content": part},
                         {"role": "user", "content": _CONTINUE}]

    # Join continuation rounds with a space so the last word of one round and the
    # first of the next don't fuse ("...plan.The main..."). Single-round answers
    # (the common case) are unaffected.
    answer = " ".join(parts).strip()
    return {
        "answer": answer,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "latency_ms": latency,
        "cost_usd": m.cost_usd(in_tok, out_tok),
    }
