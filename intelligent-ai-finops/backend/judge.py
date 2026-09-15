"""LLM-as-judge scoring (§7).

One scoring call per lane, using a small model with a rubric prompt returning a
single 0–10 float. Judge runs are logged to MLflow (best-effort - a demo without
a tracking server still works). Judging is toggleable; when off the winner rule
falls back to the cheapest completing lane and the UI hides the judge column.

Demo mode never needs this module - per-lane scores are synthesised from the tier
profile. This is the live path.
"""
from __future__ import annotations

import json
import re

from . import models

JUDGE_MODEL_TIER = "frontier"  # judge with the strongest model available

_RUBRIC = (
    "You are an impartial expert evaluator. Score how well the answer addresses "
    "the question on a 1-10 scale (10 = correct, complete, clear; 1 = wrong or "
    "unhelpful). Judge quality only - ignore cost, speed, and length except where "
    "length hurts. Question:\n{prompt}\n\nAnswer:\n{answer}\n\n"
    'Respond with ONLY JSON: {{"score": <1-10>, "reason": "<ONE concise sentence, '
    'max 22 words, naming the specific strength or gap of THIS answer for THIS '
    'question>"}}.'
)


def score_and_reason(prompt: str, answer: str, model_id: str | None = None) -> tuple[float, str]:
    """Score one answer 0–10 AND return a one-sentence rationale, via the chosen
    judge model; log the run to MLflow. `model_id` selects the judge (the UI's
    'Judged by'); falls back to the cheapest frontier model when unset/unknown."""
    judge = None
    if model_id:
        try:
            judge = models.by_id(model_id)
        except KeyError:
            judge = None
    if judge is None:
        judge = models.cheapest_of_tier(JUDGE_MODEL_TIER)
    # Budget: the judge only needs a score + one short sentence, but some models
    # (e.g. kimi-k3) write a VERBOSE reason and, plain, spend the budget on hidden
    # thinking. `_reasoning_suppression` (in models.live_query) now keeps kimi/GLM/
    # DeepSeek terse, and 1200 tokens leaves headroom so the JSON closes on a long
    # answer instead of truncating mid-"reason". temperature=0.0 keeps it deterministic.
    result = models.live_query(judge, _RUBRIC.format(prompt=prompt, answer=answer), max_tokens=1200, temperature=0.0)
    text = result["answer"] or ""
    value, reason = _extract_score_reason(text)
    if value is None:
        # Couldn't determine a score at all - use a neutral midpoint (NOT 1.0, which
        # would wrongly crown or kill a lane in the winner rule) and surface it.
        value = 5.0
        reason = reason or "Judge response could not be parsed; neutral score applied."
    value = max(1.0, min(10.0, value))
    _log_to_mlflow(judge.id, prompt, answer, value, result["cost_usd"])
    return round(value, 1), reason


def _extract_score_reason(text: str) -> tuple[float | None, str]:
    """Pull (score, reason) from the judge's output, ROBUST to messy/truncated JSON.

    Reasoning/verbose models (kimi-k3) often overrun the token budget mid-answer, so
    the JSON never closes. The score is emitted first, so we recover it directly from
    the `"score":` key even when the closing brace (and the reason) are cut off -
    which is exactly the case that used to fall through to a bogus neutral 5.0 on
    every lane. Layered: (1) clean JSON, (2) score-key regex on unclosed JSON,
    (3) an explicit "Score: N" / "N/10" phrasing. A bare number anywhere is NOT
    accepted (it wrongly matched digits like "112%" inside the reason)."""
    t = (text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # 1) Clean JSON object.
    try:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            p = json.loads(t[i : j + 1])
            if p.get("score") is not None:
                return float(p["score"]), str(p.get("reason", "") or "").strip()
    except (ValueError, KeyError, TypeError):
        pass
    # 2) Truncation-proof: read the score straight off the "score" key, and the reason
    # up to the next quote (may be cut short - that's fine, we still have the score).
    ms = re.search(r'"score"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)', t)
    if ms:
        mr = re.search(r'"reason"\s*:\s*"([^"]*)', t)
        return float(ms.group(1)), (mr.group(1).strip() if mr else "")
    # 3) Free-text phrasing like "Score: 8" or "8/10".
    mp = re.search(r'(?:score\D{0,8}|rating\D{0,8})([0-9]{1,2}(?:\.[0-9])?)|\b([0-9]{1,2}(?:\.[0-9])?)\s*/\s*10', t, re.I)
    if mp:
        return float(mp.group(1) or mp.group(2)), ""
    return None, ""


def score(prompt: str, answer: str, model_id: str | None = None) -> float:
    """Back-compat: score only (the /api/judge endpoint)."""
    return score_and_reason(prompt, answer, model_id)[0]


def _log_to_mlflow(judge_model: str, prompt: str, answer: str, score_val: float, cost: float) -> None:
    """Best-effort MLflow logging - never breaks a request if tracking is absent."""
    try:
        import mlflow

        with mlflow.start_run(run_name="finops-judge", nested=True):
            mlflow.log_params({"judge_model": judge_model, "prompt_chars": len(prompt), "answer_chars": len(answer)})
            mlflow.log_metrics({"judge_score": score_val, "judge_cost_usd": cost})
    except Exception:  # noqa: BLE001 - logging is optional; scoring must not fail
        pass
