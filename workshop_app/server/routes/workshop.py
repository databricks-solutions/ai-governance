"""Workshop content, test execution, and progress tracking."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import deep_links
from ..config import get_steps
from ..db import pool
from ..tests_registry import run_test

router = APIRouter()


@router.get("/workshop")
def workshop_content():
    """The full guidebook: intro + pillars/steps. Resolves manual deep links to URLs."""
    steps = get_steps()
    pillars = []
    for pillar in steps.get("pillars", []):
        out_steps = []
        for s in pillar.get("steps", []):
            step = dict(s)
            if step.get("manual", {}).get("deep_link"):
                step["manual"] = {**step["manual"], "url": deep_links.resolve(step["manual"]["deep_link"])}
            out_steps.append(step)
        pillars.append({**pillar, "steps": out_steps})
    return {"intro": steps.get("intro", {}), "pillars": pillars}


class RunTest(BaseModel):
    test: str
    run_id: str
    step_id: str
    pillar_id: str
    kind: str = "action"          # 'action' | 'verify'
    updated_by: str | None = None


@router.post("/test")
def run_and_record(body: RunTest):
    result = run_test(body.test)
    status = "done" if result.get("ok") else "failed"
    _save_progress(body.run_id, body.step_id, body.pillar_id, status, result, body.updated_by)
    return result


class Progress(BaseModel):
    run_id: str
    step_id: str
    pillar_id: str
    status: str
    notes: str | None = None
    updated_by: str | None = None


@router.post("/progress")
def set_progress(body: Progress):
    _save_progress(body.run_id, body.step_id, body.pillar_id, body.status, None, body.updated_by, body.notes)
    return {"ok": True}


@router.get("/progress/{run_id}")
def get_progress(run_id: str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT step_id, pillar_id, status, last_result, notes, updated_at
                   FROM step_progress WHERE run_id = %s""",
                (run_id,),
            )
            rows = cur.fetchall()
    return {
        r[0]: {"pillar_id": r[1], "status": r[2], "last_result": r[3],
               "notes": r[4], "updated_at": r[5].isoformat() if r[5] else None}
        for r in rows
    }


def _save_progress(run_id, step_id, pillar_id, status, result, updated_by, notes=None):
    if not run_id:
        raise HTTPException(400, "run_id is required")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO step_progress
                   (run_id, step_id, pillar_id, status, last_result, notes, updated_by, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, now())
                   ON CONFLICT (run_id, step_id) DO UPDATE SET
                     status = EXCLUDED.status,
                     last_result = COALESCE(EXCLUDED.last_result, step_progress.last_result),
                     notes = COALESCE(EXCLUDED.notes, step_progress.notes),
                     pillar_id = EXCLUDED.pillar_id,
                     updated_by = EXCLUDED.updated_by,
                     updated_at = now()""",
                (run_id, step_id, pillar_id, status,
                 json.dumps(result) if result is not None else None, notes, updated_by),
            )
        conn.commit()
