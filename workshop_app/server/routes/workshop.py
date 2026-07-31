"""Workshop content, test execution, and progress tracking."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import deep_links
from ..config import get_accelerators, get_steps
from ..db import pool
from ..tests_registry import run_test

router = APIRouter()

# Version of the outcomes-JSON contract the internal sales app ingests.
OUTCOMES_SCHEMA_VERSION = 1


def _resolve_group(group: dict) -> dict:
    """Resolve manual deep_links on each step of a pillar/accelerator group to URLs."""
    out_steps = []
    for s in group.get("steps", []):
        step = dict(s)
        if step.get("manual", {}).get("deep_link"):
            step["manual"] = {**step["manual"], "url": deep_links.resolve(step["manual"]["deep_link"])}
        out_steps.append(step)
    return {**group, "steps": out_steps}


@router.get("/workshop")
def workshop_content():
    """The full guidebook: intro + pillars/steps. Resolves manual deep links to URLs."""
    steps = get_steps()
    pillars = [_resolve_group(p) for p in steps.get("pillars", [])]
    return {"intro": steps.get("intro", {}), "pillars": pillars}


@router.get("/accelerators")
def accelerators_content():
    """Optional add-on accelerators: an overview + one group per accelerator."""
    acc = get_accelerators()
    groups = [_resolve_group(a) for a in acc.get("accelerators", [])]
    return {"overview": acc.get("overview", {}), "accelerators": groups}


@router.get("/faq", response_class=PlainTextResponse)
def faq():
    """Serve the repo's FAQ.md so the in-app FAQ and the repo file are the same source."""
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "FAQ.md")
    try:
        with open(os.path.abspath(path)) as f:
            return f.read()
    except FileNotFoundError:
        return "# FAQ\n\nFAQ.md not found."


class RunTest(BaseModel):
    test: str
    customer_sfid: str
    step_id: str
    pillar_id: str
    kind: str = "action"          # 'action' | 'verify'
    updated_by: str | None = None


@router.post("/test")
def run_and_record(body: RunTest):
    result = run_test(body.test)
    status = "done" if result.get("ok") else "failed"
    _save_progress(body.customer_sfid, body.step_id, body.pillar_id, status, result, body.updated_by)
    return result


class Progress(BaseModel):
    customer_sfid: str
    step_id: str
    pillar_id: str
    status: str
    notes: str | None = None
    updated_by: str | None = None


@router.post("/progress")
def set_progress(body: Progress):
    _save_progress(body.customer_sfid, body.step_id, body.pillar_id, body.status, None, body.updated_by, body.notes)
    return {"ok": True}


@router.get("/progress/{customer_sfid}")
def get_progress(customer_sfid: str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT step_id, pillar_id, status, last_result, notes, updated_at
                   FROM step_progress WHERE customer_sfid = %s""",
                (customer_sfid,),
            )
            rows = cur.fetchall()
    return {
        r[0]: {"pillar_id": r[1], "status": r[2], "last_result": r[3],
               "notes": r[4], "updated_at": r[5].isoformat() if r[5] else None}
        for r in rows
    }


def _save_progress(customer_sfid, step_id, pillar_id, status, result, updated_by, notes=None):
    if not customer_sfid:
        raise HTTPException(400, "customer_sfid is required")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO step_progress
                   (customer_sfid, step_id, pillar_id, status, last_result, notes, updated_by, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, now())
                   ON CONFLICT (customer_sfid, step_id) DO UPDATE SET
                     status = EXCLUDED.status,
                     last_result = COALESCE(EXCLUDED.last_result, step_progress.last_result),
                     notes = COALESCE(EXCLUDED.notes, step_progress.notes),
                     pillar_id = EXCLUDED.pillar_id,
                     updated_by = EXCLUDED.updated_by,
                     updated_at = now()""",
                (customer_sfid, step_id, pillar_id, status,
                 json.dumps(result) if result is not None else None, notes, updated_by),
            )
        conn.commit()


# --------------------------------------------------------------------------- Export
def _build_outcomes(customer_sfid: str, customer_name: str | None) -> dict:
    """Assemble the workshop outcomes: every step with its status, keyed to a Salesforce id.

    This is the contract the internal sales app ingests (schema_version). It merges the
    workshop definition (so every step appears, even untouched ones) with saved progress.
    """
    progress = get_progress(customer_sfid)  # {step_id: {status, last_result, notes, ...}}
    totals = {"total": 0, "done": 0}

    def _group_out(group: dict) -> dict:
        steps_out = []
        for s in group["steps"]:
            saved = progress.get(s["id"], {})
            status = saved.get("status", "not_started")
            complete = status == "done"
            totals["total"] += 1
            totals["done"] += 1 if complete else 0
            steps_out.append({
                "step_id": s["id"],
                "title": s["title"],
                "status": status,
                "complete": complete,
                "notes": saved.get("notes"),
                "last_result_summary": (saved.get("last_result") or {}).get("summary")
                if isinstance(saved.get("last_result"), dict) else None,
                "updated_at": saved.get("updated_at"),
            })
        return {"pillar_id": group["id"], "title": group["title"], "steps": steps_out}

    pillars_out = [_group_out(p) for p in workshop_content()["pillars"]]
    accelerators_out = [_group_out(a) for a in accelerators_content()["accelerators"]]

    # Next steps = anything not complete, so the sales app can drive follow-up.
    next_steps = [
        {"pillar_id": g["pillar_id"], "step_id": st["step_id"], "title": st["title"], "status": st["status"]}
        for g in pillars_out + accelerators_out for st in g["steps"] if not st["complete"]
    ]

    pct = round(100 * totals["done"] / totals["total"]) if totals["total"] else 0
    return {
        "schema_version": OUTCOMES_SCHEMA_VERSION,
        "source": "ai-governance-workshop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "customer_sfid": customer_sfid,
        "customer_name": customer_name,
        "summary": {"total": totals["total"], "done": totals["done"], "pct": pct},
        "pillars": pillars_out,
        "accelerators": accelerators_out,
        "next_steps": next_steps,
    }


@router.get("/export/outcomes")
def export_outcomes(customer_sfid: str, customer_name: str | None = None):
    """The JSON the internal sales app loads to track workshop outcomes + next steps."""
    if not customer_sfid:
        raise HTTPException(400, "customer_sfid is required")
    return _build_outcomes(customer_sfid, customer_name)


@router.get("/export/report", response_class=PlainTextResponse)
def export_report(customer_sfid: str, customer_name: str | None = None):
    """A human-readable per-step report (complete / incomplete) as Markdown."""
    if not customer_sfid:
        raise HTTPException(400, "customer_sfid is required")
    o = _build_outcomes(customer_sfid, customer_name)
    lines = [
        f"# AI Governance Workshop — Outcomes Report",
        "",
        f"**Account:** {o['customer_name'] or o['customer_sfid']}  ",
        f"**Salesforce id:** {o['customer_sfid']}  ",
        f"**Generated:** {o['generated_at']}  ",
        f"**Progress:** {o['summary']['done']}/{o['summary']['total']} steps complete "
        f"({o['summary']['pct']}%)",
        "",
    ]
    def _section(groups, heading=None):
        if heading and any(g["steps"] for g in groups):
            lines.append(f"# {heading}")
            lines.append("")
        for p in groups:
            done = sum(1 for s in p["steps"] if s["complete"])
            lines.append(f"## {p['title']} — {done}/{len(p['steps'])}")
            lines.append("")
            for s in p["steps"]:
                mark = "x" if s["complete"] else " "
                line = f"- [{mark}] {s['title']} — **{s['status']}**"
                if s.get("notes"):
                    line += f"  \n  _notes:_ {s['notes']}"
                lines.append(line)
            lines.append("")

    _section(o["pillars"])
    _section(o.get("accelerators", []), heading="Accelerators (optional add-ons)")
    if o["next_steps"]:
        lines.append("## Next steps (incomplete items)")
        lines.append("")
        for n in o["next_steps"]:
            lines.append(f"- {n['title']} ({n['pillar_id']}) — {n['status']}")
        lines.append("")
    return "\n".join(lines)
