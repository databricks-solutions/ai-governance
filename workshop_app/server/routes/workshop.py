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
# were removed (the workshop is deployed once per engagement). Bumped to 3 when per-step outcome
# flags landed: each step now carries `outcome`/`poc`/`na`, "complete" means achieved (test done
# OR hand-marked done), the summary adds `applicable` (total minus N/A), and a top-level
# `poc_items` lists steps flagged for the POC follow-up.
OUTCOMES_SCHEMA_VERSION = 3


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


class Outcome(BaseModel):
    step_id: str
    pillar_id: str
    outcome: str | None = None    # "done" | "na" | null (Done and N/A are mutually exclusive)
    poc: bool = False             # flag the step for the POC follow-up
    updated_by: str | None = None


@router.post("/outcome")
def set_outcome(body: Outcome):
    """Record the hand-marked outcome flags (Done / N/A / Add-to-POC) for one step.

    Separate from /progress: these are set by hand — on a step card or the outcomes checklist —
    so the workshop can guide activities even when the interactive Try-It tests aren't run. The
    client sends the full desired state each time. A step is achieved if the test ran `done` OR
    outcome == "done".
    """
    store.set_outcome(body.step_id, body.pillar_id, outcome=body.outcome, poc=body.poc,
                      updated_by=body.updated_by)
    return {"ok": True}


@router.get("/progress")
def get_progress():
    return {
        step_id: {"pillar_id": r.get("pillar_id"), "status": r.get("status"),
                  "last_result": r.get("last_result"), "notes": r.get("notes"),
                  "outcome": r.get("outcome"), "poc": bool(r.get("poc", False)),
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
    progress = get_progress()  # {step_id: {status, last_result, notes, outcome, poc, ...}}
    totals = {"total": 0, "applicable": 0, "done": 0, "na": 0}
    poc_items: list[dict] = []

    def _group_out(group: dict) -> dict:
        steps_out = []
        for s in group["steps"]:
            saved = progress.get(s["id"], {})
            raw_status = saved.get("status", "not_started")
            outcome = saved.get("outcome")            # "done" | "na" | None (hand-marked)
            poc = bool(saved.get("poc", False))
            na = outcome == "na"
            # Achieved = the interactive test passed OR the outcome was marked done by hand, so a
            # workshop run without the app's Try-It buttons still reflects real outcomes.
            achieved = (raw_status == "done") or (outcome == "done")
            if na:
                disp = "n/a"
            elif achieved and raw_status != "done":
                disp = "done (marked)"
            else:
                disp = raw_status
            totals["total"] += 1
            if na:
                totals["na"] += 1
            else:
                totals["applicable"] += 1
                totals["done"] += 1 if achieved else 0
            row = {
                "step_id": s["id"],
                "title": s["title"],
                "status": disp,
                "raw_status": raw_status,
                "outcome": outcome,
                "poc": poc,
                "na": na,
                "complete": achieved,
                "notes": saved.get("notes"),
                "last_result_summary": (saved.get("last_result") or {}).get("summary")
                if isinstance(saved.get("last_result"), dict) else None,
                "updated_at": saved.get("updated_at"),
            }
            if poc:
                poc_items.append({"pillar_id": group["id"], "step_id": s["id"],
                                  "title": s["title"], "status": disp, "notes": saved.get("notes")})
            steps_out.append(row)
        return {"pillar_id": group["id"], "title": group["title"], "steps": steps_out}

    pillars_out = [_group_out(p) for p in workshop_content()["pillars"]]
    accelerators_out = [_group_out(a) for a in accelerators_content()["accelerators"]]

    # Next steps = anything applicable that isn't achieved, to drive follow-up. N/A drops out.
    next_steps = [
        {"pillar_id": g["pillar_id"], "step_id": st["step_id"], "title": st["title"], "status": st["status"]}
        for g in pillars_out + accelerators_out for st in g["steps"]
        if not st["complete"] and not st["na"]
    ]

    applicable = totals["applicable"]
    pct = round(100 * totals["done"] / applicable) if applicable else 0
    return {
        "schema_version": OUTCOMES_SCHEMA_VERSION,
        "source": "ai-governance-workshop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": totals["total"], "applicable": applicable,
                    "done": totals["done"], "na": totals["na"], "pct": pct},
        "pillars": pillars_out,
        "accelerators": accelerators_out,
        "poc_items": poc_items,
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
        f"**Progress:** {o['summary']['done']}/{o['summary']['applicable']} applicable steps "
        f"achieved ({o['summary']['pct']}%)"
        + (f" · {o['summary']['na']} marked N/A" if o['summary'].get('na') else ""),
        "",
    ]
    def _section(groups, heading=None):
        if heading and any(g["steps"] for g in groups):
            lines.append(f"# {heading}")
            lines.append("")
        for p in groups:
            applicable = [s for s in p["steps"] if not s.get("na")]
            done = sum(1 for s in applicable if s["complete"])
            lines.append(f"## {p['title']} — {done}/{len(applicable)}")
            lines.append("")
            for s in p["steps"]:
                mark = "x" if s["complete"] else ("-" if s.get("na") else " ")
                line = f"- [{mark}] {s['title']} — **{s['status']}**"
                if s.get("poc"):
                    line += "  ·  _POC_"
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
    if o.get("poc_items"):
        lines.append("## Flagged for POC follow-up")
        lines.append("")
        for p in o["poc_items"]:
            line = f"- {p['title']} ({p['pillar_id']}) — {p['status']}"
            if p.get("notes"):
                line += f" — _{p['notes']}_"
            lines.append(line)
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
    the session (cost/choice/control, 3h hands-on + 1h slides, target personas, accelerators).

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
