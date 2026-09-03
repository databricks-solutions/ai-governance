"""The Unity AI Gateway box (Tab 2).

A question (predefined or free-text) enters the gateway; the customer picks 2-3
candidate models and ticks the governance features they want applied. The router
classifies the question's complexity and sends it to the CHEAPEST selected model
whose tier clears the bar (else the most capable one selected), then reports the
model, the cost, and how it routed - the $$$ story, over the customer's own set.

Deterministic by design (no random failover), so the routed model and cost are
predictable in front of a customer.
"""
from __future__ import annotations

import re

from . import compare, judge, models, routing

# Governance features shown as ticks in the box. `feature` maps to the config
# panel; `label` is display text; `category` colours the tick.
FEATURES = [
    {"id": "rate-limits", "label": "Rate limits", "feature": "rate-limits"},
    {"id": "guardrails", "label": "AI guardrails", "feature": "guardrails"},
    {"id": "budget", "label": "Budgets routing", "feature": "budgets"},
    {"id": "routing-policy", "label": "Complexity routing", "feature": "routing-policy"},
    {"id": "inference-tables", "label": "Inference tables", "feature": "inference-tables"},
]

_RANK = {"small-oss": 0, "large-oss": 1, "frontier": 2}
_VALID_TIERS = set(_RANK)
_TIER_LABEL = {"small-oss": "small OSS", "large-oss": "large OSS", "frontier": "frontier"}


def required_tier(complexity: int) -> str:
    th = routing.load_config()["policy"]["thresholds"]
    if complexity < th["small_max"]:
        return "small-oss"
    if complexity < th["large_max"]:
        return "large-oss"
    return "frontier"


# Words a customer might use in free-text criteria, mapped to a tier.
_TIER_WORDS = [
    ("small-oss", "small oss"), ("small-oss", "small"), ("small-oss", "simple"),
    ("small-oss", "cheap"), ("small-oss", "trivial"), ("small-oss", "basic"),
    ("large-oss", "large oss"), ("large-oss", "large"), ("large-oss", "medium"),
    ("large-oss", "standard"), ("large-oss", "mid"), ("large-oss", "moderate"),
    ("frontier", "frontier"), ("frontier", "complex"), ("frontier", "hard"),
    ("frontier", "flagship"), ("frontier", "premium"), ("frontier", "advanced"),
]
# Filler words dropped from the left (keyword) side of a criteria line.
_FILLER = {"route", "send", "put", "anything", "any", "about", "questions", "question",
           "prompts", "prompt", "the", "a", "an", "to", "for", "with", "that", "is", "are",
           "on", "of", "everything", "else", "otherwise", "default"}


def _tier_from_phrase(s: str) -> str | None:
    s = s.lower()
    for tier, word in _TIER_WORDS:
        if word in s:
            return tier
    return None


def parse_criteria(text: str | None) -> list[tuple[list[str], str]]:
    """Parse the customer's free-text routing criteria into (keywords, tier) rules.

    Handles lines like "code, sql -> small", "finance, valuation => complex",
    "route legal to frontier". The tier is inferred from tier words on the right
    (small/medium/complex, small oss/large oss/frontier, cheap/standard/flagship).
    Anything unparseable is skipped, so a prompt with no keyword match falls back
    to the complexity bands."""
    rules: list[tuple[list[str], str]] = []
    for raw in re.split(r"[\n;]+", text or ""):
        line = raw.strip()
        if not line:
            continue
        parts = re.split(r"->|=>|→|:", line, maxsplit=1)
        if len(parts) == 2:
            left, right = parts
        else:  # "route X to <tier>" - split on the LAST " to "
            m = list(re.finditer(r"\bto\b", line, re.I))
            if not m:
                continue
            left, right = line[: m[-1].start()], line[m[-1].end():]
        tier = _tier_from_phrase(right)
        if not tier:
            continue
        kws = []
        for phrase in re.split(r"[,/]|\band\b|\bor\b", left):
            # Strip leading/trailing filler words but keep multi-word phrases
            # like "credit card" intact.
            words = [w for w in re.split(r"\s+", phrase.strip().lower()) if w]
            while words and words[0] in _FILLER:
                words.pop(0)
            while words and words[-1] in _FILLER:
                words.pop()
            k = " ".join(words)
            if k and k not in _FILLER:
                kws.append(k)
        if kws:
            rules.append((kws, tier))
    return rules


def resolve_policy(cx: int, prompt: str | None, bands: list[dict] | None,
                   policy: dict | None) -> tuple[str, str | None, str | None]:
    """Resolve the required tier from the customer's OWN routing policy.

    Two policy modes (see the Routing policy Configure panel):
      - "criteria": free-text rules ("code -> small", "finance -> complex") are
        parsed to keyword→tier; a matching keyword forces that tier, regardless
        of the complexity score.
      - "bands" (default): the complexity score falls into a user-defined band.
    With no user policy at all, the default config thresholds apply.
    Returns (tier, label, matched_keyword)."""
    policy = policy or {}
    mode = policy.get("mode")
    clean = [b for b in (bands or []) if b.get("tier") in _VALID_TIERS]

    # 1) criteria mode: a keyword rule wins over the score. Prefer structured
    # rules ([{keywords, tier}]) from the row editor; fall back to parsing free text.
    if mode == "criteria" and prompt:
        low = prompt.lower()
        rules = policy.get("rules")
        if rules:
            parsed = []
            for r in rules:
                tier = r.get("tier")
                if tier not in _VALID_TIERS:
                    continue
                kws = [k.strip().lower() for k in re.split(r"[,/]", r.get("keywords") or "") if k.strip()]
                if kws:
                    parsed.append((kws, tier))
        else:
            parsed = parse_criteria(policy.get("text"))
        for kws, tier in parsed:
            for kw in kws:
                if kw and kw in low:
                    return tier, f'criteria "{kw}"', kw

    # 2) score falls into a band
    if clean:
        for b in sorted(clean, key=lambda x: x.get("min", 0)):
            if b.get("min", 0) <= cx <= b.get("max", 100):
                return b["tier"], b.get("label"), None
        top = max(clean, key=lambda x: x.get("max", 100))  # above all bands → the top one
        return top["tier"], top.get("label"), None

    # 3) default policy thresholds
    return required_tier(cx), None, None


def _action_label(action: str) -> str:
    """Human phrase for a budget action (a tier cap, or a hard block)."""
    if action == "block":
        return "block new requests"
    return f"cap at {_TIER_LABEL.get(action, action)}"


def _budget_ceiling(consumed_pct: float, downgrade_at: float | None = None,
                    open_only_at: float | None = None,
                    downgrade_action: str | None = None,
                    open_only_action: str | None = None) -> tuple[str, str]:
    """Budget pressure applies a customer-defined ACTION as spend rises. Each of
    the two thresholds carries its own action: cap the ceiling at a chosen tier,
    or 'block' new requests entirely. Returns (action, note) where action is a
    tier id OR the literal 'block'. Defaults preserve the old behaviour (downgrade
    → large-OSS, open-only → small-OSS)."""
    b = routing.load_config()["policy"]["budget"]
    downgrade_at = downgrade_at if downgrade_at is not None else b.get("downgrade_at_pct", 55)
    open_only_at = open_only_at if open_only_at is not None else b.get("open_only_at_pct", 80)
    dg = downgrade_action if downgrade_action in (*_VALID_TIERS, "block") else "large-oss"
    oo = open_only_action if open_only_action in (*_VALID_TIERS, "block") else "small-oss"
    # Higher threshold wins first.
    if consumed_pct >= open_only_at:
        return oo, f"Budget {consumed_pct:.0f}% consumed (≥{open_only_at}%) - {_action_label(oo)}."
    if consumed_pct >= downgrade_at:
        return dg, f"Budget {consumed_pct:.0f}% consumed (≥{downgrade_at}%) - {_action_label(dg)}."
    return "frontier", ""


def run(selected_ids: list[str], features: list[str], complexity: int | None = None,
        prompt: str | None = None, budget: dict | None = None,
        bands: list[dict] | None = None, policy: dict | None = None,
        demo: bool = True) -> dict:
    """Route the question over the customer's selected models.

    The customer's OWN routing policy (see resolve_policy) is either user-defined
    complexity `bands` OR free-text criteria in `policy` ({"mode": "criteria",
    "text": ...}). When absent the default config thresholds apply.

    When `budget` is applied ({"applied": True, "consumedPct": float, "capUsd": ...,
    "downgradeAction", "openOnlyAction"}) the customer's per-threshold action fires
    as spend rises - cap the ceiling at a chosen tier, or block new requests. Model
    selection is otherwise unchanged: still the cheapest selected model that clears
    the (eased) bar."""
    sel: list[models.Model] = []
    for mid in selected_ids:
        try:
            sel.append(models.by_id(mid))
        except KeyError:
            pass
    if not sel:
        return {"error": "Pick at least one model for the gateway."}

    cx = complexity if complexity is not None else routing.classify(prompt or "")
    # Token counts scale with the prompt (input) and complexity (output) - same
    # basis as the Compare tab, so per-query costs line up across the two tabs
    # (instead of a fixed illustrative request size).
    in_tok, out_tok = models.demo_token_counts(prompt, cx)

    def _cheapest(ms: list[models.Model]) -> models.Model:
        return min(ms, key=lambda m: m.cost_usd(in_tok, out_tok))

    # The add-on cost of the small LLM that classifies (routes) the prompt - shown
    # so the story is "even after paying the router, routing cheaper still wins".
    routing_overhead, router_short = models.router_overhead_usd(prompt)

    base_req, band_label, matched_kw = resolve_policy(cx, prompt, bands, policy)
    base_rank = _RANK[base_req]

    # How the policy landed on the required tier - reused in the reason + trace.
    if matched_kw:
        policy_desc = f"Criteria matched '{matched_kw}' → {_TIER_LABEL[base_req]}"
    elif band_label:
        policy_desc = f"Complexity {cx} in the {band_label} band → {_TIER_LABEL[base_req]}"
    else:
        policy_desc = f"Complexity {cx} → {_TIER_LABEL[base_req]}"

    budget_applied = bool(budget and budget.get("applied"))
    consumed_pct = float(budget.get("consumedPct", 0.0)) if budget_applied else 0.0
    dg_pct = budget.get("downgradeAtPct") if budget_applied else None
    oo_pct = budget.get("openOnlyAtPct") if budget_applied else None
    dg_action = budget.get("downgradeAction") if budget_applied else None
    oo_action = budget.get("openOnlyAction") if budget_applied else None
    frontier_bar = min(95, round(55 + 40 * (consumed_pct / 100))) if budget_applied else None
    action, budget_note = _budget_ceiling(consumed_pct, dg_pct, oo_pct, dg_action, oo_action) if budget_applied else ("frontier", "")

    # A 'block' action refuses the request entirely - no model is called.
    if budget_applied and action == "block":
        feat_labels = {f["id"]: f["label"] for f in FEATURES}
        trace = [{"kind": "feature", "text": f"{feat_labels[fid]} applied at the gateway"}
                 for fid in features if fid in feat_labels]
        band_txt = f" ({band_label} band)" if band_label and not matched_kw else ""
        trace.append({"kind": "route", "text": f"Classified complexity {cx}{band_txt} → needs {_TIER_LABEL[base_req]}"})
        trace.append({"kind": "route", "text": budget_note})
        trace.append({"kind": "serve", "text": "Request refused - no model called, no spend incurred."})
        return {
            "blocked": True,
            "complexity": cx,
            "bandLabel": band_label,
            "matchedRule": matched_kw,
            "requiredTier": base_req,
            "reason": (f"{policy_desc}, but {budget_note.rstrip('.').lower()}. New gateway "
                       f"requests are refused by your budget policy until spend resets."),
            "appliedFeatures": [f for f in features if f in feat_labels],
            "budget": {
                "applied": True, "consumedPct": consumed_pct,
                "capUsd": (budget or {}).get("capUsd"),
                "frontierBarPct": frontier_bar, "downgraded": True,
                "blocked": True, "note": budget_note,
            },
            "trace": trace,
        }

    ceiling = action if action in _VALID_TIERS else "frontier"
    ceiling_rank = _RANK[ceiling]

    # Route to the CHEAPEST selected model that clears the complexity bar, but
    # never above the budget ceiling. Budget only ever routes CHEAPER - with no
    # budget the ceiling is 'frontier', so this is exactly cheapest-sufficient
    # (consistent with the app's thesis; enabling a budget never costs more).
    target_rank = min(base_rank, ceiling_rank)
    in_band = [m for m in sel if target_rank <= _RANK[m.tier] <= ceiling_rank]
    under_cap = [m for m in sel if _RANK[m.tier] <= ceiling_rank]

    if in_band:
        chosen = _cheapest(in_band)
    elif under_cap:
        # Can't clear the quality bar within budget → best (most capable) affordable.
        top = max(_RANK[m.tier] for m in under_cap)
        chosen = _cheapest([m for m in under_cap if _RANK[m.tier] == top])
    else:
        chosen = _cheapest(sel)  # every pick is pricier than the cap

    budget_changed = budget_applied and _RANK[chosen.tier] < base_rank
    if budget_applied and not under_cap:
        budget_note += " · none of your picks are at/under the cap"
        reason = (
            f"{policy_desc}, but the budget is {consumed_pct:.0f}% consumed and every model you selected is "
            f"pricier than the {_TIER_LABEL[ceiling]} cap - routed to the cheapest you picked ({chosen.short}). "
            f"Add a large- or small-OSS model to route cheaper."
        )
    elif budget_changed:
        reason = (
            f"{policy_desc}, but the budget is {consumed_pct:.0f}% consumed - capped at {_TIER_LABEL[ceiling]} "
            f"and routed to {chosen.short}, the cheapest that fits."
        )
    elif _RANK[chosen.tier] >= base_rank:
        reason = (
            f"{policy_desc} - routed to {chosen.short}, the cheapest of your models that clears the bar."
        )
        if budget_applied and action == "frontier":
            reason += (
                f" Budget is {consumed_pct:.0f}% consumed, below your cap thresholds, so budget didn't "
                f"tighten routing (raise Consumed % or lower a threshold to see the cap engage)."
            )
    else:
        reason = (
            f"{policy_desc}, but none of your picks reaches it - routed to {chosen.short}, "
            f"the most capable you selected."
        )
    req = chosen.tier

    # Produce the actual answer + a quality score for the Result panel. Live mode
    # calls the chosen model (real answer/tokens/latency + a real LLM-as-judge);
    # demo mode synthesises so it runs offline. Token counts feed the cost below.
    if demo:
        answer = compare._demo_answer(prompt or "")
        judge_score = models.demo_judge(chosen)
        judge_reason = compare._demo_judge_reason(judge_score)
        latency = models.demo_latency_ms(chosen)
    else:
        try:
            live = models.live_query(chosen, prompt or "",
                                     max_tokens=compare._ANSWER_MAX_TOKENS, system=compare._ANSWER_SYSTEM,
                                     temperature=0.0)
            answer = live["answer"] or "(no answer returned)"
            in_tok, out_tok, latency = live["input_tokens"], live["output_tokens"], live["latency_ms"]
            judge_score, judge_reason = judge.score_and_reason(prompt or "", answer)
        except Exception as e:  # noqa: BLE001 - degrade to a visible error, never hang
            answer = f"[error calling {chosen.short}: {str(e)[:160]}]"
            judge_score, judge_reason, latency = 0.0, "", 0

    baseline = max(sel, key=lambda m: m.cost_usd(in_tok, out_tok))
    cost = chosen.cost_usd(in_tok, out_tok)
    base_cost = baseline.cost_usd(in_tok, out_tok)
    savings = base_cost - cost
    savings_pct = round(savings / base_cost * 100, 1) if base_cost > 0 else 0.0

    # A short, honest trace: governance ticks first, then classify → route → serve.
    feat_labels = {f["id"]: f["label"] for f in FEATURES}
    trace: list[dict] = []
    for fid in features:
        if fid in feat_labels:
            trace.append({"kind": "feature", "text": f"{feat_labels[fid]} applied at the gateway"})
    if matched_kw:
        trace.append({"kind": "route", "text": f"Router (small LLM) matched criteria '{matched_kw}' → needs {_TIER_LABEL[base_req]}"})
    else:
        band_txt = f" ({band_label} band)" if band_label else ""
        trace.append({"kind": "route", "text": f"Router (small LLM) scored complexity {cx}{band_txt} → needs {_TIER_LABEL[base_req]}"})
    if budget_applied and budget_note:
        trace.append({"kind": "route", "text": budget_note})
    elif budget_applied:
        trace.append({"kind": "route", "text": f"Budget {consumed_pct:.0f}% consumed - below your cap thresholds, no downgrade (all tiers available)"})
    trace.append({"kind": "route", "text": f"Routed to {chosen.short} ({_TIER_LABEL[chosen.tier]})"})
    trace.append({"kind": "serve", "text": f"Served via Model Serving · {latency} ms"})

    return {
        "chosen": {"id": chosen.id, "short": chosen.short, "tier": chosen.tier},
        "costUsd": cost,
        "latencyMs": latency,
        "judgeScore": judge_score,
        "judgeReason": judge_reason,
        "answer": answer,
        "inputTokens": in_tok,
        "outputTokens": out_tok,
        "complexity": cx,
        "bandLabel": band_label,
        "matchedRule": matched_kw,
        "requiredTier": req,
        "baseRequiredTier": base_req,
        "reason": reason,
        "baseline": {"short": baseline.short, "costUsd": base_cost},
        "savingsUsd": savings,
        "savingsPct": savings_pct,
        # The small-LLM router add-on, and the all-in cost (routed + router). Even
        # after paying the router, the all-in stays far under the frontier baseline.
        "routingOverheadUsd": routing_overhead,
        "routerModel": router_short,
        "allInCostUsd": cost + routing_overhead,
        "cheaperThanBaselineX": round(base_cost / (cost + routing_overhead), 1) if (cost + routing_overhead) > 0 else None,
        "appliedFeatures": [f for f in features if f in feat_labels],
        "budget": {
            "applied": budget_applied,
            "consumedPct": consumed_pct,
            "capUsd": (budget or {}).get("capUsd"),
            "frontierBarPct": frontier_bar,
            "downgraded": budget_changed,
            "note": budget_note,
        } if budget_applied else None,
        "trace": trace,
    }
