
import asyncio

from app.agents.manager import AgentManager
from app.storage.database import init_db, get_session, close_db
from app.storage.issue_repository import IssueRepository

from tests.test_audit_routing import (
    REPORT_PATH,
    convert_page_findings,
    convert_crawl_errors,
)
import json


async def main():
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"Audit report not found: {REPORT_PATH}"
        )

    # Load the existing audit report.
    with REPORT_PATH.open("r", encoding="utf-8") as file:
        report = json.load(file)

    # Convert findings into structured SEOIssue objects.
    issues = []

    for page in report.get("pages", []):
        issues.extend(convert_page_findings(page))

    issues.extend(convert_crawl_errors(report))

    # Assign each issue to its specialist agent.
    manager = AgentManager()
    manager.route_issues(issues)

    # Initialize the database and create missing tables.
    await init_db()

    repository = IssueRepository()

    try:
        async with get_session() as session:
            # Save all issues in one transaction.
            saved_count = await repository.save_issues(
                session,
                issues,
            )

            await session.commit()

            # Retrieve saved records to verify persistence.
            saved_issues = await repository.get_all_issues(
                session
            )

            # Verify each newly saved issue can be retrieved.
            first_issue = await repository.get_issue_by_id(
                session,
                issues[0].issue_id,
            )

            print("=" * 55)
            print("SEO ISSUE DATABASE PERSISTENCE TEST")
            print("=" * 55)
            print(f"Website: {report.get('website')}")
            print(f"Structured issues: {len(issues)}")
            print(f"Records saved: {saved_count}")
            print(f"Total records in database: {len(saved_issues)}")
            print(
                "First issue retrieved:",
                first_issue is not None,
            )

            assert saved_count == len(issues)
            assert first_issue is not None

            print()
            print("Sample saved records:")

            for issue in saved_issues[:5]:
                print(
                    f"- {issue.issue_type} | "
                    f"{issue.assigned_agent} | "
                    f"{issue.status}"
                )

            print()
            print("All database persistence tests passed.")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())