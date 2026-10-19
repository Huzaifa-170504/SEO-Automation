
from app.agents.manager import AgentManager
from app.models.issue import SEOIssue, IssueCategory


def create_issue(category, issue_type, title):
    return SEOIssue(
        source_agent="website_auditor",
        category=category,
        issue_type=issue_type,
        title=title,
        description=f"Test issue: {title}",
    )


def main():
    manager = AgentManager()

    issues = [
        create_issue(
            IssueCategory.ON_PAGE_SEO,
            "missing_h1",
            "Missing H1 heading",
        ),
        create_issue(
            IssueCategory.ON_PAGE_SEO,
            "missing_image_alt",
            "Missing image alt text",
        ),
        create_issue(
            IssueCategory.KEYWORDS,
            "keyword_gap",
            "Missing target keywords",
        ),
        create_issue(
            IssueCategory.COMPETITORS,
            "competitor_content_gap",
            "Competitor content gap",
        ),
        create_issue(
            IssueCategory.LINKS,
            "broken_internal_link",
            "Broken internal link",
        ),
    ]

    routed_issues = manager.route_issues(issues)

    print("Agent Manager Routing Results")
    print("-" * 40)

    for issue in routed_issues:
        print(f"Issue: {issue.title}")
        print(f"Assigned agent: {issue.assigned_agent}")
        print()

    assert routed_issues[0].assigned_agent == "content_strategist"
    assert routed_issues[1].assigned_agent == "content_writer"
    assert routed_issues[2].assigned_agent == "content_strategist"
    assert routed_issues[3].assigned_agent == "content_strategist"
    assert routed_issues[4].assigned_agent == "website_auditor"

    print("All Agent Manager tests passed.")


if __name__ == "__main__":
    main()
