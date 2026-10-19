from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.models import Base, ContentJob, SEOProject, WorkflowRun, utc_now
from app.storage.retention_manager import RetentionManager


def test_default_retention_is_fifteen_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUDIT_RETENTION_COUNT", raising=False)
    monkeypatch.delenv("CONTENT_RETENTION_COUNT", raising=False)

    retention = RetentionManager()

    assert retention.audit_retention_count == 15
    assert retention.content_retention_count == 15


@pytest.mark.asyncio
async def test_retention_keeps_six_terminal_records_and_active_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, record) -> None:
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessions():
        async with factory() as session:
            yield session

    monkeypatch.setattr("app.storage.retention_manager.get_session", sessions)
    monkeypatch.setattr(
        "app.storage.retention_manager.DATABASE_URL", "postgresql://test"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    now = utc_now()
    async with factory() as session:
        project = SEOProject(name="Example", website_url="https://example.com")
        session.add(project)
        await session.flush()
        for index in range(8):
            path = reports / f"audit_{index}.json"
            path.write_text("{}", encoding="utf-8")
            session.add(
                WorkflowRun(
                    project_id=project.id,
                    status="completed",
                    completed_at=now + timedelta(seconds=index),
                    output_data={"report_path": str(path)},
                )
            )
            session.add(
                ContentJob(
                    project_id=project.id,
                    status="approved",
                    primary_keyword=f"keyword {index}",
                    completed_at=now + timedelta(seconds=index),
                )
            )
        session.add(WorkflowRun(project_id=project.id, status="running"))
        session.add(
            ContentJob(
                project_id=project.id,
                status="writer_running",
                primary_keyword="active",
            )
        )
        await session.commit()

    result = await RetentionManager(
        audit_retention_count=6,
        content_retention_count=6,
        report_directory=reports,
    ).cleanup()
    assert result == {
        "audit_runs_deleted": 2,
        "content_jobs_deleted": 2,
        "report_files_deleted": 2,
    }
    async with factory() as session:
        audits = list((await session.execute(select(WorkflowRun))).scalars())
        jobs = list((await session.execute(select(ContentJob))).scalars())
    assert len(audits) == 7
    assert any(item.status == "running" for item in audits)
    assert len(jobs) == 7
    assert any(item.status == "writer_running" for item in jobs)

    discarded = await RetentionManager(
        audit_retention_count=6,
        content_retention_count=6,
        report_directory=reports,
    ).discard_incomplete()
    assert discarded == {
        "audit_runs_deleted": 1,
        "content_jobs_deleted": 1,
        "report_files_deleted": 0,
    }
    async with factory() as session:
        assert len(list((await session.execute(select(WorkflowRun))).scalars())) == 6
        assert len(list((await session.execute(select(ContentJob))).scalars())) == 6
    await engine.dispose()
