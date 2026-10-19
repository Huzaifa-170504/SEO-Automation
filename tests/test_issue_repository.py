from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.issue import (
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    SEOIssue,
    ValidationStatus,
)
from app.storage.issue_repository import IssueRepository
from app.storage.models import (
    AgentExecution,
    Base,
    SEOIssueRecord,
    SEOProject,
    TokenUsage,
    WorkflowRun,
)


@pytest_asyncio.fixture
async def test_session(tmp_path: Path):
    """Provide an isolated temporary SQLite database session."""
    database_path = tmp_path / "test_issue_repository.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

    engine = create_async_engine(
        database_url,
        echo=False,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as connection:
        await connection.execute(
            text("PRAGMA foreign_keys=ON")
        )
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            text("PRAGMA foreign_keys=ON")
        )
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def project_and_run(
    test_session: AsyncSession,
) -> tuple[SEOProject, WorkflowRun]:
    """Create a project and workflow run for repository tests."""
    project = SEOProject(
        name="Repository Test Project",
        website_url="https://example.com/",
        description="Issue repository test project",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="running",
        trigger="manual",
        input_data={
            "website_url": "https://example.com/",
        },
    )

    test_session.add(workflow_run)
    await test_session.flush()

    return project, workflow_run


def build_issue(
    *,
    issue_id: str,
    project_id: int,
    workflow_run_id: int,
    assigned_agent: str | None = None,
    category: IssueCategory = IssueCategory.ON_PAGE_SEO,
    issue_type: str = "missing_h1",
    severity: IssueSeverity = IssueSeverity.MEDIUM,
    detected_at: datetime | None = None,
) -> SEOIssue:
    """Build a valid SEO issue for repository tests."""
    issue = SEOIssue(
        issue_id=issue_id,
        project_id=project_id,
        workflow_run_id=workflow_run_id,
        source_agent="website_auditor",
        assigned_agent=assigned_agent,
        category=category,
        issue_type=issue_type,
        severity=severity,
        url="https://example.com/page",
        title="Test SEO issue",
        description="Test SEO issue description.",
        evidence={
            "test": True,
        },
        validation_status=ValidationStatus.PENDING,
        validation_notes=None,
        recommendation="Fix the detected SEO issue.",
        status=IssueStatus.OPEN,
    )

    if detected_at is not None:
        issue.detected_at = detected_at

    return issue


@pytest.mark.asyncio
async def test_save_issues_persists_multiple_issues(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify that multiple SEO issues are persisted correctly."""
    project, workflow_run = project_and_run

    issues = [
        build_issue(
            issue_id="repository-issue-001",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_strategist",
            issue_type="missing_h1",
            severity=IssueSeverity.HIGH,
        ),
        build_issue(
            issue_id="repository-issue-002",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_writer",
            issue_type="missing_image_alt",
            severity=IssueSeverity.MEDIUM,
        ),
    ]

    repository = IssueRepository()

    saved_count = await repository.save_issues(
        test_session,
        issues,
    )

    await test_session.commit()

    assert saved_count == 2

    first = await repository.get_issue_by_id(
        test_session,
        "repository-issue-001",
    )
    second = await repository.get_issue_by_id(
        test_session,
        "repository-issue-002",
    )

    assert first is not None
    assert second is not None

    assert first.issue_id == "repository-issue-001"
    assert first.project_id == project.id
    assert first.workflow_run_id == workflow_run.id
    assert first.source_agent == "website_auditor"
    assert first.assigned_agent == "content_strategist"
    assert first.category == "on_page_seo"
    assert first.issue_type == "missing_h1"
    assert first.severity == "high"
    assert first.status == "open"

    assert second.issue_id == "repository-issue-002"
    assert second.assigned_agent == "content_writer"
    assert second.issue_type == "missing_image_alt"
    assert second.severity == "medium"


@pytest.mark.asyncio
async def test_save_issues_converts_enum_values_to_strings(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify enum values are stored as plain database strings."""
    project, workflow_run = project_and_run

    issue = build_issue(
        issue_id="repository-enum-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        assigned_agent="reviewer",
        category=IssueCategory.CONTENT,
        issue_type="content_gap",
        severity=IssueSeverity.CRITICAL,
    )

    issue.validation_status = ValidationStatus.CONFIRMED
    issue.validation_notes = "Confirmed during repository test."
    issue.status = IssueStatus.IN_PROGRESS
    issue.recommendation = "Improve the content coverage."

    repository = IssueRepository()

    saved_count = await repository.save_issues(
        test_session,
        [issue],
    )

    await test_session.commit()

    assert saved_count == 1

    stored = await repository.get_issue_by_id(
        test_session,
        "repository-enum-001",
    )

    assert stored is not None
    assert stored.category == "content"
    assert stored.severity == "critical"
    assert stored.validation_status == "confirmed"
    assert stored.status == "in_progress"
    assert stored.validation_notes == (
        "Confirmed during repository test."
    )


@pytest.mark.asyncio
async def test_save_issues_returns_zero_for_empty_input(
    test_session: AsyncSession,
) -> None:
    """Verify saving an empty issue collection is a no-op."""
    repository = IssueRepository()

    saved_count = await repository.save_issues(
        test_session,
        [],
    )

    assert saved_count == 0


@pytest.mark.asyncio
async def test_get_issue_by_id_returns_issue(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify retrieving an existing issue by unique issue ID."""
    project, workflow_run = project_and_run

    issue = build_issue(
        issue_id="repository-get-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        assigned_agent="content_strategist",
    )

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        [issue],
    )
    await test_session.commit()

    stored = await repository.get_issue_by_id(
        test_session,
        "repository-get-001",
    )

    assert stored is not None
    assert stored.issue_id == "repository-get-001"
    assert stored.title == "Test SEO issue"
    assert stored.description == "Test SEO issue description."
    assert stored.evidence == {
        "test": True,
    }


@pytest.mark.asyncio
async def test_get_issue_by_id_returns_none_for_unknown_issue(
    test_session: AsyncSession,
) -> None:
    """Verify unknown issue IDs return None."""
    repository = IssueRepository()

    stored = await repository.get_issue_by_id(
        test_session,
        "does-not-exist",
    )

    assert stored is None


@pytest.mark.asyncio
async def test_get_issues_by_agent_filters_correctly(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify issues are filtered by assigned agent."""
    project, workflow_run = project_and_run

    issues = [
        build_issue(
            issue_id="repository-agent-001",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_strategist",
        ),
        build_issue(
            issue_id="repository-agent-002",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_writer",
        ),
        build_issue(
            issue_id="repository-agent-003",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_strategist",
        ),
        build_issue(
            issue_id="repository-agent-004",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="reviewer",
        ),
    ]

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        issues,
    )
    await test_session.commit()

    strategist_issues = await repository.get_issues_by_agent(
        test_session,
        "content_strategist",
    )

    writer_issues = await repository.get_issues_by_agent(
        test_session,
        "content_writer",
    )

    reviewer_issues = await repository.get_issues_by_agent(
        test_session,
        "reviewer",
    )

    assert len(strategist_issues) == 2
    assert {
        issue.issue_id
        for issue in strategist_issues
    } == {
        "repository-agent-001",
        "repository-agent-003",
    }

    assert len(writer_issues) == 1
    assert writer_issues[0].issue_id == "repository-agent-002"

    assert len(reviewer_issues) == 1
    assert reviewer_issues[0].issue_id == "repository-agent-004"


@pytest.mark.asyncio
async def test_get_issues_by_agent_returns_newest_first(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify agent issue results are ordered newest first."""
    project, workflow_run = project_and_run

    base_time = datetime.now(timezone.utc)

    older_issue = build_issue(
        issue_id="repository-order-older",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        assigned_agent="content_strategist",
        detected_at=base_time,
    )

    newer_issue = build_issue(
        issue_id="repository-order-newer",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        assigned_agent="content_strategist",
        detected_at=base_time + timedelta(minutes=5),
    )

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        [
            older_issue,
            newer_issue,
        ],
    )
    await test_session.commit()

    results = await repository.get_issues_by_agent(
        test_session,
        "content_strategist",
    )

    assert len(results) == 2
    assert results[0].issue_id == "repository-order-newer"
    assert results[1].issue_id == "repository-order-older"


@pytest.mark.asyncio
async def test_get_all_issues_returns_all_issues_newest_first(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify all issues are returned in newest-first order."""
    project, workflow_run = project_and_run

    base_time = datetime.now(timezone.utc)

    issues = [
        build_issue(
            issue_id="repository-all-older",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_strategist",
            detected_at=base_time,
        ),
        build_issue(
            issue_id="repository-all-newer",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="reviewer",
            detected_at=base_time + timedelta(minutes=10),
        ),
        build_issue(
            issue_id="repository-all-middle",
            project_id=project.id,
            workflow_run_id=workflow_run.id,
            assigned_agent="content_writer",
            detected_at=base_time + timedelta(minutes=5),
        ),
    ]

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        issues,
    )
    await test_session.commit()

    results = await repository.get_all_issues(
        test_session,
    )

    assert len(results) == 3
    assert [issue.issue_id for issue in results] == [
        "repository-all-newer",
        "repository-all-middle",
        "repository-all-older",
    ]


@pytest.mark.asyncio
async def test_save_issues_preserves_optional_fields(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify nullable issue fields are preserved correctly."""
    project, workflow_run = project_and_run

    issue = SEOIssue(
        issue_id="repository-optional-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        source_agent="website_auditor",
        assigned_agent=None,
        category=IssueCategory.TECHNICAL_SEO,
        issue_type="technical_test",
        severity=IssueSeverity.LOW,
        url=None,
        title="Optional field test",
        description="Testing nullable repository fields.",
        evidence={},
        validation_status=ValidationStatus.PENDING,
        validation_notes=None,
        recommendation=None,
        status=IssueStatus.OPEN,
    )

    repository = IssueRepository()

    saved_count = await repository.save_issues(
        test_session,
        [issue],
    )
    await test_session.commit()

    assert saved_count == 1

    stored = await repository.get_issue_by_id(
        test_session,
        "repository-optional-001",
    )

    assert stored is not None
    assert stored.assigned_agent is None
    assert stored.url is None
    assert stored.validation_notes is None
    assert stored.recommendation is None
    assert stored.evidence == {}


@pytest.mark.asyncio
async def test_repository_persists_validation_and_resolution_timestamps(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify validation and resolution timestamps are persisted."""
    project, workflow_run = project_and_run

    issue = build_issue(
        issue_id="repository-timestamps-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
    )

    issue.confirm("Confirmed by repository test.")
    issue.mark_resolved()

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        [issue],
    )
    await test_session.commit()

    stored = await repository.get_issue_by_id(
        test_session,
        "repository-timestamps-001",
    )

    assert stored is not None
    assert stored.validation_status == "confirmed"
    assert stored.validation_notes == (
        "Confirmed by repository test."
    )
    assert stored.validated_at is not None
    assert stored.status == "resolved"
    assert stored.resolved_at is not None


@pytest.mark.asyncio
async def test_repository_does_not_create_unrelated_records(
    test_session: AsyncSession,
    project_and_run: tuple[SEOProject, WorkflowRun],
) -> None:
    """Verify issue persistence does not create unrelated records."""
    project, workflow_run = project_and_run

    issue = build_issue(
        issue_id="repository-isolation-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        assigned_agent="content_writer",
    )

    repository = IssueRepository()

    await repository.save_issues(
        test_session,
        [issue],
    )
    await test_session.commit()

    execution_result = await test_session.execute(
        select(AgentExecution)
    )

    usage_result = await test_session.execute(
        select(TokenUsage)
    )

    issue_result = await test_session.execute(
        select(SEOIssueRecord)
    )

    assert execution_result.scalars().all() == []
    assert usage_result.scalars().all() == []
    assert len(issue_result.scalars().all()) == 1