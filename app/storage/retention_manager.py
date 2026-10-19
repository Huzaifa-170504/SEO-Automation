from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

from app.storage.database import DATABASE_URL, engine, get_session
from app.storage.models import ContentJob, WorkflowRun

AUDIT_TERMINAL_STATES = {"completed", "failed", "cancelled"}
AUDIT_INCOMPLETE_STATES = {"pending", "running", "auditing", "routing"}
CONTENT_TERMINAL_STATES = {
    "awaiting_review",
    "needs_revision",
    "approved",
    "human_review_required",
    "failed",
    "cancelled",
}
CONTENT_INCOMPLETE_STATES = {
    "pending",
    "strategy_running",
    "writer_running",
    "review_running",
}
DEFAULT_RETENTION_COUNT = 15


class StorageLimitError(RuntimeError):
    pass


class RetentionManager:
    def __init__(
        self,
        audit_retention_count: int | None = None,
        content_retention_count: int | None = None,
        max_database_size_mb: int | None = None,
        report_directory: str | Path = "data/reports",
    ) -> None:
        audit_setting = os.getenv("AUDIT_RETENTION_COUNT")
        content_setting = os.getenv("CONTENT_RETENTION_COUNT")
        self.audit_retention_count = (
            audit_retention_count
            if audit_retention_count is not None
            else (int(audit_setting) if audit_setting else DEFAULT_RETENTION_COUNT)
        )
        self.content_retention_count = (
            content_retention_count
            if content_retention_count is not None
            else (
                int(content_setting) if content_setting else DEFAULT_RETENTION_COUNT
            )
        )
        self.max_database_size_mb = (
            max_database_size_mb
            if max_database_size_mb is not None
            else int(os.getenv("MAX_DATABASE_SIZE_MB", "500"))
        )
        self.report_directory = Path(report_directory).resolve()

    async def cleanup(self) -> dict[str, Any]:
        audit_ids, report_paths = await self._old_audits()
        content_ids = await self._old_content_jobs()

        async with get_session() as session:
            if content_ids:
                await session.execute(
                    delete(ContentJob).where(ContentJob.id.in_(content_ids))
                )
            if audit_ids:
                await session.execute(
                    delete(WorkflowRun).where(WorkflowRun.id.in_(audit_ids))
                )
            await self._delete_orphans(session)
            await session.commit()

        reports_deleted = self._delete_reports(report_paths)
        deleted = len(audit_ids) + len(content_ids)
        if deleted and DATABASE_URL.startswith("sqlite"):
            await self._vacuum()

        return {
            "audit_runs_deleted": len(audit_ids),
            "content_jobs_deleted": len(content_ids),
            "report_files_deleted": reports_deleted,
        }

    async def discard_incomplete(self) -> dict[str, int]:
        """Remove work left incomplete by a prior shutdown before accepting jobs."""
        async with get_session() as session:
            audit_result = await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.status.in_(AUDIT_INCOMPLETE_STATES)
                )
            )
            audits = list(audit_result.scalars())
            content_result = await session.execute(
                select(ContentJob.id).where(
                    ContentJob.status.in_(CONTENT_INCOMPLETE_STATES)
                )
            )
            content_ids = list(content_result.scalars())
            paths = []
            for audit in audits:
                output = audit.output_data or {}
                value = output.get("report_path")
                if isinstance(value, str) and value:
                    paths.append(value)
                else:
                    paths.append(f"data/reports/audit_{audit.id}.json")
            if content_ids:
                await session.execute(
                    delete(ContentJob).where(ContentJob.id.in_(content_ids))
                )
            if audits:
                await session.execute(
                    delete(WorkflowRun).where(
                        WorkflowRun.id.in_([audit.id for audit in audits])
                    )
                )
            await self._delete_orphans(session)
            await session.commit()
        reports_deleted = self._delete_reports(paths)
        return {
            "audit_runs_deleted": len(audits),
            "content_jobs_deleted": len(content_ids),
            "report_files_deleted": reports_deleted,
        }

    async def ensure_capacity(self) -> None:
        if self.database_size_mb() <= self.max_database_size_mb:
            return
        await self.cleanup()
        if self.database_size_mb() > self.max_database_size_mb:
            raise StorageLimitError(
                "Storage limit reached. Cleanup could not free enough database space."
            )

    def database_size_mb(self) -> float:
        path = self._sqlite_path()
        if path is None or not path.exists():
            return 0.0
        total = path.stat().st_size
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                total += sidecar.stat().st_size
        return total / (1024 * 1024)

    async def _old_audits(self) -> tuple[list[int], list[str]]:
        if self.audit_retention_count is None:
            return [], []
        async with get_session() as session:
            result = await session.execute(
                select(WorkflowRun)
                .where(WorkflowRun.status.in_(AUDIT_TERMINAL_STATES))
                .order_by(
                    WorkflowRun.created_at.desc(),
                    WorkflowRun.id.desc(),
                )
                .offset(self.audit_retention_count)
            )
            rows = list(result.scalars())
        paths = []
        for row in rows:
            output = row.output_data or {}
            path = output.get("report_path")
            if isinstance(path, str) and path:
                paths.append(path)
        return [row.id for row in rows], paths

    async def _old_content_jobs(self) -> list[int]:
        if self.content_retention_count is None:
            return []
        async with get_session() as session:
            result = await session.execute(
                select(ContentJob.id)
                .where(ContentJob.status.in_(CONTENT_TERMINAL_STATES))
                .order_by(
                    ContentJob.created_at.desc(),
                    ContentJob.id.desc(),
                )
                .offset(self.content_retention_count)
            )
            return list(result.scalars())

    def _delete_reports(self, paths: list[str]) -> int:
        deleted = 0
        root = self.report_directory
        for value in paths:
            path = Path(value).resolve()
            if root not in path.parents or not path.is_file():
                continue
            path.unlink()
            deleted += 1
        return deleted

    async def _vacuum(self) -> None:
        async with engine.connect() as connection:
            await connection.execute(text("VACUUM"))

    @staticmethod
    async def _delete_orphans(session: Any) -> None:
        statements = (
            (
                "DELETE FROM content_token_usages WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE "
                "content_jobs.id = content_token_usages.content_job_id)"
            ),
            (
                "DELETE FROM content_reviews WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE content_jobs.id = content_reviews.content_job_id) "
                "OR NOT EXISTS (SELECT 1 FROM content_versions WHERE "
                "content_versions.id = content_reviews.content_version_id)"
            ),
            (
                "DELETE FROM content_versions WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE content_jobs.id = content_versions.content_job_id)"
            ),
            (
                "DELETE FROM content_strategies WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE content_jobs.id = content_strategies.content_job_id)"
            ),
            (
                "DELETE FROM content_conversion_links WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE "
                "content_jobs.id = content_conversion_links.content_job_id)"
            ),
            (
                "DELETE FROM content_competitors WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE content_jobs.id = content_competitors.content_job_id)"
            ),
            (
                "DELETE FROM content_keywords WHERE NOT EXISTS "
                "(SELECT 1 FROM content_jobs WHERE content_jobs.id = content_keywords.content_job_id)"
            ),
        )
        for statement in statements:
            await session.execute(text(statement))

    @staticmethod
    def _sqlite_path() -> Path | None:
        prefix = "sqlite+aiosqlite:///"
        if not DATABASE_URL.startswith(prefix):
            return None
        value = DATABASE_URL.removeprefix(prefix)
        return Path(value).resolve()
