"""Build the AI Governance **POC DOC** from the workshop outcomes.

The workshop proves Choice / Cost / Control controls live on the customer's own workspace. The
POC DOC is the leave-behind that takes them the rest of the way to production (U6): every control
the room could not finish becomes a tracked task with an owner, a due date, and a status, and
every control it DID prove is recorded as done. It is the same structure as the field's standard
POC DOC template (`docs/POC_DOC_TEMPLATE.md`) - header, contacts, scope & success criteria, a
tasks-and-timeline punch list, staffing, mutual success plan - so an account team can drop it into
an engagement without reformatting.

ONE builder owns the content (`build_poc_doc`) so the Markdown export (`render_markdown`, here) and
the PDF export (`pdf.report_pdf`, which consumes the same structured dict) can never drift. The
builder fills everything the app knows - the task list from the room's "Add to POC" flags plus any
incomplete step, the success criteria from each step's "We can…" outcome, what was proven - and
leaves the customer-specific scaffolding (contacts, owners, dates, staffing) as placeholders for
the SA to complete.
"""
from __future__ import annotations

from typing import Any

# Governance objective per pillar - the "why this matters" blurb shown in the Objectives section
# and used as the Business Value line on each pillar's scope group. Keyed by the pillar id from
# steps.yaml. Accelerators (any other id) fall back to a generic line.
PILLAR_OBJECTIVES = {
    "choice": "Any model, tool, or agent behind one Unity Catalog control plane - proprietary and "
              "open-weight addressed the same way, governed by UC grants, so model choice is never "
              "a single-vendor bet.",
    "cost": "Every request priced, projected, budgeted, and attributed to a team and a task - so AI "
            "spend is visible, forecastable, and capped before it runs away.",
    "control": "Rate limits, guardrails, and MCP policies that deny specific calls, with identity "
               "propagation and the audit telemetry that proves each control actually fired.",
}
_ACCEL_OBJECTIVE = ("A production deep-dive on one priority capability, governed through the same "
                    "control plane as the core pillars.")

# Status shown on carried / incomplete tasks and scope rows, cleaned for display.
_STATUS_LABEL = {
    "done (marked)": "Proven in workshop",
    "n/a": "N/A",
    "not_started": "Not started",
    "action_required": "Action needed",
    "failed": "Failed - needs follow-up",
    "done": "Proven in workshop",
}


def _status(raw: str | None) -> str:
    return _STATUS_LABEL.get((raw or "").strip(), (raw or "").replace("_", " ").strip() or "Not started")


def _objective(pillar_id: str) -> str:
    return PILLAR_OBJECTIVES.get(pillar_id, _ACCEL_OBJECTIVE)


def build_poc_doc(outcomes: dict, customer: str | None = None) -> dict:
    """Assemble the structured POC DOC from `_build_outcomes()` output.

    Returns a dict of sections consumed identically by `render_markdown` (Markdown export) and
    `pdf.report_pdf` (PDF export). Dynamic sections (scope, tasks, proven) are filled from the
    workshop; scaffolding sections (contacts, staffing, mutual success, resources) carry
    placeholders for the account team.
    """
    cust = (customer or "").strip() or "[Customer]"
    summary = outcomes.get("summary", {}) or {}
    done = summary.get("done", 0)
    applicable = summary.get("applicable", 0)
    na = summary.get("na", 0)
    pct = summary.get("pct", 0)

    # Core pillars always appear. An accelerator appears ONLY if the customer selected it - i.e.
    # the room touched at least one of its steps (marked done, flagged for POC, or ran a Try-It
    # that left a status). An untouched accelerator is not part of this engagement, so it stays
    # out of the POC doc entirely.
    def _selected(group: dict) -> bool:
        for s in group["steps"]:
            if s.get("complete") or s.get("poc"):
                return True
            st = (s.get("status") or "").strip().lower()
            if not s.get("na") and st not in ("", "not_started", "n/a"):
                return True
        return False

    pillars = list(outcomes.get("pillars", []))
    accels = [a for a in outcomes.get("accelerators", []) if _selected(a)]
    groups = pillars + accels
    # Which groups are accelerators - they sort into the "Accelerator" task phase, not a core one.
    pillar_ids = {g["pillar_id"] for g in pillars}

    # --- Scope & success criteria: one group per pillar, one row per step (outcome = criterion).
    scope_groups: list[dict] = []
    proven_groups: list[dict] = []
    for g in groups:
        rows, done_titles, carried_titles = [], [], []
        for s in g["steps"]:
            crit = s.get("criterion") or s.get("title")
            rows.append({
                "okr": s["title"],
                "success_criteria": crit,
                "status": _status(s.get("status")),
                "na": bool(s.get("na")),
                "done": bool(s.get("complete")),
            })
            if s.get("na"):
                continue
            (done_titles if s.get("complete") else carried_titles).append(s["title"])
        scope_groups.append({
            "pillar_id": g["pillar_id"],
            "title": g["title"],
            "objective": _objective(g["pillar_id"]),
            "rows": rows,
        })
        if done_titles or carried_titles:
            proven_groups.append({
                "title": g["title"],
                "proven": done_titles,
                "carried": carried_titles,
            })

    # --- Tasks & timeline: everything that is NOT proven and NOT N/A becomes a task, grouped by
    # pillar. POC-flagged ("Add to POC") items come first within each group - they are the room's
    # deliberate carry-forward - then the merely-incomplete steps. Proven and N/A steps drop out.
    poc_ids = {p["step_id"] for p in outcomes.get("poc_items", [])}
    notes_by_id = {p["step_id"]: p.get("notes") for p in outcomes.get("poc_items", [])}
    by_group: dict[str, list[dict]] = {}
    group_title = {g["pillar_id"]: g["title"] for g in groups}
    group_order = [g["pillar_id"] for g in groups]

    for g in groups:
        for s in g["steps"]:
            if s.get("na") or s.get("complete"):
                continue
            by_group.setdefault(g["pillar_id"], []).append({
                "task": s["title"],
                "comments": s.get("notes") or notes_by_id.get(s["step_id"]) or "",
                "status": _status(s.get("status")),
                "poc": s["step_id"] in poc_ids,
            })
    # POC-flagged first, stable otherwise.
    for rows in by_group.values():
        rows.sort(key=lambda r: not r["poc"])

    task_groups: list[dict] = [{
        "phase": "Kickoff & environment",
        "rows": [
            {"task": "POC kickoff - align scope, owners, and the success criteria below",
             "comments": "Full team, both sides", "status": "", "poc": False},
            {"task": "Confirm workspace, Unity Gateway, and the two system grants are in place",
             "comments": "Carries over the workshop prerequisites", "status": "", "poc": False},
        ],
    }]
    for pid in group_order:
        rows = by_group.get(pid)
        if not rows:
            continue
        phase = group_title.get(pid, pid)
        if pid not in pillar_ids:
            phase = f"Accelerator - {phase}"
        task_groups.append({"phase": phase, "rows": rows})
    task_groups.append({
        "phase": "Readout & production sign-off",
        "rows": [
            {"task": "Final readout - every success criterion met, remaining risks named",
             "comments": "Full team, both sides", "status": "", "poc": False},
            {"task": "Production sign-off and transition to steady-state ownership",
             "comments": "", "status": "", "poc": False},
        ],
    })

    return {
        "customer": cust,
        "title": f"{cust} // Databricks",
        "subtitle": "AI Governance - Production POC",
        "generated_at": outcomes.get("generated_at"),
        "intro": (
            f"The AI Governance Workshop proved Choice, Cost, and Control live on {cust}'s own "
            "workspace. This POC takes that from a working session to production: every control the "
            "room could not finish becomes a tracked task below, and the goal is to drive the list "
            "to zero so AI at " + cust + " runs on one governed control plane - every model, tool, "
            "and agent inventoried, every request priced and attributed, every policy enforced and "
            "audited."
        ),
        "summary": {
            "done": done, "applicable": applicable, "na": na, "pct": pct,
            "line": (f"{done} of {applicable} applicable controls were proven live in the "
                     f"workshop ({pct}%)" + (f"; {na} marked N/A" if na else "") +
                     f". The remaining {max(applicable - done, 0)} are the POC punch list below."),
        },
        "objectives": [{"title": g["title"], "text": g["objective"]} for g in scope_groups],
        "scope_groups": scope_groups,
        "task_groups": task_groups,
        "proven_groups": proven_groups,
        # --- Scaffolding: placeholders the account team fills per engagement. ---
        "contacts": {
            "databricks": [["@FirstName LastName", "Account Executive"],
                           ["@FirstName LastName", "Solutions Architect (lead)"],
                           ["@FirstName LastName", "Specialist SA - AI Governance"]],
            "customer": [["Name", "Platform / Cloud admin"],
                         ["Name", "AI Governance lead"],
                         ["Name", "Principal developer"]],
        },
        "staffing": {
            "databricks": [["@FirstName LastName", "Lead SA", "End-to-end ownership"],
                           ["@FirstName LastName", "Specialist SA", "AI Governance overlay"]],
            "customer": [["Name", "Platform admin", "Workspace & entitlements"],
                         ["Name", "AI Governance lead", "Policy & budget owner"]],
            "cadence": [
                "Kickoff with the full team on both sides",
                "Weekly progress review against the task list below",
                "Final readout when the success criteria are met",
            ],
        },
        "mutual_success": [
            ["Executive alignment", "Confirm the governance mandate and budget owner", "[ ]", "[ ]"],
            ["Environment ready", "Workspace, Unity Gateway, and system grants in place", "[ ]", "[ ]"],
            ["Punch list to zero", "Work the tasks below to done", "Joint", "[ ]"],
            ["Production sign-off", "Readout and transition to steady state", "[ ]", "[ ]"],
        ],
        "resources": [
            ["AI Governance overview", "go/aigovernance"],
            ["Unity Gateway documentation", "https://docs.databricks.com"],
            ["Workshop app", "https://github.com/databricks-solutions/ai-governance"],
            ["AI governance maturity assessment",
             "https://github.com/databricks-solutions/ai-governance/blob/main/workshop_app/docs/AI_Governance_Maturity_Assessment.xlsx"],
        ],
    }


# --------------------------------------------------------------------------- Markdown renderer
def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """A GitHub/Google-Docs-compatible pipe table. Empty cells render as a single space."""
    def cell(x: Any) -> str:
        return str(x if x not in (None, "") else " ").replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(cell(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(cell(c) for c in r) + " |")
    return out


def render_markdown(doc: dict) -> str:
    """Render the structured POC DOC to Markdown - the `.md` export and the Google-Doc source.

    Kept converter-safe for the "open the .md in the google-docs skill" workflow: ASCII only and
    emphasis as `**bold**` pairs, never `_italic_`/`*italic*` (the markdown->Google-Doc converter
    mishandles single-emphasis and non-ASCII, bleeding italics across the doc).
    """
    L: list[str] = [f"# {doc['title']}", "", f"## {doc['subtitle']}", ""]
    if doc.get("generated_at"):
        L += [f"Generated {str(doc['generated_at'])[:19]} from the AI Governance Workshop app.", ""]
    L += [doc["intro"], ""]

    L += ["### Key Contacts", "", "**Databricks**", ""]
    L += _table(["Name", "Role"], doc["contacts"]["databricks"]) + [""]
    L += [f"**{doc['customer']}**", ""]
    L += _table(["Name", "Title / Role"], doc["contacts"]["customer"]) + [""]

    L += ["### Executive Alignment", "",
          "- **[Date]:** [Customer exec] ([title]) and [Databricks exec] ([title]) - [purpose]", ""]

    L += ["### Summary & Scope", "", doc["summary"]["line"], ""]

    L += ["### Governance Objectives", ""]
    for o in doc["objectives"]:
        L += [f"**{o['title']}** - {o['text']}", ""]

    L += ["### POC Scope & Success Criteria", ""]
    rows: list[list[str]] = []
    for g in doc["scope_groups"]:
        rows.append([f"**{g['title']}** - {g['objective']}", "", ""])
        for r in g["rows"]:
            rows.append([r["okr"], r["success_criteria"], r["status"]])
    L += _table(["OKR", "Success criteria", "Status"], rows) + [""]

    L += ["### Tasks and Timeline", "",
          "Everything not proven in the workshop, as a tracked punch list. **Add to POC** items "
          "from the room are listed first in each section. Work the list to zero to reach "
          "production.", ""]
    trows: list[list[str]] = []
    for g in doc["task_groups"]:
        trows.append([f"**{g['phase']}**", "", "", "", "", ""])
        for r in g["rows"]:
            task = r["task"] + ("  -  **Add to POC**" if r.get("poc") else "")
            trows.append([task, "", "", r.get("comments", ""), "", r.get("status", "")])
    L += _table(["Task", f"{doc['customer']} owner", "Databricks owner", "Comments",
                 "Target due date", "Status"], trows) + [""]

    L += ["### POC Staffing Plan", "", "**Databricks**", ""]
    L += _table(["Name", "Role", "Focus"], doc["staffing"]["databricks"]) + [""]
    L += [f"**{doc['customer']}**", ""]
    L += _table(["Name", "Role", "Focus"], doc["staffing"]["customer"]) + [""]
    L += ["**Cadence**", ""] + [f"- {c}" for c in doc["staffing"]["cadence"]] + [""]

    if doc["proven_groups"]:
        L += ["### Done in the Workshop", "",
              "Proven live in the session. Carried items moved into the task list above.", ""]
        for g in doc["proven_groups"]:
            L += [f"**{g['title']}**", ""]
            for t in g["proven"]:
                L.append(f"- {t} (proven in workshop)")
            for t in g["carried"]:
                L.append(f"- {t} (carried into the task list above)")
            L.append("")

    L += ["### Mutual Success Plan", ""]
    L += _table(["Objective", "Actions", "Owner", "Target"], doc["mutual_success"]) + [""]

    L += ["### Evaluation Results", "", "**Note:** To be completed during and after the POC.", ""]
    erows = [[g["title"], c["success_criteria"], "", c["status"]]
             for g in doc["scope_groups"] for c in g["rows"] if not c["na"]]
    L += _table(["Pillar / OKR", "Success criteria (target)", "Result", "Status"], erows) + [""]

    L += ["### Resources", ""]
    for label, url in doc["resources"]:
        L.append(f"- [{label}]({url})" if url.startswith("http") else f"- {label} ({url})")
    L += ["", "### Notes", "", "**Note:** Running notes - filled during the POC.", ""]
    return "\n".join(L)
