"""PDF generation for the leave-behinds: the prerequisites checklist, the brochure, and the POC DOC.

Server-side (reportlab) rather than browser print-to-PDF, so the customer gets a real file with
a real filename and no print dialog - these are documents that get emailed to an account admin
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
    """Render the small amount of inline markdown the configs use: `code`, **bold**, *italic*.

    Escaping happens first, so the markup we emit is the only markup in the output. Bold runs
    before italic so `**...**` is consumed before the single-asterisk pass sees it.
    """
    import re
    s = _esc(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(^|[\s(])\*([^*\n]+)\*", r"\1<i>\2</i>", s)
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


def _brochure_footer(canvas, doc):
    """Brochure footer: provenance only, no page number (it is a single-page one-pager)."""
    from reportlab.lib.colors import HexColor
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(HexColor(MUTED))
    canvas.drawString(0.7 * 72, 0.4 * 72, "Databricks · AI Governance Workshop")
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
    says WHY it matters - an admin who understands the consequence acts faster than one handed
    a bare list of grants.
    """
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, "AI Governance Workshop - Prerequisites")
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
        "self-checked - those are the ones to start early.", S["note"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def brochure_pdf(b: dict, customer: str | None = None) -> bytes:
    """The one-page workshop brochure: what it covers, how long, who it's for, accelerators.

    A leave-ahead an account team sends to book the session. Deliberately one page and
    marketing-toned - the substance lives in the app itself and the prerequisites checklist.
    """
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    base = ss["BodyText"]
    st = {
        "title": ParagraphStyle("bt", parent=base, fontName="Helvetica-Bold", fontSize=24,
                                leading=27, textColor=HexColor(NAVY), spaceAfter=3),
        "subtitle": ParagraphStyle("bst", parent=base, fontName="Helvetica", fontSize=11,
                                   leading=15, textColor=HexColor(LAVA), spaceAfter=10),
        "lead": ParagraphStyle("bl", parent=base, fontName="Helvetica", fontSize=9.5,
                               leading=13.5, textColor=HexColor(MUTED), spaceAfter=4),
        # Persona intro sits at the same left inset as the persona rows below it, so the block
        # lines up under the heading instead of the role names hanging out at the page margin.
        "persona_intro": ParagraphStyle("bpi", parent=base, fontName="Helvetica", fontSize=9.5,
                                        leading=13.5, textColor=HexColor(MUTED), spaceAfter=4,
                                        leftIndent=9),
        "h2": ParagraphStyle("bh2", parent=base, fontName="Helvetica-Bold", fontSize=11.5,
                             leading=14, textColor=HexColor(NAVY), spaceBefore=14, spaceAfter=6),
        "pillar_title": ParagraphStyle("bpt", parent=base, fontName="Helvetica-Bold",
                                       fontSize=12, leading=14, textColor=white),
        "pillar_body": ParagraphStyle("bpb", parent=base, fontName="Helvetica", fontSize=8.3,
                                      leading=11, textColor=HexColor(NAVY)),
        "role": ParagraphStyle("br", parent=base, fontName="Helvetica-Bold", fontSize=8.7,
                               leading=11, textColor=HexColor(NAVY)),
        "role_val": ParagraphStyle("brv", parent=base, fontName="Helvetica", fontSize=8.3,
                                   leading=11, textColor=HexColor(MUTED)),
        "acc": ParagraphStyle("bacc", parent=base, fontName="Helvetica", fontSize=8.7,
                              leading=12, textColor=HexColor(NAVY), alignment=TA_LEFT),
        "acc_bullet": ParagraphStyle("baccb", parent=base, fontName="Helvetica", fontSize=8.7,
                                     leading=12, textColor=HexColor(NAVY), leftIndent=12,
                                     bulletIndent=2, spaceBefore=3),
        "acc_h": ParagraphStyle("bacch", parent=base, fontName="Helvetica-Bold", fontSize=10.5,
                                leading=13, textColor=HexColor(NAVY), spaceAfter=3),
        "note": ParagraphStyle("bn", parent=base, fontName="Helvetica-Oblique", fontSize=7.8,
                               leading=10.5, textColor=HexColor(MUTED), spaceBefore=12),
        "meta": ParagraphStyle("bm", parent=base, fontName="Helvetica-Bold", fontSize=9,
                               leading=12, textColor=HexColor(NAVY)),
    }

    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import SimpleDocTemplate
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title="AI Governance Workshop", author="Databricks", subject="AI Governance Workshop",
    )
    avail_w = doc.width

    story: list[Any] = [Paragraph(_esc(b.get("title", "AI Governance Workshop")), st["title"])]
    if b.get("subtitle"):
        story.append(Paragraph(_md_inline(b["subtitle"]), st["subtitle"]))

    # Duration + format band - the two facts a reader scans for first.
    meta_bits = [x for x in (b.get("duration"), b.get("format")) if x]
    if meta_bits:
        meta = Table([[Paragraph(" &nbsp;·&nbsp; ".join(_esc(m) for m in meta_bits), st["meta"])]],
                     colWidths=[avail_w])
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F7F8")),
            ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [meta, Spacer(1, 8)]

    if customer:
        story.append(Paragraph(f"Prepared for <b>{_esc(customer)}</b>", st["lead"]))
    if b.get("lead"):
        story.append(Paragraph(_md_inline(b["lead"]), st["lead"]))

    # Three pillars as a 3-column card row: navy title cell over a white blurb cell.
    pillars = b.get("pillars", [])[:3]
    if pillars:
        story.append(Paragraph("What we'll cover", st["h2"]))
        titles = [Paragraph(_esc(p.get("title")), st["pillar_title"]) for p in pillars]
        blurbs = [Paragraph(_md_inline(p.get("blurb")), st["pillar_body"]) for p in pillars]
        n = len(pillars)
        col_w = [avail_w / n] * n
        pt = Table([titles, blurbs], colWidths=col_w)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), HexColor(NAVY)),
            ("BACKGROUND", (0, 1), (-1, 1), white),
            ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
            ("INNERGRID", (0, 0), (-1, -1), 3, white),  # white gutters between cards
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ("TOPPADDING", (0, 1), (-1, 1), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ]
        pt.setStyle(TableStyle(style))
        story.append(pt)

    # Personas - two columns: bold role, muted why-they're-here.
    personas = b.get("personas", [])
    if personas:
        story.append(Paragraph("Who it's for", st["h2"]))
        if b.get("personas_intro"):
            story.append(Paragraph(_md_inline(b["personas_intro"]), st["persona_intro"]))
            story.append(Spacer(1, 2))
        # Support both the {role, value} dict form and a bare-string role.
        rows = []
        for p in personas:
            role = p if isinstance(p, str) else (p.get("role") or "")
            value = "" if isinstance(p, str) else (p.get("value") or "")
            rows.append([Paragraph(_md_inline(role), st["role"]),
                         Paragraph(_md_inline(value), st["role_val"])])
        pers = Table(rows, colWidths=[2.3 * inch, avail_w - 2.3 * inch])
        pers.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor(RULE)),
        ]))
        story.append(pers)

    # Accelerators, closing the page in a tinted band: an intro line + one bullet each.
    acc = b.get("accelerators", {}) or {}
    items = acc.get("items", [])
    if items or acc.get("intro") or acc.get("body"):
        story.append(Spacer(1, 12))
        cell = [Paragraph(_esc(acc.get("title", "Accelerators")), st["acc_h"])]
        if acc.get("intro") or acc.get("body"):
            cell.append(Paragraph(_md_inline(acc.get("intro") or acc.get("body")), st["acc"]))
        for it in items:
            cell.append(Paragraph(_md_inline(it), st["acc_bullet"], bulletText="•"))
        band = Table([[cell]], colWidths=[avail_w])
        band.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FBEDEA")),  # faint lava tint
            ("BOX", (0, 0), (-1, -1), 0.4, HexColor("#F3C9C0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(band)

    # "Let's go" - the closing flow from interested to booked: numbered steps in a navy band.
    lg = b.get("lets_go", {}) or {}
    lg_steps = lg.get("steps", [])
    if lg_steps:
        story.append(Spacer(1, 12))
        cell = [Paragraph(_esc(lg.get("title", "Let's go")), st["acc_h"])]
        if lg.get("intro"):
            cell.append(Paragraph(_md_inline(lg["intro"]), st["acc"]))
        for n, it in enumerate(lg_steps, 1):
            cell.append(Paragraph(_md_inline(it), st["acc_bullet"], bulletText=f"{n}."))
        band = Table([[cell]], colWidths=[avail_w])
        band.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F7F8")),
            ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(band)

    if b.get("footer_note"):
        story.append(Paragraph(_md_inline(b["footer_note"]), st["note"]))

    # One-pager, so the footer carries provenance but no page number.
    doc.build(story, onFirstPage=_brochure_footer, onLaterPages=_brochure_footer)
    return buf.getvalue()


def _row_for(item: dict, S: dict, widths: list) -> Any:
    from reportlab.platypus import Paragraph

    label = _md_inline(item.get("item"))
    if item.get("optional"):
        label += ' <font size="7" color="%s">(SCOPE-DEPENDENT)</font>' % MUTED
    why = Paragraph(_md_inline(item["why"]), S["why"]) if item.get("why") else None
    who = (Paragraph(f'<font size="7.5"><b>Persona:</b> {_esc(item["who"])}</font>', S["why"])
           if item.get("who") else None)
    return _checklist_row(_checkbox(), Paragraph(label, S["item"]), why, who, widths)


def _poc_cell_styles():
    """Paragraph styles for POC-table cells: body, bold header, and a muted small variant."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()["BodyText"]
    return {
        "cell": ParagraphStyle("pc", parent=base, fontName="Helvetica", fontSize=8.3,
                               leading=11, textColor=HexColor(NAVY)),
        "cell_head": ParagraphStyle("pch", parent=base, fontName="Helvetica-Bold", fontSize=8.3,
                                    leading=11, textColor=HexColor(NAVY)),
        "cell_muted": ParagraphStyle("pcm", parent=base, fontName="Helvetica", fontSize=8,
                                     leading=10.5, textColor=HexColor(MUTED)),
    }


def _poc_table(headers, rows, widths, group_rows, C):
    """A POC table with a tinted header, striped group/phase rows spanned full-width.

    `rows` is a list of cell-lists; `group_rows` is the set of row indices (0-based, data rows)
    that are spanned group/phase headers (bold, tinted).
    """
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph, Table, TableStyle

    # All cell text runs through _md_inline (which _esc-escapes first), so an & / < / > in a
    # customer name, step title, note, or objective cannot corrupt reportlab's paragraph parser.
    # Header text is additionally wrapped white (a Paragraph's own colour wins over TableStyle).
    head = [Paragraph(f'<font color="#FFFFFF">{_esc(h)}</font>', C["cell_head"]) for h in headers]
    body = [head]
    for ri, r in enumerate(rows):
        if ri in group_rows:
            # One spanned cell carries the group label; pad the rest so the row has ncols cells.
            body.append([Paragraph(_md_inline(r[0]), C["cell_head"])] + [""] * (len(headers) - 1))
        else:
            body.append([Paragraph(_md_inline(c), C["cell"]) if c else "" for c in r])
    t = Table(body, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(NAVY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
        ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for ri in group_rows:
        style.append(("SPAN", (0, ri + 1), (-1, ri + 1)))
        style.append(("BACKGROUND", (0, ri + 1), (-1, ri + 1), HexColor("#EEF2F3")))
    t.setStyle(TableStyle(style))
    return t


def report_pdf(doc_data: dict) -> bytes:
    """The AI Governance **POC DOC** as a PDF.

    Consumes the structured dict from `poc.build_poc_doc`, so it renders exactly the same
    sections (header, contacts, scope & success criteria, tasks & timeline, staffing, outcomes,
    mutual success plan, evaluation, resources) as the Markdown export and the Google-Doc template.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

    S = _styles()
    C = _poc_cell_styles()
    buf = io.BytesIO()
    pdoc = _doc(buf, f"AI Governance POC DOC - {doc_data.get('customer', '')}")
    W = pdoc.width

    story: list[Any] = [
        Paragraph(_esc(doc_data["title"]), S["title"]),
        Paragraph(_esc(doc_data["subtitle"]), S["h2"]),
    ]
    if doc_data.get("generated_at"):
        story.append(Paragraph(
            f"Generated {_esc(str(doc_data['generated_at'])[:19])} from the AI Governance "
            "Workshop app", S["subtitle"]))
    story.append(Paragraph(_md_inline(doc_data["intro"]), S["intro"]))

    # Summary band - the one-line progress read.
    band = Table([[Paragraph(_md_inline(doc_data["summary"]["line"]), S["item"])]], colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F7F8")),
        ("BOX", (0, 0), (-1, -1), 0.4, HexColor(RULE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [Spacer(1, 2), band, Spacer(1, 4)]

    def h2(text):
        story.append(Paragraph(_esc(text), S["h2"]))

    def small_table(headers, rows, widths):
        return _poc_table(headers, rows, widths, set(), C)

    # Key Contacts
    h2("Key Contacts")
    story.append(Paragraph("<b>Databricks</b>", C["cell"]))
    story.append(small_table(["Name", "Role"], doc_data["contacts"]["databricks"], [W * 0.4, W * 0.6]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>{_esc(doc_data['customer'])}</b>", C["cell"]))
    story.append(small_table(["Name", "Title / Role"], doc_data["contacts"]["customer"],
                             [W * 0.4, W * 0.6]))

    # Summary & Scope (the narrative lives in the intro + band; this is the scope statement)
    h2("Executive Alignment")
    story.append(Paragraph(
        "[Date]: [Customer exec] ([title]) and [Databricks exec] ([title]) - [purpose]", S["intro"]))

    # Governance Objectives
    h2("Governance Objectives")
    for o in doc_data["objectives"]:
        story.append(Paragraph(f"<b>{_esc(o['title'])}</b> - {_md_inline(o['text'])}", S["intro"]))

    # POC Scope & Success Criteria
    h2("POC Scope & Success Criteria")
    rows, group_rows = [], set()
    for g in doc_data["scope_groups"]:
        group_rows.add(len(rows))
        rows.append([f"{g['title']} - {g['objective']}"])
        for r in g["rows"]:
            rows.append([r["okr"], r["success_criteria"], r["status"]])
    story.append(_poc_table(["OKR", "Success criteria", "Status"], rows,
                            [W * 0.34, W * 0.49, W * 0.17], group_rows, C))

    # Tasks and Timeline
    h2("Tasks and Timeline")
    story.append(Paragraph(
        "Everything not proven in the workshop, as a tracked punch list. <b>Add to POC</b> items "
        "from the room are listed first in each section.", S["intro"]))
    trows, tgroup = [], set()
    for g in doc_data["task_groups"]:
        tgroup.add(len(trows))
        trows.append([g["phase"]])
        for r in g["rows"]:
            task = r["task"] + ("  -  **Add to POC**" if r.get("poc") else "")
            trows.append([task, "", "", r.get("comments", ""), "", r.get("status", "")])
    story.append(_poc_table(
        ["Task", f"{doc_data['customer']} owner", "Databricks owner", "Comments", "Due", "Status"],
        trows, [W * 0.3, W * 0.12, W * 0.14, W * 0.21, W * 0.1, W * 0.13], tgroup, C))

    # Staffing
    h2("POC Staffing Plan")
    story.append(Paragraph("<b>Databricks</b>", C["cell"]))
    story.append(small_table(["Name", "Role", "Focus"], doc_data["staffing"]["databricks"],
                             [W * 0.3, W * 0.25, W * 0.45]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>{_esc(doc_data['customer'])}</b>", C["cell"]))
    story.append(small_table(["Name", "Role", "Focus"], doc_data["staffing"]["customer"],
                             [W * 0.3, W * 0.25, W * 0.45]))
    story.append(Spacer(1, 4))
    for c in doc_data["staffing"]["cadence"]:
        story.append(Paragraph(f"• {_esc(c)}", C["cell"]))

    # Workshop Outcomes
    if doc_data["proven_groups"]:
        h2("Done in the Workshop")
        for g in doc_data["proven_groups"]:
            lines = [Paragraph(f"<b>{_esc(g['title'])}</b>", C["cell"])]
            for t in g["proven"]:
                lines.append(Paragraph(f'<font color="{LAVA}">✓</font> {_esc(t)}', C["cell"]))
            for t in g["carried"]:
                lines.append(Paragraph(f"– {_esc(t)} <i>(carried into the task list)</i>",
                                       C["cell_muted"]))
            story.append(KeepTogether(lines + [Spacer(1, 3)]))

    # Mutual Success Plan
    h2("Mutual Success Plan")
    story.append(small_table(["Objective", "Actions", "Owner", "Target"], doc_data["mutual_success"],
                             [W * 0.24, W * 0.44, W * 0.16, W * 0.16]))

    # Evaluation Results
    h2("Evaluation Results")
    story.append(Paragraph("<i>To be completed during and after the POC.</i>", S["intro"]))
    erows = [[g["title"], c["success_criteria"], "", c["status"]]
             for g in doc_data["scope_groups"] for c in g["rows"] if not c["na"]]
    story.append(small_table(["Pillar / OKR", "Success criteria (target)", "Result", "Status"],
                             erows, [W * 0.22, W * 0.44, W * 0.17, W * 0.17]))

    # Resources
    h2("Resources")
    for label, url in doc_data["resources"]:
        story.append(Paragraph(f"• {_esc(label)} - {_esc(url)}", C["cell"]))

    h2("Notes")
    story.append(Paragraph("<i>Running notes - filled during the POC.</i>", S["intro"]))

    pdoc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
