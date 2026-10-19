from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.content_repository import ContentRepository
from app.storage.models import (
    Base,
    ContentJob,
    ContentReview,
    ContentStrategy,
    ContentVersion,
    SEOProject,
    WorkflowRun,
    utc_now,
)


@pytest_asyncio.fixture
async def session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'content.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, record) -> None:
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest.mark.asyncio
async def test_content_job_and_children_persist_and_cascade(
    session: AsyncSession,
) -> None:
    project = SEOProject(name="Example", website_url="https://example.com")
    session.add(project)
    await session.flush()
    audit = WorkflowRun(
        project_id=project.id,
        status="completed",
        completed_at=utc_now(),
    )
    session.add(audit)
    await session.commit()

    repository = ContentRepository()
    job = await repository.create_job(
        session,
        project.id,
        audit.id,
        "AI trading bot",
        ["automated trading", "crypto bot"],
        ["https://competitor.example/article"],
        "Best AI Trading Bots",
        conversion_urls={
            "contact": "https://example.com/contact",
            "login": "https://example.com/login",
        },
    )
    loaded = await repository.get_job(session, job.id)
    assert loaded is not None
    assert len(loaded.keywords) == 3
    assert len(loaded.competitors) == 1
    assert {link.link_type for link in loaded.conversion_links} == {"contact", "login"}

    strategy = await repository.save_strategy(session, job.id, {"outline": ["Intro"]})
    version = await repository.save_version(
        session,
        job.id,
        {"title": "AI trading bot", "h1": "AI trading bot", "body": "Useful text"},
    )
    await repository.save_review(
        session, job.id, version.id, {"status": "approved", "issues": []}
    )
    await repository.approve(session, job.id, version.id)
    assert strategy.id is not None
    assert version.word_count == 8

    await session.delete(project)
    await session.commit()
    assert await session.scalar(select(ContentJob.id)) is None
    assert await session.scalar(select(ContentStrategy.id)) is None
    assert await session.scalar(select(ContentVersion.id)) is None
    assert await session.scalar(select(ContentReview.id)) is None


@pytest.mark.asyncio
async def test_latest_completed_audit_ignores_running(session: AsyncSession) -> None:
    project = SEOProject(name="Example", website_url="https://example.com")
    session.add(project)
    await session.flush()
    completed = WorkflowRun(
        project_id=project.id, status="completed", completed_at=utc_now()
    )
    running = WorkflowRun(project_id=project.id, status="running")
    session.add_all([completed, running])
    await session.commit()
    latest = await ContentRepository().latest_completed_audit(session)
    assert latest is not None
    assert latest[1].id == completed.id


@pytest.mark.asyncio
async def test_latest_completed_audit_is_scoped_to_requester(
    session: AsyncSession,
) -> None:
    first = SEOProject(name="First", website_url="https://first.example")
    second = SEOProject(name="Second", website_url="https://second.example")
    session.add_all([first, second])
    await session.flush()
    owned = WorkflowRun(
        project_id=first.id,
        requester_id="user-1",
        status="completed",
        completed_at=utc_now(),
    )
    other = WorkflowRun(
        project_id=second.id,
        requester_id="user-2",
        status="completed",
        completed_at=utc_now(),
    )
    session.add_all([owned, other])
    await session.commit()

    latest = await ContentRepository().latest_completed_audit(session, "user-1")

    assert latest is not None
    assert latest[1].id == owned.id


@pytest.mark.asyncio
async def test_create_job_rejects_another_requesters_audit(
    session: AsyncSession,
) -> None:
    project = SEOProject(name="Example", website_url="https://example.com")
    session.add(project)
    await session.flush()
    audit = WorkflowRun(
        project_id=project.id,
        requester_id="owner",
        status="completed",
        completed_at=utc_now(),
    )
    session.add(audit)
    await session.commit()

    with pytest.raises(ValueError, match="requesting user"):
        await ContentRepository().create_job(
            session,
            project.id,
            audit.id,
            "focused keyword",
            ["related keyword"],
            ["https://competitor.example/article"],
            "Focused topic",
            requester_id="someone-else",
        )
