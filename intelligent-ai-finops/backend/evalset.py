"""Bring-your-own evaluation set - validate Smart Routing holds quality on YOUR prompts.

A customer pastes a handful of prompts representative of their workload; we run each
one BOTH through the router (finops-auto, cheapest-sufficient) and through a fixed
frontier flagship, judge both answers with the same LLM-as-judge, and aggregate:
average routed quality vs frontier quality (the retention), and the cost saved. That
answers the question every FinOps buyer asks - "does routing keep quality for MY
domain, and how much does it save?" - measured, not asserted.

Prompts run CONCURRENTLY, and within each row the routed vs frontier generations run
in parallel and the two judge calls run in parallel, so a row costs ~2 sequential LLM
round-trips (one generation + one judge) instead of the naive six. The batch wall-time
stays near a single prompt's, well under the Databricks Apps request timeout. Capped at
MAX_PROMPTS. Best-effort MLflow logging of the aggregate metrics; degrades
cleanly (logged:false) if MLflow/experiment access isn't available.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import judge as judge_mod
from . import models as reg
from . import proxy

MAX_PROMPTS = 6


def _quality(prompt: str, answer: str, judge_model: str | None) -> float | None:
    try:
        v, reason = judge_mod.score_and_reason(prompt, answer, model_id=judge_model)
        return None if "could not be parsed" in (reason or "") else v
    except Exception:  # noqa: BLE001
        return None


def run_eval(prompts: list[str], candidates: list[str] | None = None,
             frontier: str | None = None, judge_model: str | None = None,
             user: str = "eval") -> dict:
    """Run each prompt through the router vs a frontier baseline; judge both; aggregate."""
    prompts = [p.strip() for p in (prompts or []) if p and p.strip()][:MAX_PROMPTS]
    if not prompts:
        return {"error": "Provide at least one prompt."}
    if not frontier:
        fr = [m for m in reg.registry() if m.tier == "frontier"]
        frontier = (max(fr, key=lambda m: m.price_out_per_1m).id if fr else reg.frontier_model().id)
    base = {"semanticCache": {"enabled": False}}
    on_opts = dict(base)
    if candidates:
        on_opts["models"] = candidates

    def _one(p: str) -> dict:
        msgs = [{"role": "user", "content": p}]
        # The routed answer and the frontier answer are independent, so run them
        # concurrently - the row's wall-time becomes one generation, not two stacked.
        try:
            with ThreadPoolExecutor(max_workers=2) as gex:
                routed_fut = gex.submit(proxy.serve, msgs, "finops-auto", dict(on_opts), user)
                front_fut = gex.submit(proxy.serve, msgs, frontier, dict(base), user)
                r_on, f_on = routed_fut.result()
                r_off, f_off = front_fut.result()
        except proxy.ProxyError as e:
            return {"prompt": p, "error": e.message}
        a_on = r_on["choices"][0]["message"]["content"]
        a_off = r_off["choices"][0]["message"]["content"]
        # Both judge calls are independent too - score them in parallel.
        with ThreadPoolExecutor(max_workers=2) as jex:
            qon_fut = jex.submit(_quality, p, a_on, judge_model)
            qoff_fut = jex.submit(_quality, p, a_off, judge_model)
            q_on = qon_fut.result()
            q_off = qoff_fut.result()
        saved = max(0.0, f_off["costUsd"] - f_on["costUsd"])
        return {
            "prompt": p,
            "routed": {"model": f_on["servedBy"]["short"], "tier": f_on["servedBy"]["tier"],
                       "costUsd": f_on["costUsd"], "quality": q_on, "complexity": f_on["complexity"]},
            "frontier": {"model": f_off["servedBy"]["short"], "costUsd": f_off["costUsd"], "quality": q_off},
            "savedUsd": saved,
            "savedPct": round(saved / f_off["costUsd"] * 100, 1) if f_off["costUsd"] > 0 else 0.0,
        }

    with ThreadPoolExecutor(max_workers=min(MAX_PROMPTS, len(prompts))) as ex:
        rows = list(ex.map(_one, prompts))

    ok = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]

    def _avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    routed_q = _avg([r["routed"]["quality"] for r in ok])
    frontier_q = _avg([r["frontier"]["quality"] for r in ok])
    routed_cost = sum(r["routed"]["costUsd"] for r in ok)
    frontier_cost = sum(r["frontier"]["costUsd"] for r in ok)
    saved = max(0.0, frontier_cost - routed_cost)
    retention = (round(routed_q / frontier_q * 100, 1)
                 if (routed_q is not None and frontier_q not in (None, 0)) else None)
    try:
        judge_short = reg.by_id(judge_model).short if judge_model else reg.cheapest_of_tier("frontier").short
    except Exception:  # noqa: BLE001
        judge_short = judge_model or "frontier"

    agg = {
        "count": len(ok),
        "avgRoutedQuality": routed_q,
        "avgFrontierQuality": frontier_q,
        "qualityRetentionPct": retention,
        "routedCostUsd": routed_cost,
        "frontierCostUsd": frontier_cost,
        "savedUsd": saved,
        "savedPct": round(saved / frontier_cost * 100, 1) if frontier_cost > 0 else 0.0,
        "judge": judge_short,
        "frontierBaseline": (reg.by_id(frontier).short if _safe_by_id(frontier) else frontier),
    }
    mlflow_log = _log_mlflow(agg)
    return {"aggregate": agg, "rows": rows, "errors": errors, "mlflow": mlflow_log}


def _safe_by_id(mid: str) -> bool:
    try:
        reg.by_id(mid)
        return True
    except Exception:  # noqa: BLE001
        return False


def _log_mlflow(agg: dict) -> dict:
    """Best-effort: log the aggregate eval metrics to an MLflow run so the result is
    tracked/reproducible. Degrades to {logged:false} if MLflow or experiment access
    isn't available (the eval itself never depends on it)."""
    try:
        import mlflow
        exp = "/Shared/intelligent-ai-finops-eval"
        mlflow.set_experiment(exp)
        with mlflow.start_run(run_name="byo-eval") as run:
            for k in ("count", "avgRoutedQuality", "avgFrontierQuality", "qualityRetentionPct",
                      "routedCostUsd", "frontierCostUsd", "savedUsd", "savedPct"):
                v = agg.get(k)
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, float(v))
            mlflow.set_tag("judge", agg.get("judge", ""))
            return {"logged": True, "experiment": exp, "runId": run.info.run_id}
    except Exception as e:  # noqa: BLE001
        return {"logged": False, "reason": str(e)[:140]}
