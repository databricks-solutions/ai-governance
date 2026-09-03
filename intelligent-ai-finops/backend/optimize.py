"""Prompt optimizer - sharpen a user's question before it fans out to the three
Compare lanes.

Live mode asks a capable model to rewrite the prompt (make the goal explicit,
add the implied output format/constraints, remove ambiguity) WITHOUT answering
it. Demo mode applies a deterministic structured rewrite so it runs offline.
The optimized prompt is what all three lanes then run on, so the LLM-as-judge
scores answers to the improved prompt.
"""
from __future__ import annotations

from . import models

_META = (
    "You are an expert prompt engineer. Rewrite the user's request into a single, "
    "sharper prompt that will get a better answer from an LLM: make the goal "
    "explicit, add the output format and any constraints that are clearly implied, "
    "and remove ambiguity. Preserve the user's intent EXACTLY - do not answer the "
    "request, do not invent facts or numbers, do not add scope the user didn't ask "
    "for. Return ONLY the rewritten prompt, with no preamble or quotation marks.\n\n"
    "User request:\n{prompt}"
)


def _demo_rewrite(p: str) -> str:
    """Deterministic offline rewrite - wraps the ask with explicit structure and
    output guidance so the improvement is visible without a network call."""
    core = p.strip().rstrip(".")
    return (
        f"{core}.\n\n"
        "Answer with structure: (1) state any assumptions you make, (2) show the "
        "key steps, trade-offs, or calculations, and (3) give the result in a clear "
        "format - use short labelled sections or a table where it helps. Be specific "
        "and concise, and call out the main risks or edge cases explicitly."
    )


def optimize_prompt(prompt: str, demo: bool = True, model_id: str | None = None) -> dict:
    """Return {optimized, changed, model?, note?}. Never raises - on any failure
    it falls back to the original prompt so the comparison still runs."""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"optimized": "", "changed": False}

    if demo:
        opt = _demo_rewrite(prompt)
        return {"optimized": opt, "changed": opt != prompt, "note": "demo rewrite (offline)"}

    try:
        m = models.by_id(model_id) if model_id else models.frontier_model()
    except KeyError:
        m = models.frontier_model()
    try:
        res = models.live_query(m, _META.format(prompt=prompt), max_tokens=800)
        opt = (res.get("answer") or "").strip().strip('"') or prompt
    except Exception as e:  # noqa: BLE001 - degrade gracefully, keep the original prompt
        return {"optimized": prompt, "changed": False, "note": f"optimizer unavailable: {str(e)[:120]}"}
    return {"optimized": opt, "changed": opt != prompt, "model": m.short}
