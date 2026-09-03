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
    # The judge only needs to emit two lines of JSON (a score + one sentence), so
    # its budget is capped tight. This matters for latency: the judge is a SECOND
    # live call on every lane (3 per Compare run), and on a reasoning judge the
    # token budget is the dominant cost - 600 is plenty for the JSON and keeps the
    # judge from thinking for tens of seconds per lane.
    # temperature=0.0 makes the judge deterministic - the same answer scores the
    # same way run-to-run, which is what makes the scoring feel consistent.
    result = models.live_query(judge, _RUBRIC.format(prompt=prompt, answer=answer), max_tokens=600, temperature=0.0)
    text = result["answer"] or ""
    value, reason = 0.0, ""
    try:
        i, j = text.find("{"), text.rfind("}")
        parsed = json.loads(text[i : j + 1])
        value = float(parsed.get("score", 0))
        reason = str(parsed.get("reason", "") or "").strip()
    except (ValueError, KeyError, TypeError):
        pass
    value = max(1.0, min(10.0, value))
    _log_to_mlflow(judge.id, prompt, answer, value, result["cost_usd"])
    return round(value, 1), reason


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
