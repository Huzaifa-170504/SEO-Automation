from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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
    database_path = tmp_path / "test_storage.db"
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


@pytest.mark.asyncio
async def test_all_storage_tables_are_created(
    test_session: AsyncSession,
) -> None:
    """Verify that all expected storage tables exist."""
    table_names = await test_session.run_sync(
        lambda sync_session: set(
            inspect(sync_session.get_bind()).get_table_names()
        )
    )

    expected_tables = {
        "seo_projects",
        "workflow_runs",
        "agent_executions",
        "token_usages",
        "seo_issues",
    }

    assert expected_tables.issubset(table_names)


@pytest.mark.asyncio
async def test_project_can_be_persisted_and_retrieved(
    test_session: AsyncSession,
) -> None:
    """Verify basic SEO project persistence."""
    project = SEOProject(
        name="Example Project",
        website_url="https://example.com/",
        description="Test SEO project",
    )

    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    assert project.id is not None
    assert project.name == "Example Project"
    assert project.website_url == "https://example.com/"
    assert project.description == "Test SEO project"
    assert project.is_active is True
    assert project.created_at is not None
    assert project.updated_at is not None

    result = await test_session.execute(
        select(SEOProject).where(
            SEOProject.id == project.id,
        )
    )

    stored_project = result.scalar_one()

    assert stored_project.id == project.id
    assert stored_project.name == "Example Project"


@pytest.mark.asyncio
async def test_workflow_run_belongs_to_project(
    test_session: AsyncSession,
) -> None:
    """Verify the project-to-workflow-run relationship."""
    project = SEOProject(
        name="Workflow Test",
        website_url="https://example.com/",
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
        started_at=datetime.now(timezone.utc),
    )

    test_session.add(workflow_run)
    await test_session.commit()
    await test_session.refresh(workflow_run)

    assert workflow_run.id is not None
    assert workflow_run.project_id == project.id
    assert workflow_run.status == "running"

    result = await test_session.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_run.id,
        )
    )

    stored_run = result.scalar_one()

    assert stored_run.project_id == project.id
    assert stored_run.input_data == {
        "website_url": "https://example.com/",
    }


@pytest.mark.asyncio
async def test_agent_execution_belongs_to_workflow_run(
    test_session: AsyncSession,
) -> None:
    """Verify agent execution persistence and relationship."""
    project = SEOProject(
        name="Agent Test",
        website_url="https://example.com/",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="running",
        trigger="manual",
    )

    test_session.add(workflow_run)
    await test_session.flush()

    execution = AgentExecution(
        workflow_run_id=workflow_run.id,
        agent_name="content_strategist",
        status="completed",
        model_name="qwen-seo:4b",
        input_data={
            "issue_type": "missing_h1",
        },
        output_data={
            "status": "approved",
        },
    )

    test_session.add(execution)
    await test_session.commit()
    await test_session.refresh(execution)

    assert execution.id is not None
    assert execution.workflow_run_id == workflow_run.id
    assert execution.agent_name == "content_strategist"
    assert execution.model_name == "qwen-seo:4b"
    assert execution.output_data == {
        "status": "approved",
    }


@pytest.mark.asyncio
async def test_token_usage_can_be_persisted(
    test_session: AsyncSession,
) -> None:
    """Verify token usage and estimated cost persistence."""
    project = SEOProject(
        name="Token Test",
        website_url="https://example.com/",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="running",
    )

    test_session.add(workflow_run)
    await test_session.flush()

    execution = AgentExecution(
        workflow_run_id=workflow_run.id,
        agent_name="content_writer",
        status="completed",
        model_name="qwen-seo:4b",
    )

    test_session.add(execution)
    await test_session.flush()

    usage = TokenUsage(
        workflow_run_id=workflow_run.id,
        agent_execution_id=execution.id,
        provider="ollama",
        model_name="qwen-seo:4b",
        input_tokens=500,
        output_tokens=750,
        total_tokens=1250,
        estimated_cost_usd=Decimal("0"),
    )

    test_session.add(usage)
    await test_session.commit()
    await test_session.refresh(usage)

    assert usage.id is not None
    assert usage.workflow_run_id == workflow_run.id
    assert usage.agent_execution_id == execution.id
    assert usage.provider == "ollama"
    assert usage.model_name == "qwen-seo:4b"
    assert usage.input_tokens == 500
    assert usage.output_tokens == 750
    assert usage.total_tokens == 1250
    assert usage.estimated_cost_usd == Decimal("0")


@pytest.mark.asyncio
async def test_issue_record_can_be_persisted(
    test_session: AsyncSession,
) -> None:
    """Verify complete SEO issue record persistence."""
    project = SEOProject(
        name="Issue Test",
        website_url="https://example.com/",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="running",
    )

    test_session.add(workflow_run)
    await test_session.flush()

    issue = SEOIssueRecord(
        issue_id="test-issue-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        source_agent="website_auditor",
        assigned_agent="content_strategist",
        category="on_page_seo",
        issue_type="missing_h1",
        severity="medium",
        url="https://example.com/page",
        title="Missing H1 heading",
        description="The page does not contain an H1 heading.",
        evidence={
            "h1_headings": [],
        },
        validation_status="pending",
        recommendation="Add a descriptive H1 heading.",
        status="open",
    )

    test_session.add(issue)
    await test_session.commit()
    await test_session.refresh(issue)

    assert issue.id is not None
    assert issue.issue_id == "test-issue-001"
    assert issue.project_id == project.id
    assert issue.workflow_run_id == workflow_run.id
    assert issue.source_agent == "website_auditor"
    assert issue.assigned_agent == "content_strategist"
    assert issue.category == "on_page_seo"
    assert issue.issue_type == "missing_h1"
    assert issue.severity == "medium"
    assert issue.url == "https://example.com/page"
    assert issue.evidence == {
        "h1_headings": [],
    }
    assert issue.validation_status == "pending"
    assert issue.status == "open"


@pytest.mark.asyncio
async def test_relationships_are_available(
    test_session: AsyncSession,
) -> None:
    """Verify the important SQLAlchemy relationships."""
    project = SEOProject(
        name="Relationship Test",
        website_url="https://example.com/",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="completed",
    )

    test_session.add(workflow_run)
    await test_session.flush()

    execution = AgentExecution(
        workflow_run_id=workflow_run.id,
        agent_name="reviewer",
        status="completed",
        model_name="qwen-seo:4b",
    )

    test_session.add(execution)
    await test_session.flush()

    issue = SEOIssueRecord(
        issue_id="relationship-issue-001",
        project_id=project.id,
        workflow_run_id=workflow_run.id,
        source_agent="website_auditor",
        assigned_agent="reviewer",
        category="content",
        issue_type="test_issue",
        severity="low",
        title="Test issue",
        description="Relationship test issue.",
    )

    usage = TokenUsage(
        workflow_run_id=workflow_run.id,
        agent_execution_id=execution.id,
        provider="ollama",
        model_name="qwen-seo:4b",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        estimated_cost_usd=Decimal("0"),
    )

    test_session.add_all(
        [
            issue,
            usage,
        ]
    )

    await test_session.commit()

    workflow_result = await test_session.execute(
        select(WorkflowRun).where(
            WorkflowRun.project_id == project.id,
        )
    )
    project_workflow_runs = list(
        workflow_result.scalars().all()
    )

    execution_result = await test_session.execute(
        select(AgentExecution).where(
            AgentExecution.workflow_run_id == workflow_run.id,
        )
    )
    workflow_executions = list(
        execution_result.scalars().all()
    )

    issue_result = await test_session.execute(
        select(SEOIssueRecord).where(
            SEOIssueRecord.workflow_run_id == workflow_run.id,
        )
    )
    workflow_issues = list(
        issue_result.scalars().all()
    )

    usage_result = await test_session.execute(
        select(TokenUsage).where(
            TokenUsage.workflow_run_id == workflow_run.id,
        )
    )
    workflow_token_usages = list(
        usage_result.scalars().all()
    )

    execution_usage_result = await test_session.execute(
        select(TokenUsage).where(
            TokenUsage.agent_execution_id == execution.id,
        )
    )
    execution_token_usages = list(
        execution_usage_result.scalars().all()
    )

    assert len(project_workflow_runs) == 1
    assert project_workflow_runs[0].id == workflow_run.id

    assert len(workflow_executions) == 1
    assert workflow_executions[0].id == execution.id

    assert len(workflow_issues) == 1
    assert workflow_issues[0].issue_id == "relationship-issue-001"

    assert len(workflow_token_usages) == 1
    assert workflow_token_usages[0].total_tokens == 30

    assert len(execution_token_usages) == 1
    assert execution_token_usages[0].id == usage.id


@pytest.mark.asyncio
async def test_cascade_delete_removes_project_children(
    test_session: AsyncSession,
) -> None:
    """Verify project deletion cascades to owned records."""
    await test_session.execute(
        text("PRAGMA foreign_keys=ON")
    )

    pragma_result = await test_session.execute(
        text("PRAGMA foreign_keys")
    )
    foreign_keys_enabled = pragma_result.scalar_one()

    assert foreign_keys_enabled == 1

    project = SEOProject(
        name="Cascade Test",
        website_url="https://example.com/",
    )

    test_session.add(project)
    await test_session.flush()

    workflow_run = WorkflowRun(
        project_id=project.id,
        status="completed",
    )

    issue = SEOIssueRecord(
        issue_id="cascade-issue-001",
        project_id=project.id,
        source_agent="website_auditor",
        category="technical_seo",
        issue_type="test_issue",
        severity="low",
        title="Cascade test",
        description="Testing cascade behavior.",
    )

    test_session.add_all(
        [
            workflow_run,
            issue,
        ]
    )
    await test_session.flush()

    execution = AgentExecution(
        workflow_run_id=workflow_run.id,
        agent_name="website_auditor",
        status="completed",
    )

    test_session.add(execution)
    await test_session.flush()

    usage = TokenUsage(
        workflow_run_id=workflow_run.id,
        agent_execution_id=execution.id,
        provider="ollama",
        model_name="qwen-seo:4b",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        estimated_cost_usd=Decimal("0"),
    )

    test_session.add(usage)
    await test_session.commit()

    project_id = project.id
    workflow_run_id = workflow_run.id
    execution_id = execution.id
    usage_id = usage.id
    issue_id = issue.issue_id

    await test_session.delete(project)
    await test_session.commit()

    project_result = await test_session.execute(
        select(SEOProject).where(
            SEOProject.id == project_id,
        )
    )

    workflow_result = await test_session.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_run_id,
        )
    )

    execution_result = await test_session.execute(
        select(AgentExecution).where(
            AgentExecution.id == execution_id,
        )
    )

    usage_result = await test_session.execute(
        select(TokenUsage).where(
            TokenUsage.id == usage_id,
        )
    )

    issue_result = await test_session.execute(
        select(SEOIssueRecord).where(
            SEOIssueRecord.issue_id == issue_id,
        )
    )

    assert project_result.scalar_one_or_none() is None
    assert workflow_result.scalar_one_or_none() is None
    assert execution_result.scalar_one_or_none() is None
    assert usage_result.scalar_one_or_none() is None
    assert issue_result.scalar_one_or_none() is None