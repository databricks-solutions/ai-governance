"""V2 REAL inference proxy - the app becomes the gateway.

A caller points their OpenAI SDK at `<app>/v1/chat/completions` with
`model="finops-auto"`; this module classifies the prompt, routes it to the
CHEAPEST candidate model that clears the quality bar, enforces app-layer
guardrails + rate limits, compresses the request, serves it via Model Serving
with a fallback chain, and returns a normal OpenAI completion plus an `x_finops`
receipt (routed model, cost, savings). Passing a real serving-endpoint id as
`model` instead governs + passes the call through to that one endpoint.

This is the productized form of gateway.run: it reuses the SAME classifier,
policy resolver, guardrail scanner, rate limiter, compressor and fallback logic,
but returns an OpenAI response instead of the Pipeline-tab demo receipt. So a
customer can route production traffic through it, not just watch a simulation.
"""
from __future__ import annotations

import time
import uuid

from . import compare, compress, gateway, models, routing
from . import guardrails as _guard
from . import semcache as _sem
from .appconfig import load_config

# Virtual model ids that mean "let the router pick". Anything else is treated as
# a real endpoint id to govern + pass through.
AUTO_IDS = {"finops-auto", "finops-router", "auto", "router"}

_RANK = gateway._RANK
_TIER_LABEL = gateway._TIER_LABEL


class ProxyError(Exception):
    """A policy/serving failure the endpoint turns into an OpenAI-style error.
    `status` is the HTTP code (400 guardrail block, 429 rate limit, 404 unknown
    model, 502 all upstreams failed); `finops` carries whatever receipt we have."""

    def __init__(self, status: int, message: str, code: str, finops: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.finops = finops or {}


def _shape_directive(words: int) -> str:
    """Output-shaping system directive: costs ~20 input tokens, cuts output tokens
    (the priciest kind) by capping length and stripping preamble/restatement."""
    return (f"Answer directly and concisely. Do not restate the question or add preamble. "
            f"Use at most about {words} words; stop as soon as the answer is complete.")


def _text(content) -> str:
    """Coerce an OpenAI message `content` (string OR a list of content parts) to
    plain text, so classification/guardrails see the words regardless of shape."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content or "")


def _saved_policy() -> dict:
    """The admin's server-side router policy (candidates + bands + guardrails +
    fallback), persisted in Lakebase so `finops-auto` behaves the same across
    restarts/replicas. Empty when unset or Lakebase is unreachable."""
    from . import lakebase
    return lakebase.get("router_policy", max_age_s=10 ** 9) or {}


def effective_policy(options: dict | None) -> dict:
    """Merge the saved server-side policy with any per-request `finops` override
    (the override wins). Candidates default to the full curated registry."""
    base = _saved_policy()
    o = options or {}

    def pick(key, default=None):
        if o.get(key) is not None:
            return o[key]
        if base.get(key) is not None:
            return base[key]
        return default

    return {
        "models": pick("models", [m.id for m in models.registry()]),
        "bands": pick("bands"),
        "policy": pick("policy"),
        "routerModel": pick("routerModel"),
        "guardrails": pick("guardrails"),
        "rateLimit": pick("rateLimit"),
        "fallback": pick("fallback"),
        # Semantic cache defaults ON - it's the highest-leverage FinOps lever and the
        # per-request `finops` field or saved policy can turn it off / retune the threshold.
        "semanticCache": pick("semanticCache", {"enabled": True, "threshold": 0.92}),
        # Live budget: a monthly cap enforced against REAL month-to-date spend (not a
        # slider). {enabled, capUsd, downgradeAtPct, openOnlyAtPct, downgradeAction, openOnlyAction}.
        "budget": pick("budget"),
        # Output-shaping optimization: {enabled, targetWords}. Caps + de-fluffs the answer
        # to cut OUTPUT tokens. Off by default (opt-in); the A/B endpoint proves the net.
        "optimize": pick("optimize"),
    }


def _openai_response(served: models.Model, answer: str, in_tok: int, out_tok: int,
                     finish: str = "stop") -> dict:
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": served.id,  # the endpoint that ACTUALLY answered
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": finish,
        }],
        "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok,
                  "total_tokens": in_tok + out_tok},
    }


def serve(messages: list[dict], requested_model: str | None = None, options: dict | None = None,
          user: str | None = None, max_tokens: int | None = None,
          temperature: float | None = 0.0) -> tuple[dict, dict]:
    """Route + govern + serve one chat request. Returns (openai_response, finops).
    Raises ProxyError for a policy block / rate limit / unknown model / upstream
    failure so the endpoint can map it to the right HTTP status."""
    cfg = load_config()
    demo = cfg["demoMode"]
    pol = effective_policy(options)
    who = user or "proxy-user"
    is_auto = (not requested_model) or requested_model.lower() in AUTO_IDS

    # ---- Candidate set ---------------------------------------------------
    if not is_auto:
        try:
            candidates = [models.by_id(requested_model)]
        except KeyError:
            raise ProxyError(404, f"Unknown model '{requested_model}'. Use a registered serving "
                                  f"endpoint id or 'finops-auto' to let the router pick.", "unknown_model")
    else:
        candidates = []
        for mid in pol["models"] or []:
            try:
                candidates.append(models.by_id(mid))
            except KeyError:
                continue
        if not candidates:
            candidates = models.registry()

    # ---- Prompt text (last user turn, plus everything for classification) ----
    user_turns = [m for m in messages if m.get("role") == "user"]
    prompt = _text(user_turns[-1].get("content")) if user_turns else ""
    if not prompt.strip():
        raise ProxyError(400, "No user message content to route.", "empty_prompt")

    # ---- App-layer governance (enforced by the gateway itself) -----------
    # 1) Rate limit (per user / minute) - in-process sliding window.
    rl = pol.get("rateLimit") or {}
    if rl.get("enabled"):
        per_min = max(1, int(rl.get("perMin") or 60))
        allowed, count = gateway._rate_check(who, per_min)
        if not allowed:
            raise ProxyError(429, f"Rate limit reached: {per_min} requests/minute for '{who}'. "
                                  f"Refused by the gateway before any model was called.", "rate_limited",
                             {"rateLimit": {"perMin": per_min, "countInWindow": count}})
    # 2) Guardrails (PII + keyword): block, or mask the matches and proceed.
    guard_note = None
    gr = pol.get("guardrails") or {}
    if gr.get("enabled"):
        pii = gr.get("pii", True)
        kws = gr.get("keywords") or []
        findings = _guard.scan(prompt, pii=pii, keywords=kws)
        if findings:
            cats = ", ".join(sorted({f["category"] for f in findings}))
            if gr.get("mode", "block") == "block":
                raise ProxyError(400, f"Blocked by AI guardrails: detected {cats}. Refused by the "
                                      f"gateway before any model was called.", "guardrail_block",
                                 {"guardrail": {"action": "block", "categories": cats,
                                                "count": len(findings)}})
            masked, _ = _guard.mask(prompt, pii=pii, keywords=kws)
            prompt = masked
            guard_note = {"action": "mask", "categories": cats, "count": len(findings)}

    # ---- Semantic cache: serve a stored answer for an equivalent prompt --------
    # Embed the (post-guardrail) prompt once; if a semantically-equivalent prompt is
    # already cached above the similarity threshold, return its answer with NO model
    # call - the full re-answer cost is the saving. The embedding is reused to store
    # the answer on a miss, so we embed at most once per request.
    sc_cfg = pol.get("semanticCache") or {}
    # Demo mode must stay fully offline, so never embed / touch Lakebase there
    # (embed() is a real endpoint call and the durable tier is real DB round-trips).
    sc_on = bool(sc_cfg.get("enabled")) and not demo
    sc_emb = None
    if sc_on:
        t0 = time.monotonic()
        sc_emb = _sem.embed(prompt)
        hit = _sem.lookup(prompt, sc_cfg.get("threshold"), embedding=sc_emb) if sc_emb else None
        if hit:
            meta = hit["meta"]
            saved = float(meta.get("costUsd") or 0.0)
            _sem.note_hit(saved)
            tier = meta.get("servedTier", "small-oss")
            cached = dict(hit["response"])
            cached["id"] = "chatcmpl-" + uuid.uuid4().hex[:24]
            cached["created"] = int(time.time())
            finops = {
                "requestedModel": requested_model or "finops-auto",
                "mode": "auto" if is_auto else "passthrough",
                "cacheHit": True,
                "similarity": hit["similarity"],
                "cachedFrom": (hit["prompt"] or "")[:120],
                "routedTo": {"id": meta.get("servedId", ""), "short": meta.get("servedShort", "cache"), "tier": tier},
                "servedBy": {"id": "semantic-cache", "short": "semantic cache", "tier": tier},
                "complexity": meta.get("complexity", 0),
                "requiredTier": tier,
                "requiredTierLabel": _TIER_LABEL.get(tier, tier),
                "bandLabel": None, "matchedRule": None,
                "costUsd": 0.0,
                "baselineUsd": saved,
                "baselineModel": meta.get("servedShort", "cache"),
                "savingsUsd": saved,
                "savingsPct": 100.0 if saved > 0 else 0.0,
                "inputTokens": 0, "outputTokens": 0,
                "latencyMs": round((time.monotonic() - t0) * 1000),
                "candidates": [m.short for m in candidates],
                "guardrail": guard_note,
                "compression": None,
                "fallback": None,
                "demo": demo,
            }
            return cached, finops
        _sem.note_miss()

    # ---- Classify complexity + resolve the required tier -----------------
    # Manual override (Live Gateway "Manual" routing mode): the caller supplies a
    # 0-100 complexity, so skip the classifier and route on that number. Any other
    # value falls through to automatic classification (the default finops-auto path).
    cx_override = (options or {}).get("complexity")
    if isinstance(cx_override, (int, float)) and not isinstance(cx_override, bool) and 0 <= cx_override <= 100:
        cx = int(cx_override)
    else:
        router_model = pol.get("routerModel")
        if not demo and router_model:
            cx = gateway.classify_complexity(prompt, router_model)
        else:
            cx = routing.classify(prompt)

    in_est, out_est = models.demo_token_counts(prompt, cx)  # for cost pre-estimate + baseline
    base_req, band_label, matched_kw = gateway.resolve_policy(cx, prompt, pol.get("bands"), pol.get("policy"))

    # ---- Live budget: cap/block against REAL month-to-date spend --------------
    # Unlike the demo slider, this reads the actual last-30-day spend from the cached
    # system-tables overview and applies the admin's per-threshold action (cap the
    # ceiling tier, or block) automatically as real spend rises toward the cap.
    budget_info = None
    ceiling_rank = _RANK["frontier"]  # no cap by default
    bud = pol.get("budget") or {}
    if is_auto and bud.get("enabled") and bud.get("capUsd"):
        from . import costcache
        cap = float(bud["capUsd"])
        # A what-if `consumedPct` override drives the budget as if spend were at that
        # level - it keeps the interactive "slide spend up, watch routing tighten" demo
        # working even when real month-to-date spend is ~0. Without it, enforce against
        # REAL last-30-day spend from the cached system-tables overview.
        cx_override = bud.get("consumedPct")
        simulated = isinstance(cx_override, (int, float)) and not isinstance(cx_override, bool)
        if simulated:
            consumed_pct = max(0.0, min(100.0, float(cx_override)))
            mtd = cap * consumed_pct / 100.0
        else:
            mtd = costcache.spend_last_30d()
            consumed_pct = (min(100.0, mtd / cap * 100) if cap > 0 else 0.0) if mtd is not None else None
        if consumed_pct is not None:
            action, note = gateway._budget_ceiling(
                consumed_pct, bud.get("downgradeAtPct"), bud.get("openOnlyAtPct"),
                bud.get("downgradeAction"), bud.get("openOnlyAction"))
            if action == "block":
                raise ProxyError(429, f"Budget cap reached: ${mtd:,.0f} of ${cap:,.0f} 30-day cap "
                                      f"({consumed_pct:.0f}%). Request refused - no model called.",
                                 "budget_block",
                                 {"budget": {"mtdUsd": round(mtd, 2), "capUsd": cap,
                                             "consumedPct": round(consumed_pct, 1), "action": "block", "note": note}})
            if action in _RANK:
                ceiling_rank = _RANK[action]
            budget_info = {"mtdUsd": round(mtd, 2), "capUsd": cap, "consumedPct": round(consumed_pct, 1),
                           "ceiling": action, "note": note}

    # ---- Select the cheapest candidate that clears the bar (under any cap) -----
    def _cheapest(ms: list[models.Model]) -> models.Model:
        return min(ms, key=lambda m: m.cost_usd(in_est, out_est))

    if not is_auto:
        chosen = candidates[0]  # passthrough: govern the one endpoint the caller named
    else:
        base_rank = _RANK[base_req]
        target_rank = min(base_rank, ceiling_rank)  # budget only ever routes cheaper
        in_band = [m for m in candidates if target_rank <= _RANK[m.tier] <= ceiling_rank]
        under_cap = [m for m in candidates if _RANK[m.tier] <= ceiling_rank]
        if in_band:
            chosen = _cheapest(in_band)
        elif under_cap:  # can't clear the bar within budget → best affordable
            top = max(_RANK[m.tier] for m in under_cap)
            chosen = _cheapest([m for m in under_cap if _RANK[m.tier] == top])
        else:  # every pick is pricier than the cap → cheapest overall
            chosen = _cheapest(candidates)

    # ---- Compress the last user turn (real - the compressed text is sent) ----
    comp = compress.compress_prompt(prompt)
    send_messages = list(messages)
    if user_turns:
        # Rebuild with the compressed (and guardrail-masked) content on the last user turn.
        last_idx = max(i for i, m in enumerate(send_messages) if m.get("role") == "user")
        send_messages[last_idx] = {**send_messages[last_idx], "content": comp["compressed"] or prompt}

    # ---- Output-shaping optimization (opt-in) --------------------------------
    # The net-positive lever: a small system directive + a max_tokens cap that trims
    # OUTPUT tokens (priced ~4-5x input). Prove the net with the A/B endpoint.
    opt = pol.get("optimize") or {}
    opt_on = bool(opt.get("enabled"))
    opt_words = max(20, int(opt.get("targetWords") or 150))
    if opt_on:
        send_messages = [{"role": "system", "content": _shape_directive(opt_words)}] + send_messages

    # ---- Fallback chain (routed model first, then the admin's order) -----
    by_id = {m.id: m for m in candidates}
    fb_cfg = pol.get("fallback") or {}
    fb_on = bool(fb_cfg.get("enabled")) and is_auto
    fb_order = [i for i in (fb_cfg.get("order") or []) if i in by_id] if fb_on else []
    if fb_on and not fb_order:
        fb_order = [m.id for m in candidates]
    chain = [chosen] + [by_id[i] for i in fb_order if i != chosen.id] if fb_on else [chosen]

    # ---- Serve -----------------------------------------------------------
    served = chosen
    fb_fired = False
    fb_from = None
    ans_max = int(max_tokens) if max_tokens else compare._ANSWER_MAX_TOKENS
    if opt_on:
        # The directive is the primary lever (model self-limits + finishes cleanly);
        # the cap is a SAFETY ceiling with headroom (~3 tok/word) so a compliant answer
        # ends at finish=stop, not truncated. Continuation is disabled at serve time so
        # the cap can't be 3x'd.
        ans_max = min(ans_max, opt_words * 3)
    if demo:
        answer = compare._demo_answer(prompt)
        in_tok, out_tok = in_est, out_est
        latency = models.demo_latency_ms(chosen)
    else:
        last_err = None
        served_ok = False
        answer = ""
        in_tok = out_tok = latency = 0
        for idx, cand in enumerate(chain):
            try:
                live = models.live_chat(cand, send_messages, max_tokens=ans_max, temperature=temperature,
                                        continue_on_length=not opt_on)
                answer = live["answer"] or "(no answer returned)"
                in_tok, out_tok, latency = live["input_tokens"], live["output_tokens"], live["latency_ms"]
                served = cand
                if idx > 0:
                    fb_fired = True
                    fb_from = chosen.short
                served_ok = True
                break
            except Exception as e:  # noqa: BLE001 - try the next model in the chain
                last_err = e
                continue
        if not served_ok:
            raise ProxyError(502, f"All candidate endpoints failed. Last error: {str(last_err)[:180]}",
                             "upstream_error", {"routedTo": {"id": chosen.id, "short": chosen.short}})

    # ---- Cost / savings (vs the priciest candidate that was on the table) ----
    baseline = max(candidates, key=lambda m: m.cost_usd(in_tok, out_tok))
    cost = served.cost_usd(in_tok, out_tok)
    base_cost = baseline.cost_usd(in_tok, out_tok)
    savings = base_cost - cost
    savings_pct = round(savings / base_cost * 100, 1) if base_cost > 0 else 0.0

    finops = {
        "requestedModel": requested_model or "finops-auto",
        "mode": "auto" if is_auto else "passthrough",
        "cacheHit": False,
        "routedTo": {"id": chosen.id, "short": chosen.short, "tier": chosen.tier},
        "servedBy": {"id": served.id, "short": served.short, "tier": served.tier},
        "complexity": cx,
        "requiredTier": base_req,
        "requiredTierLabel": _TIER_LABEL.get(base_req, base_req),
        "bandLabel": band_label,
        "matchedRule": matched_kw,
        "costUsd": cost,
        "baselineUsd": base_cost,
        "baselineModel": baseline.short,
        "savingsUsd": savings,
        "savingsPct": savings_pct,
        "inputTokens": in_tok,
        "outputTokens": out_tok,
        "latencyMs": latency,
        "candidates": [m.short for m in candidates],
        "guardrail": guard_note,
        "compression": comp,
        "fallback": {
            "enabled": fb_on,
            "armed": [m.short for m in chain] if fb_on and len(chain) > 1 else [],
            "fired": fb_fired,
            "from": fb_from,
        } if fb_on else None,
        "budget": budget_info,
        "optimization": {
            "enabled": True, "mode": "shape", "targetWords": opt_words,
            "outputTokens": out_tok,
            "baselineOutputTokens": out_est,  # complexity-scaled expectation (unshaped)
            "savedOutputTokens": max(0, out_est - out_tok),
            "savedUsdEst": served.cost_usd(0, max(0, out_est - out_tok)),
        } if opt_on else None,
        "demo": demo,
    }
    resp = _openai_response(served, answer, in_tok, out_tok)
    # Store the served answer so a semantically-equivalent prompt is a hit next time.
    if sc_on and answer and not answer.startswith("[error"):
        _sem.put(prompt, resp, {
            "servedShort": served.short, "servedId": served.id, "servedTier": served.tier,
            "costUsd": cost, "inTok": in_tok, "outTok": out_tok, "complexity": cx,
        }, embedding=sc_emb)
    return resp, finops
