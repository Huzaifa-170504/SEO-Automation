from __future__ import annotations

from typing import Any

from app.models.issue import IssueCategory, IssueSeverity
from app.workflow.orchestrator import convert_crawl_errors, convert_page_findings


def make_page(
    *, url: str = "https://example.com/page", issues: list[str] | None = None
) -> dict[str, Any]:
    return {
        "url": url,
        "title": "Example Page",
        "h1_headings": [],
        "canonical": url,
        "issues": issues or [],
        "images_missing_alt": [],
    }


def test_convert_page_findings_creates_missing_h1_issue() -> None:
    issues = convert_page_findings(make_page(issues=["Missing H1 heading"]))
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_h1"
    assert issues[0].category == IssueCategory.ON_PAGE_SEO
    assert issues[0].severity == IssueSeverity.MEDIUM
    assert issues[0].source_agent == "website_auditor"


def test_convert_page_findings_creates_missing_alt_issue() -> None:
    page = make_page(issues=["2 images missing alt text"])
    page["images_missing_alt"] = [
        "https://example.com/image-1.jpg",
        "https://example.com/image-2.jpg",
    ]
    issues = convert_page_findings(page)
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_image_alt"
    assert issues[0].category == IssueCategory.CONTENT
    assert issues[0].evidence["image_count"] == 2


def test_convert_crawl_errors_creates_sitemap_issue() -> None:
    issues = convert_crawl_errors(
        {
            "errors": [
                {
                    "url": "https://example.com/sitemap.xml",
                    "error": "HTTP 500",
                }
            ]
        }
    )
    assert len(issues) == 1
    assert issues[0].issue_type == "sitemap_error"
    assert issues[0].category == IssueCategory.TECHNICAL_SEO
    assert issues[0].source_agent == "website_auditor"
