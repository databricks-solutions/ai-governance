"""Workshop content, test execution, and progress tracking."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from .. import deep_links, pdf, routing, store
from ..config import get_accelerators, get_brochure, get_prerequisites, get_steps
from ..tests_registry import run_test

router = APIRouter()

# Version of the outcomes-JSON contract. Bumped to 2 when the account/Salesforce identifiers
# were removed: the workshop is deployed once per engagement, so the export no longer carries a
# customer_sfid or customer_name.
OUTCOMES_SCHEMA_VERSION = 2


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


@router.get("/prerequisites")
def prerequisites_content():
    """The pre-workshop checklist, plus whether the PDF export can be generated.

    `pdf_available` lets the UI hide (rather than offer and then fail) the PDF button if
    reportlab is missing from the deployed image.
    """
    ok, reason = pdf.available()
    return {**get_prerequisites(), "pdf_available": ok, "pdf_unavailable_reason": reason}


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


# --------------------------------------------------------------------------- Cost routing
# The Cost pillar steps drive these through /api/test, but they are exposed directly too so
# a deliverer can try the customer's own prompts without touching the guidebook flow.
@router.get("/routing/panel")
def routing_panel():
    """Model panel, prices, and the routing policy."""
    return routing.panel()


class RoutingPrompt(BaseModel):
    prompt: str


@router.post("/routing/compare")
def routing_compare(body: RoutingPrompt):
    """One prompt against every model — cost, latency, and answers side by side."""
    return routing.compare(body.prompt)


@router.post("/routing/route")
def routing_route(body: RoutingPrompt):
    """Classify, dispatch to the cheapest sufficient model, and price the counterfactual."""
    return routing.route(body.prompt)


class RunTest(BaseModel):
    test: str
    step_id: str
    pillar_id: str
    kind: str = "action"          # 'action' | 'verify'
    updated_by: str | None = None


@router.post("/test")
def run_and_record(body: RunTest):
    result = run_test(body.test)
    # A test can come back three ways, and collapsing them would overstate progress:
    # ok + action_required means "ran fine, but nothing is proven yet" (a guided step, or
    # telemetry with no data). Recording that as `done` would inflate the progress bar and
    # the outcomes JSON.
    if result.get("status") == "action_required":
        status = "action_required"
    elif result.get("ok"):
        status = "done"
    else:
        status = "failed"
    _save_progress(body.step_id, body.pillar_id, status, result, body.updated_by)
    return result


class Progress(BaseModel):
    step_id: str
    pillar_id: str
    status: str
    notes: str | None = None
    updated_by: str | None = None


@router.post("/progress")
def set_progress(body: Progress):
    _save_progress(body.step_id, body.pillar_id, body.status, None, body.updated_by, body.notes)
    return {"ok": True}


@router.get("/progress")
def get_progress():
    return {
        step_id: {"pillar_id": r.get("pillar_id"), "status": r.get("status"),
                  "last_result": r.get("last_result"), "notes": r.get("notes"),
                  "updated_at": r.get("updated_at")}
        for step_id, r in store.get().items()
    }


def _save_progress(step_id, pillar_id, status, result, updated_by, notes=None):
    store.save(step_id, pillar_id, status, result, updated_by, notes)


# --------------------------------------------------------------------------- Export
def _build_outcomes() -> dict:
    """Assemble the workshop outcomes: every step with its status.

    A versioned JSON document (schema_version) that merges the workshop definition (so every
    step appears, even untouched ones) with saved progress. It carries no account or Salesforce
    identifier — the app is deployed once per workshop.
    """
    progress = get_progress()  # {step_id: {status, last_result, notes, ...}}
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

    # Next steps = anything not complete, to drive follow-up.
    next_steps = [
        {"pillar_id": g["pillar_id"], "step_id": st["step_id"], "title": st["title"], "status": st["status"]}
        for g in pillars_out + accelerators_out for st in g["steps"] if not st["complete"]
    ]

    pct = round(100 * totals["done"] / totals["total"]) if totals["total"] else 0
    return {
        "schema_version": OUTCOMES_SCHEMA_VERSION,
        "source": "ai-governance-workshop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": totals["total"], "done": totals["done"], "pct": pct},
        "pillars": pillars_out,
        "accelerators": accelerators_out,
        "next_steps": next_steps,
    }


@router.get("/export/outcomes")
def export_outcomes():
    """The machine-readable workshop outcomes + next steps (JSON, schema_version)."""
    return _build_outcomes()


@router.get("/export/report", response_class=PlainTextResponse)
def export_report():
    """A human-readable per-step report (complete / incomplete) as Markdown."""
    o = _build_outcomes()
    lines = [
        "# AI Governance Workshop — Outcomes Report",
        "",
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


def _pdf_response(body: bytes, filename: str) -> Response:
    """Return a PDF as a download.

    `attachment` (not `inline`) on purpose: these are documents that get saved and emailed,
    so the browser should write a file with our chosen name rather than open a viewer tab.
    """
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_pdf() -> None:
    ok, reason = pdf.available()
    if not ok:
        # 503, not 500: the request was valid and the same request will work once the
        # dependency is installed. The Markdown exports remain available meanwhile.
        raise HTTPException(
            503,
            "PDF generation is unavailable on this deployment (reportlab failed to import: "
            f"{reason}). Use the Markdown/JSON export instead.",
        )


@router.get("/export/brochure.pdf")
def export_brochure_pdf(customer_name: str | None = None):
    """The one-page workshop brochure as a PDF — the leave-ahead an account team sends to book
    the session (cost/choice/control, 4-hour format, target personas, accelerators).

    Exists before any workshop does, so it needs no progress.
    """
    _require_pdf()
    return _pdf_response(
        pdf.brochure_pdf(get_brochure(), customer_name),
        "ai-governance-workshop-brochure.pdf",
    )


@router.get("/export/prerequisites.pdf")
def export_prerequisites_pdf(customer_name: str | None = None):
    """The prerequisites checklist as a printable PDF with tickable checkboxes.

    This is pre-workshop material that exists before any progress does, which is exactly why
    it is on the Walkthrough page rather than behind the export panel.
    """
    _require_pdf()
    return _pdf_response(
        pdf.prerequisites_pdf(get_prerequisites(), customer_name),
        "ai-governance-workshop-prerequisites.pdf",
    )


@router.get("/export/report.pdf")
def export_report_pdf():
    """The outcomes report as a PDF — the leave-behind that replaced the POC DOC."""
    _require_pdf()
    o = _build_outcomes()
    return _pdf_response(pdf.report_pdf(o), "ai-governance-workshop-outcomes.pdf")
