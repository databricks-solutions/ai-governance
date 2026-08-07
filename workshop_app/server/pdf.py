"""PDF generation for the two leave-behinds: the prerequisites checklist and the outcomes report.

Server-side (reportlab) rather than browser print-to-PDF, so the customer gets a real file with
a real filename and no print dialog — these are documents that get emailed to an account admin
and attached to a POC, not pages someone reads on screen.

reportlab is imported LAZILY inside the builders. It is in requirements.txt, but a Databricks
App that failed to install it should degrade to "PDF unavailable, use the Markdown export"
rather than 500 on a page the room is watching. `available()` reports which it is.

Layout is deliberately plain: one column, generous leading, and checkboxes that survive being
printed and ticked with a pen. The prerequisites PDF is something an SE prints and walks
through with a customer's platform team a week before the session.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

# Databricks palette, matched to the app's Tailwind theme so the PDFs look like the product.
NAVY = "#1B3139"
LAVA = "#FF3621"
MUTED = "#5A6B73"
RULE = "#DDE3E6"


def available() -> tuple[bool, str | None]:
    """(True, None) if reportlab can be imported, else (False, reason)."""
    try:
        import reportlab  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]
    return True, None


def _styles():
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()
    base = ss["BodyText"]
    return {
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20,
                                leading=24, textColor=HexColor(NAVY), spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base, fontName="Helvetica", fontSize=9.5,
                                   leading=13, textColor=HexColor(MUTED), spaceAfter=14),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12.5,
                             leading=15, textColor=HexColor(NAVY), spaceBefore=14,
                             spaceAfter=2),
        "lead": ParagraphStyle("lead", parent=base, fontName="Helvetica-Oblique", fontSize=8.5,
                               leading=11, textColor=HexColor(LAVA), spaceAfter=6),
        "intro": ParagraphStyle("intro", parent=base, fontName="Helvetica", fontSize=9,
                                leading=12.5, textColor=HexColor(MUTED), spaceAfter=8),
        "item": ParagraphStyle("item", parent=base, fontName="Helvetica-Bold", fontSize=9.5,
                               leading=12.5, textColor=HexColor(NAVY), alignment=TA_LEFT),
        "why": ParagraphStyle("why", parent=base, fontName="Helvetica", fontSize=8.5,
                              leading=11.5, textColor=HexColor(MUTED)),
        "note": ParagraphStyle("note", parent=base, fontName="Helvetica", fontSize=8.5,
                               leading=12, textColor=HexColor(MUTED), spaceBefore=10),
    }


def _esc(text: Any) -> str:
    """Escape for reportlab's mini-HTML paragraph markup.

    Customer-edited YAML flows through here, so a stray `&` or `<` must not corrupt the PDF.
    """
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _md_inline(text: Any) -> str:
    """Render the small amount of inline markdown the configs use: `code` and **bold**.

    Escaping happens first, so the markup we emit is the only markup in the output.
    """
    import re
    s = _esc(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", rf'<font face="Courier" color="{NAVY}">\1</font>', s)
    return s


def _checkbox(size: float = 9.5):
    """An empty square that reads as tickable on paper.

    A drawn box rather than the ☐ glyph: the built-in Type-1 fonts have no reliable box
    glyph, and a missing glyph silently renders as a black blob.
    """
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib.colors import HexColor, white

    d = Drawing(size + 2, size + 2)
    d.add(Rect(1, 1, size, size, strokeColor=HexColor(NAVY), fillColor=white, strokeWidth=0.9))
    return d


def _doc(buf, title: str):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=title, author="Databricks", subject="AI Governance Workshop",
    )


def _footer(canvas, doc):
    """Page number plus provenance, so a printed page is traceable to the app that made it."""
    from reportlab.lib.colors import HexColor
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(HexColor(MUTED))
    canvas.drawString(0.75 * 72, 0.45 * 72, "Databricks · AI Governance Workshop")
    canvas.drawRightString(canvas._pagesize[0] - 0.75 * 72, 0.45 * 72, f"Page {doc.page}")
    canvas.restoreState()


def _checklist_row(cb_drawing, item_para, why_para, who_para, widths):
    """One checkbox row: [box] [bold item + why + who]."""
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Table, TableStyle

    right = [[item_para]]
    if why_para:
        right.append([why_para])
    if who_para:
        right.append([who_para])
    inner = Table(right, colWidths=[widths[1]])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    t = Table([[cb_drawing, inner]], colWidths=widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
    ]))
    return t


def prerequisites_pdf(prereqs: dict, customer: str | None = None) -> bytes:
    """The pre-workshop checklist, with real checkboxes to tick.

    Printed and worked through with the customer's platform team about a week out. Every item
    says WHY it matters — an admin who understands the consequence acts faster than one handed
    a bare list of grants.
    """
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, "AI Governance Workshop — Prerequisites")
    avail_w = doc.width
    widths = [0.32 * inch, avail_w - 0.32 * inch]

    story: list[Any] = [
        Paragraph("AI Governance Workshop", S["title"]),
        Paragraph("Prerequisites checklist", S["h2"]),
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    who_for = f"Prepared for {_esc(customer)} · " if customer else ""
    story.append(Paragraph(f"{who_for}Generated {stamp}", S["subtitle"]))

    if prereqs.get("lead_time_note"):
        story.append(Paragraph(_md_inline(prereqs["lead_time_note"]), S["intro"]))

    for g in prereqs.get("groups", []):
        block: list[Any] = [Paragraph(_esc(g.get("title")), S["h2"])]
        if g.get("lead_time"):
            block.append(Paragraph(_esc(g["lead_time"]), S["lead"]))
        if g.get("intro"):
            block.append(Paragraph(_md_inline(g["intro"]), S["intro"]))
        # Keep the heading with its first row so a group never starts alone at a page break.
        items = g.get("items", [])
        if items:
            first = items[0]
            block.append(_row_for(first, S, widths))
            story.append(KeepTogether(block))
            rest = items[1:]
        else:
            story.append(KeepTogether(block))
            rest = []
        for it in rest:
            story.append(_row_for(it, S, widths))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Everything above is checked automatically where possible: <font face='Courier'>"
        "GET /api/health</font> on the deployed app returns "
        "<font face='Courier'>{\"status\":\"ok\",\"config_problems\":[]}</font> when the "
        "configuration side is complete. Items needing an account admin cannot be "
        "self-checked — those are the ones to start early.", S["note"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _row_for(item: dict, S: dict, widths: list) -> Any:
    from reportlab.platypus import Paragraph

    label = _md_inline(item.get("item"))
    if item.get("optional"):
        label += ' <font size="7" color="%s">(SCOPE-DEPENDENT)</font>' % MUTED
    why = Paragraph(_md_inline(item["why"]), S["why"]) if item.get("why") else None
    who = (Paragraph(f'<font size="7.5"><b>Owner:</b> {_esc(item["who"])}</font>', S["why"])
           if item.get("who") else None)
    return _checklist_row(_checkbox(), Paragraph(label, S["item"]), why, who, widths)


def report_pdf(o: dict) -> bytes:
    """The outcomes report: what was proven, what wasn't, and what happens next.

    This is the leave-behind that replaced the POC DOC, so it has to stand on its own in an
    inbox — hence the summary band up top and next steps called out as their own section.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, "AI Governance Workshop — Outcomes")
    avail_w = doc.width

    summary = o.get("summary", {}) or {}
    done, total = summary.get("done", 0), summary.get("total", 0)
    pct = summary.get("pct", 0)

    story: list[Any] = [
        Paragraph("AI Governance Workshop", S["title"]),
        Paragraph("Outcomes report", S["h2"]),
        Paragraph(
            f"Account: <b>{_esc(o.get('customer_name') or o.get('customer_sfid'))}</b> · "
            f"Account ID: <font face='Courier'>{_esc(o.get('customer_sfid'))}</font> · "
            f"Generated {_esc((o.get('generated_at') or '')[:19])}",
            S["subtitle"]),
    ]

    band = Table([[Paragraph(
        f"<b>{done} of {total} steps complete ({pct}%)</b> — "
        f"{total - done} item(s) remain, listed as next steps at the end.", S["item"])]],
        colWidths=[avail_w])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F7F8")),
        ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [band, Spacer(1, 4)]

    widths = [0.32 * inch, avail_w - 0.32 * inch]

    def section(groups: list, heading: str | None = None):
        if heading and any(g.get("steps") for g in groups):
            story.append(Paragraph(_esc(heading), S["h2"]))
        for p in groups:
            steps = p.get("steps", [])
            if not steps:
                continue
            d = sum(1 for s in steps if s.get("complete"))
            block = [Paragraph(f"{_esc(p.get('title'))} — {d}/{len(steps)}", S["h2"])]
            story.append(KeepTogether(block + [_step_row(steps[0], S, widths)]))
            for s in steps[1:]:
                story.append(_step_row(s, S, widths))

    section(o.get("pillars", []))
    section(o.get("accelerators", []), heading="Accelerators (optional add-ons)")

    nxt = o.get("next_steps", [])
    if nxt:
        story.append(Paragraph("Next steps", S["h2"]))
        story.append(Paragraph(
            "Everything not completed in the session. These carry into the 1–2 week "
            "follow-up.", S["intro"]))
        for n in nxt:
            story.append(_checklist_row(
                _checkbox(),
                Paragraph(_md_inline(n.get("title")), S["item"]),
                Paragraph(f'<font size="7.5">{_esc(n.get("pillar_id"))} · '
                          f'status: {_esc(n.get("status"))}</font>', S["why"]),
                None, widths))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "For adopting Unity AI Gateway fresh, or migrating from a previous Databricks or "
        "external gateway, see the detailed field guides: the <b>Adoption Guide</b> and the "
        "<b>Migration Guide</b>.", S["note"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _step_row(step: dict, S: dict, widths: list) -> Any:
    """One step: a ticked or empty box, the title, its status, and any notes."""
    from reportlab.graphics.shapes import Line
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph

    box = _checkbox()
    if step.get("complete"):
        # Draw a check INSIDE the box rather than swapping in a glyph.
        box.add(Line(2.6, 5.4, 4.4, 3.0, strokeColor=HexColor(LAVA), strokeWidth=1.5))
        box.add(Line(4.4, 3.0, 8.2, 8.0, strokeColor=HexColor(LAVA), strokeWidth=1.5))
    status = _esc(step.get("status") or "not started").replace("_", " ")
    meta = f'<font size="7.5">status: {status}</font>'
    if step.get("notes"):
        meta += f'<br/><font size="7.5"><i>notes: {_esc(step["notes"])}</i></font>'
    return _checklist_row(box, Paragraph(_md_inline(step.get("title")), S["item"]),
                          Paragraph(meta, S["why"]), None, widths)
