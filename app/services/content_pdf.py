from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _paragraphs(value: Any, style: ParagraphStyle) -> list[Any]:
    """Render nested saved data without exposing a machine-oriented JSON attachment."""
    if value is None or value == "" or value == [] or value == {}:
        return [Paragraph("Not available", style)]
    if isinstance(value, dict):
        flowables: list[Any] = []
        for key, item in value.items():
            label = str(key).replace("_", " ").title()
            if isinstance(item, (dict, list)):
                flowables.append(Paragraph(f"<b>{escape(label)}</b>", style))
                flowables.extend(_paragraphs(item, style))
            else:
                flowables.append(
                    Paragraph(f"<b>{escape(label)}:</b> {escape(_text(item))}", style)
                )
        return flowables
    if isinstance(value, list):
        flowables = []
        for item in value:
            if isinstance(item, (dict, list)):
                flowables.extend(_paragraphs(item, style))
                flowables.append(Spacer(1, 2 * mm))
            else:
                flowables.append(Paragraph(f"&#8226; {escape(_text(item))}", style))
        return flowables
    lines = str(value).splitlines() or [str(value)]
    return [Paragraph(escape(line) or "&nbsp;", style) for line in lines]


def build_content_pdf(payload: dict[str, Any]) -> BytesIO:
    """Create one human-readable PDF containing research, strategy, drafts, and reviews."""
    job_id = int(payload["job_id"])
    output = BytesIO()
    output.name = f"content_{job_id}_results.pdf"
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"SEO Content Report #{job_id}",
        author="SEO Automation",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ContentBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        wordWrap="CJK",
        spaceAfter=3,
    )
    section = ParagraphStyle(
        "ContentSection",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#17324D"),
        fontSize=16,
        leading=20,
        spaceAfter=7,
    )
    subsection = ParagraphStyle(
        "ContentSubsection",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#2A5276"),
        fontSize=12,
        leading=15,
        spaceAfter=5,
    )
    story: list[Any] = [
        Paragraph("SEO Content Report", styles["Title"]),
        Spacer(1, 3 * mm),
    ]
    summary = Table(
        [
            ["Content job", f"#{job_id}", "Status", _text(payload.get("status")).title()],
            ["Website", _text(payload.get("website")), "Primary keyword", _text(payload.get("primary_keyword"))],
        ],
        colWidths=[28 * mm, 58 * mm, 30 * mm, 56 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF3F8")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD6E2")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([summary, Spacer(1, 7 * mm)])

    story.append(Paragraph("Page research, comparison, and content strategy", section))
    story.extend(_paragraphs(payload.get("strategy"), body))
    story.append(PageBreak())
    story.append(Paragraph("Generated drafts", section))
    drafts = payload.get("drafts") or []
    if not drafts:
        story.append(Paragraph("No generated draft is available.", body))
    for draft in drafts:
        story.append(Paragraph(f"Draft {escape(_text(draft.get('version')))}", subsection))
        story.extend(_paragraphs(draft, body))
        story.append(Spacer(1, 5 * mm))

    story.append(PageBreak())
    story.append(Paragraph("Review results", section))
    story.extend(_paragraphs(payload.get("reviews"), body))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Final content", section))
    story.extend(_paragraphs(payload.get("final_content"), body))

    document.build(story)
    output.seek(0)
    return output
