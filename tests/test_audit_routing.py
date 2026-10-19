
import json
from collections import Counter
from pathlib import Path

from app.agents.manager import AgentManager
from app.models.issue import SEOIssue, IssueCategory, IssueSeverity


REPORT_PATH = Path("data/zeetech_seo_audit.json")


def convert_page_findings(page):
    """Convert a page's audit findings into structured SEO issues."""

    issues = []

    issue_mapping = {
        "Missing H1 heading": {
            "issue_type": "missing_h1",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": (
                "Add a descriptive H1 heading that reflects the page topic."
            ),
        },
        "Duplicate title found": {
            "issue_type": "duplicate_title",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": (
                "Review the title tag and make it unique to this page."
            ),
        },
    }

    for finding in page.get("issues", []):
        if finding == "36 images missing alt text" or (
            finding.endswith("images missing alt text")
        ):
            image_urls = page.get("images_missing_alt", [])

            issues.append(
                SEOIssue(
                    source_agent="website_auditor",
                    category=IssueCategory.CONTENT,
                    issue_type="missing_image_alt",
                    severity=IssueSeverity.LOW,
                    url=page.get("url"),
                    title="Images missing alt text",
                    description=(
                        f"{len(image_urls)} images on this page "
                        "are missing alt text."
                    ),
                    evidence={
                        "image_count": len(image_urls),
                        "image_urls": image_urls,
                    },
                    recommendation=(
                        "Add meaningful alt text to informative images."
                    ),
                )
            )
            continue

        mapped = issue_mapping.get(finding)

        if mapped:
            issues.append(
                SEOIssue(
                    source_agent="website_auditor",
                    category=mapped["category"],
                    issue_type=mapped["issue_type"],
                    severity=mapped["severity"],
                    url=page.get("url"),
                    title=finding,
                    description=f"{finding} on {page.get('url')}",
                    evidence={
                        "title": page.get("title"),
                        "h1_headings": page.get("h1_headings", []),
                        "canonical": page.get("canonical"),
                    },
                    recommendation=mapped["recommendation"],
                )
            )

    return issues


def convert_crawl_errors(report):
    """Convert crawler errors into structured SEO issues."""

    issues = []

    for error in report.get("errors", []):
        url = error.get("url")
        message = error.get("error", "Unknown crawl error")

        issues.append(
            SEOIssue(
                source_agent="website_auditor",
                category=IssueCategory.TECHNICAL_SEO,
                issue_type="sitemap_error",
                severity=IssueSeverity.MEDIUM,
                url=url,
                title="Sitemap crawl error",
                description=message,
                evidence={
                    "error_message": message,
                },
                recommendation=(
                    "Review the sitemap response and verify its format."
                ),
            )
        )

    return issues


def main():
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"Audit report not found: {REPORT_PATH}"
        )

    with REPORT_PATH.open("r", encoding="utf-8") as file:
        report = json.load(file)

    manager = AgentManager()
    all_issues = []

    # Convert findings from every crawled page.
    for page in report.get("pages", []):
        all_issues.extend(convert_page_findings(page))

    # Convert crawler errors.
    all_issues.extend(convert_crawl_errors(report))

    # Assign every issue to a specialist agent.
    manager.route_issues(all_issues)

    # Summarize the results.
    agent_counts = Counter(
        issue.assigned_agent for issue in all_issues
    )

    print("=" * 55)
    print("SEO AUDIT ISSUE ROUTING SUMMARY")
    print("=" * 55)
    print(f"Website: {report.get('website')}")
    print(f"Pages crawled: {report.get('pages_crawled')}")
    print(f"Structured issues created: {len(all_issues)}")
    print()

    print("Issues assigned to agents:")
    for agent, count in sorted(agent_counts.items()):
        print(f"  {agent}: {count}")

    print()
    print("Sample routed issues:")
    for issue in all_issues[:10]:
        print(
            f"- [{issue.issue_type}] "
            f"{issue.title} -> {issue.assigned_agent}"
        )

    print()
    print("Integration test completed successfully.")


if __name__ == "__main__":
    main()