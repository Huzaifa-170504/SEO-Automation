
from app.models.issue import (
    SEOIssue,
    IssueCategory,
    IssueSeverity,
    ValidationStatus,
    IssueStatus,
)


def main():
    issue = SEOIssue(
        project_id=1,
        workflow_run_id=1,
        source_agent="website_auditor",
        assigned_agent="content_strategist",
        category=IssueCategory.ON_PAGE_SEO,
        issue_type="missing_h1",
        severity=IssueSeverity.MEDIUM,
        url="https://zeetech.pro/",
        title="Missing H1 heading",
        description="The page does not contain an H1 heading.",
        evidence={
            "h1_count": 0,
            "http_status": 200,
        },
    )

    print("Issue model initialized.")
    print("Issue ID:", issue.issue_id)
    print("Category:", issue.category)
    print("Severity:", issue.severity)
    print("Validation:", issue.validation_status)
    print("Status:", issue.status)

    issue.confirm("Verified that the HTML contains no H1 heading.")

    print("\nAfter validation:")
    print("Validation:", issue.validation_status)
    print("Validation notes:", issue.validation_notes)

    issue.recommendation = (
        "Add a descriptive H1 heading that reflects the page topic."
    )

    issue.mark_resolved()

    print("\nAfter resolution:")
    print("Status:", issue.status)
    print("Recommendation:", issue.recommendation)

    assert issue.validation_status == ValidationStatus.CONFIRMED
    assert issue.status == IssueStatus.RESOLVED
    assert issue.validated_at is not None
    assert issue.resolved_at is not None

    print("\nAll issue model tests passed.")


if __name__ == "__main__":
    main()