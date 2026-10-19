from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.web.models import AuditSummary, DemoAuditResult, DemoIssue, DemoPage


def build_sample_audit() -> DemoAuditResult:
    created = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    return DemoAuditResult(
        audit_id=UUID("83c6eb08-e390-45fb-a291-a85c748fe935"),
        website_url="https://example.com/",
        created_at=created,
        expires_at=created + timedelta(days=3650),
        summary=AuditSummary(
            pages_discovered=8,
            pages_crawled=8,
            pages_failed=0,
            issue_count=5,
            severity_counts={"high": 1, "medium": 3, "low": 1},
        ),
        issues=[
            DemoIssue(
                issue_id="sample-1",
                severity="high",
                category="indexability",
                issue_type="noindex_page",
                title="Page has a noindex robots directive",
                description="A service page intended for search is excluded from indexing.",
                url="https://example.com/services/technical-seo",
                recommendation="Remove noindex if this page should appear in search results.",
                assigned_agent="website_auditor",
            ),
            DemoIssue(
                issue_id="sample-2",
                severity="medium",
                category="on_page_seo",
                issue_type="missing_meta_description",
                title="Missing meta description",
                description="The page does not provide a search-result description.",
                url="https://example.com/guides/site-audits",
                recommendation="Add a specific description that reflects the page intent.",
                assigned_agent="content_strategist",
            ),
            DemoIssue(
                issue_id="sample-3",
                severity="medium",
                category="on_page_seo",
                issue_type="duplicate_title",
                title="Duplicate title found",
                description="Two pages use the same title and compete for the same intent.",
                url="https://example.com/services/content",
                recommendation="Give each page a unique title aligned with its purpose.",
                assigned_agent="content_strategist",
            ),
            DemoIssue(
                issue_id="sample-4",
                severity="medium",
                category="on_page_seo",
                issue_type="missing_h1",
                title="Missing H1 heading",
                description="The page has no primary visible heading.",
                url="https://example.com/about",
                recommendation="Add one descriptive H1 matching the page topic.",
                assigned_agent="content_strategist",
            ),
            DemoIssue(
                issue_id="sample-5",
                severity="low",
                category="content",
                issue_type="missing_image_alt",
                title="Images missing alt text",
                description="Three informative images do not have alternative text.",
                url="https://example.com/case-studies",
                recommendation="Add concise, meaningful alt text to informative images.",
                assigned_agent="content_writer",
            ),
        ],
        pages=[
            DemoPage(
                url="https://example.com/",
                status_code=200,
                title="Example SEO Studio",
                meta_description="Evidence-led SEO audits and content strategy.",
                h1_headings=["SEO decisions backed by evidence"],
                canonical="https://example.com/",
                image_count=4,
                internal_link_count=12,
                external_link_count=2,
                word_count=684,
                language="en",
            )
        ],
        warnings=[
            "Illustrative sample data — run a live audit for current website evidence."
        ],
    )
