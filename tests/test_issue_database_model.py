
from app.storage.models import Base, SEOIssueRecord


def main():
    assert "seo_issues" in Base.metadata.tables

    table = Base.metadata.tables["seo_issues"]

    expected_columns = {
        "id",
        "issue_id",
        "project_id",
        "workflow_run_id",
        "source_agent",
        "assigned_agent",
        "category",
        "issue_type",
        "severity",
        "url",
        "title",
        "description",
        "evidence",
        "validation_status",
        "validation_notes",
        "recommendation",
        "status",
        "detected_at",
        "validated_at",
        "resolved_at",
    }

    actual_columns = set(table.columns.keys())

    missing = expected_columns - actual_columns

    assert not missing, f"Missing columns: {missing}"

    issue = SEOIssueRecord(
         issue_id="test-issue-001",
         source_agent="website_auditor",
         assigned_agent="content_strategist",
         category="on_page_seo",
         issue_type="missing_h1",
         severity="medium",
         url="https://zeetech.pro/",
         title="Missing H1 heading",
         description="The page does not contain an H1 heading.",
         evidence={"h1_count": 0},
         recommendation="Add a descriptive H1 heading.",
         status="open",
         validation_status="pending",
    )

    assert issue.issue_id == "test-issue-001"
    assert issue.status == "open"
    assert issue.validation_status == "pending"

    print("SEOIssueRecord model initialized.")
    print(f"Table: {SEOIssueRecord.__tablename__}")
    print(f"Columns verified: {len(actual_columns)}")
    print("All database model tests passed.")


if __name__ == "__main__":
    main()