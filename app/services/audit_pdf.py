from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
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

ISSUE_HELP: dict[str, tuple[str, str, str]] = {
    "Missing title": (
        "High",
        "HTML title element",
        "Add a unique, descriptive title of approximately 30-60 characters.",
    ),
    "Title longer than 60 characters": (
        "Low",
        "HTML title element",
        "Shorten the title while retaining the page's primary topic.",
    ),
    "Missing meta description": (
        "Medium",
        "HTML meta description element",
        "Add a specific, persuasive meta description for this page.",
    ),
    "Meta description longer than 160 characters": (
        "Low",
        "HTML meta description element",
        "Rewrite the description to communicate the main benefit concisely.",
    ),
    "Missing H1 heading": (
        "Medium",
        "Page H1 heading",
        "Add one descriptive H1 that matches the page's main intent.",
    ),
    "Multiple H1 headings": (
        "Medium",
        "Page H1 headings",
        "Keep one primary H1 and use H2/H3 for subordinate headings.",
    ),
    "Missing canonical tag": (
        "Medium",
        "HTML canonical link element",
        "Add a self-referencing canonical or the intended preferred URL.",
    ),
    "Page has a noindex robots directive": (
        "High",
        "HTML robots meta element",
        "Remove noindex if the page should be searchable; otherwise confirm it is intentional.",
    ),
    "Duplicate title found": (
        "Medium",
        "HTML title element",
        "Give this page a unique title aligned with its specific search intent.",
    ),
}


def _plain(value: Any) -> str:
    return " ".join(str(value or "").split())


def _issue_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    structured = report.get("issue_details") or []
    if structured:
        rows = []
        for issue in structured:
            evidence = issue.get("evidence") or {}
            locations = evidence.get("image_urls") or []
            location = ", ".join(map(str, locations)) or _plain(issue.get("url"))
            rows.append(
                {
                    "title": _plain(issue.get("title") or issue.get("issue_type")),
                    "priority": _plain(issue.get("severity") or "medium").title(),
                    "nature": _plain(issue.get("category") or "SEO").replace("_", " ").title(),
                    "page": _plain(issue.get("url")) or "Unknown URL",
                    "location": location or "Page source or content",
                    "impact": _plain(issue.get("description")),
                    "action": _plain(issue.get("recommendation")),
                }
            )
        return rows

    rows = []
    for page in report.get("pages") or []:
        for raw_finding in page.get("issues") or []:
            finding = _plain(raw_finding)
            if finding.endswith("images missing alt text"):
                priority = "Low"
                location = ", ".join(map(str, page.get("images_missing_alt") or []))
                action = "Add meaningful alt text to informative images."
                nature = "Accessibility / Image SEO"
            elif finding.startswith("HTTP error"):
                priority, location, action = (
                    "High",
                    "HTTP response",
                    "Restore the page or redirect it to the most relevant working URL.",
                )
                nature = "Technical SEO"
            else:
                priority, location, action = ISSUE_HELP.get(
                    finding,
                    ("Medium", "Page source or content", "Review and correct the affected element."),
                )
                nature = "On-page / Technical SEO"
            rows.append(
                {
                    "title": finding,
                    "priority": priority,
                    "nature": nature,
                    "page": _plain(page.get("url")) or "Unknown URL",
                    "location": location or "Page source or content",
                    "impact": "This issue can reduce search visibility, clarity, accessibility, or crawlability.",
                    "action": action,
                }
            )
    for error in report.get("errors") or []:
        rows.append(
            {
                "title": "Crawl error",
                "priority": "Medium",
                "nature": "Crawlability / Technical SEO",
                "page": _plain(error.get("url")) or "Unknown URL",
                "location": "HTTP request, robots rule, or sitemap discovery",
                "impact": f"The auditor could not inspect this URL: {_plain(error.get('error'))}",
                "action": "Verify the URL, server response, robots rules, and sitemap entry.",
            }
        )
    return rows


def build_audit_pdf(
    report: dict[str, Any],
    audit_id: int | str,
    website_url: str,
    completed_at: datetime | None,
) -> BytesIO:
    """Create a clear, paginated PDF audit report for a non-technical reader."""
    output = BytesIO()
    output.name = f"seo_audit_{audit_id}.pdf"
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"SEO Audit #{audit_id} - {website_url}",
        author="SEO Automation",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AuditTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#17324D"),
        alignment=TA_CENTER,
        fontSize=21,
        leading=25,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "IssueHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#17324D"),
        fontSize=12,
        leading=15,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "AuditBody",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=13,
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "AuditSmall", parent=body_style, fontSize=8.5, textColor=colors.HexColor("#44546A")
    )
    finished = completed_at or datetime.now(timezone.utc)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    generated = finished.astimezone(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    issues = _issue_rows(report)
    story: list[Any] = [
        Paragraph("SEO Audit Report", title_style),
        Paragraph(escape(website_url), styles["Heading2"]),
        Spacer(1, 3 * mm),
    ]
    summary = Table(
        [
            ["Audit ID", f"#{audit_id}", "Completed", generated],
            ["Pages crawled", str(report.get("pages_crawled", 0)), "Issues found", str(len(issues))],
        ],
        colWidths=[30 * mm, 30 * mm, 34 * mm, 78 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF3F8")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#17324D")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD6E2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([summary, Spacer(1, 7 * mm), Paragraph("Issues and recommended actions", styles["Heading1"])])
    if not issues:
        story.append(Paragraph("No issues were detected by the current audit checks.", body_style))
    for index, issue in enumerate(issues, 1):
        if index > 1 and (index - 1) % 5 == 0:
            story.append(PageBreak())
        story.extend(
            [
                Paragraph(f"{index}. {escape(issue['title'])}", heading_style),
                Paragraph(
                    f"<b>Priority:</b> {escape(issue['priority'])} &nbsp;&nbsp; "
                    f"<b>Nature:</b> {escape(issue['nature'])}",
                    body_style,
                ),
                Paragraph(f"<b>Affected page:</b> {escape(issue['page'])}", small_style),
                Paragraph(f"<b>Exact location:</b> {escape(issue['location'])}", small_style),
                Paragraph(f"<b>Why it matters:</b> {escape(issue['impact'])}", body_style),
                Paragraph(f"<b>Recommended action:</b> {escape(issue['action'])}", body_style),
                Spacer(1, 5 * mm),
            ]
        )
    document.build(story)
    output.seek(0)
    return output
