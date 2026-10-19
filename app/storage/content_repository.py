from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_runtime_config
from app.storage.models import (
    ContentCompetitor,
    ContentConversionLink,
    ContentJob,
    ContentKeyword,
    ContentReview,
    ContentStrategy,
    ContentTokenUsage,
    ContentVersion,
    SEOProject,
    WorkflowRun,
    utc_now,
)


class ContentRepository:
    async def list_completed_audits(
        self, session: AsyncSession, requester_id: str, limit: int = 10
    ) -> list[tuple[SEOProject, WorkflowRun]]:
        """Return the requester's latest completed audit for each website."""
        result = await session.execute(
            select(SEOProject, WorkflowRun)
            .join(WorkflowRun, WorkflowRun.project_id == SEOProject.id)
            .where(
                WorkflowRun.status == "completed",
                WorkflowRun.requester_id == requester_id,
            )
            .order_by(WorkflowRun.completed_at.desc(), WorkflowRun.id.desc())
        )
        rows: list[tuple[SEOProject, WorkflowRun]] = []
        seen_projects: set[int] = set()
        for project, audit in result.all():
            if project.id in seen_projects:
                continue
            seen_projects.add(project.id)
            rows.append((project, audit))
            if len(rows) >= limit:
                break
        return rows

    async def get_owned_completed_audit(
        self, session: AsyncSession, audit_run_id: int, requester_id: str
    ) -> tuple[SEOProject, WorkflowRun] | None:
        """Resolve an explicitly selected audit without falling back to another site."""
        result = await session.execute(
            select(SEOProject, WorkflowRun)
            .join(WorkflowRun, WorkflowRun.project_id == SEOProject.id)
            .where(
                WorkflowRun.id == audit_run_id,
                WorkflowRun.status == "completed",
                WorkflowRun.requester_id == requester_id,
            )
        )
        row = result.first()
        return (row[0], row[1]) if row else None

    async def latest_completed_audit(
        self, session: AsyncSession, requester_id: str | None = None
    ) -> tuple[SEOProject, WorkflowRun] | None:
        statement = (
            select(SEOProject, WorkflowRun)
            .join(WorkflowRun, WorkflowRun.project_id == SEOProject.id)
            .where(WorkflowRun.status == "completed")
            .order_by(WorkflowRun.completed_at.desc(), WorkflowRun.id.desc())
            .limit(1)
        )
        if requester_id is not None:
            statement = statement.where(WorkflowRun.requester_id == requester_id)
        result = await session.execute(statement)
        row = result.first()
        return (row[0], row[1]) if row else None

    async def create_job(
        self,
        session: AsyncSession,
        project_id: int,
        audit_run_id: int | None,
        primary_keyword: str,
        secondary_keywords: list[str],
        competitor_urls: list[str],
        topic: str | None,
        conversion_urls: dict[str, str] | None = None,
        requester_id: str | None = None,
    ) -> ContentJob:
        if audit_run_id is None:
            raise ValueError("A completed audit is required for every content job.")
        audit = await session.get(WorkflowRun, audit_run_id)
        if audit is None or audit.status != "completed":
            raise ValueError("The selected audit does not exist or is not completed.")
        if audit.project_id != project_id:
            raise ValueError(
                "The selected audit does not belong to the selected project."
            )
        if requester_id is not None and audit.requester_id != requester_id:
            raise ValueError(
                "The selected audit does not belong to the requesting user."
            )
        job = ContentJob(
            requester_id=requester_id or audit.requester_id,
            project_id=project_id,
            audit_run_id=audit_run_id,
            primary_keyword=primary_keyword,
            topic=topic,
            max_revisions=get_runtime_config().max_revisions,
        )
        session.add(job)
        await session.flush()

        session.add(
            ContentKeyword(
                content_job_id=job.id,
                keyword=primary_keyword,
                keyword_type="primary",
            )
        )
        session.add_all(
            ContentKeyword(
                content_job_id=job.id,
                keyword=keyword,
                keyword_type="secondary",
            )
            for keyword in secondary_keywords
        )
        session.add_all(
            ContentCompetitor(
                content_job_id=job.id,
                url=url,
                domain=(urlparse(url).hostname or "").lower(),
            )
            for url in competitor_urls
        )
        session.add_all(
            ContentConversionLink(
                content_job_id=job.id,
                link_type=link_type,
                url=url,
            )
            for link_type, url in (conversion_urls or {}).items()
        )
        await session.commit()
        await session.refresh(job)
        return job

    async def get_job(self, session: AsyncSession, job_id: int) -> ContentJob | None:
        result = await session.execute(
            select(ContentJob)
            .where(ContentJob.id == job_id)
            .options(
                selectinload(ContentJob.project),
                selectinload(ContentJob.keywords),
                selectinload(ContentJob.competitors),
                selectinload(ContentJob.conversion_links),
                selectinload(ContentJob.versions),
                selectinload(ContentJob.strategies),
                selectinload(ContentJob.reviews),
            )
        )
        return result.scalar_one_or_none()

    async def get_owned_job(
        self, session: AsyncSession, job_id: int, requester_id: str
    ) -> ContentJob | None:
        result = await session.execute(
            select(ContentJob)
            .where(
                ContentJob.id == job_id,
                ContentJob.requester_id == requester_id,
            )
            .options(
                selectinload(ContentJob.project),
                selectinload(ContentJob.keywords),
                selectinload(ContentJob.competitors),
                selectinload(ContentJob.conversion_links),
                selectinload(ContentJob.strategies),
                selectinload(ContentJob.versions),
                selectinload(ContentJob.reviews),
            )
        )
        return result.scalar_one_or_none()

    async def list_owned_jobs(
        self, session: AsyncSession, requester_id: str, limit: int = 5
    ) -> list[ContentJob]:
        result = await session.execute(
            select(ContentJob)
            .where(ContentJob.requester_id == requester_id)
            .options(selectinload(ContentJob.project))
            .order_by(ContentJob.created_at.desc(), ContentJob.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def set_status(
        self,
        session: AsyncSession,
        job_id: int,
        status: str,
        current_agent: str | None = None,
        error_message: str | None = None,
        revision_count: int | None = None,
        previous_review_status: str | None = None,
        revision_target: str | None = None,
        revision_reason: str | None = None,
        technical_retry_count: int | None = None,
    ) -> None:
        job = await session.get(ContentJob, job_id)
        if job is None:
            raise ValueError(f"Content job {job_id} was not found.")
        job.status = status
        job.current_agent = current_agent
        job.error_message = error_message
        if revision_count is not None:
            job.revision_count = revision_count
        if previous_review_status is not None:
            job.previous_review_status = previous_review_status
        if revision_target is not None:
            job.revision_target = revision_target
        if revision_reason is not None:
            job.revision_reason = revision_reason
        if technical_retry_count is not None:
            job.technical_retry_count = technical_retry_count
        if job.started_at is None and status != "pending":
            job.started_at = utc_now()
        if status in {"approved", "human_review_required", "failed", "cancelled"}:
            job.completed_at = utc_now()
        await session.commit()

    async def save_strategy(
        self, session: AsyncSession, job_id: int, strategy: dict[str, Any]
    ) -> ContentStrategy:
        record = ContentStrategy(content_job_id=job_id, strategy_data=strategy)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def save_version(
        self, session: AsyncSession, job_id: int, content: dict[str, Any]
    ) -> ContentVersion:
        result = await session.execute(
            select(ContentVersion.version_number)
            .where(ContentVersion.content_job_id == job_id)
            .order_by(ContentVersion.version_number.desc())
            .limit(1)
        )
        version_number = (result.scalar_one_or_none() or 0) + 1
        record = ContentVersion(
            content_job_id=job_id,
            version_number=version_number,
            content=content,
            word_count=self.word_count(content),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def save_review(
        self,
        session: AsyncSession,
        job_id: int,
        version_id: int,
        review: dict[str, Any],
    ) -> ContentReview:
        record = ContentReview(
            content_job_id=job_id,
            content_version_id=version_id,
            status=str(review.get("status", "failed")),
            revision_number=int(review.get("revision_number") or 0),
            overall_score=(
                float(review["overall_score"])
                if review.get("overall_score") is not None
                else None
            ),
            feedback=review,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def approve(
        self, session: AsyncSession, job_id: int, version_id: int
    ) -> None:
        job = await session.get(ContentJob, job_id)
        if job is None:
            raise ValueError(f"Content job {job_id} was not found.")
        job.status = "approved"
        job.current_agent = None
        job.final_version_id = version_id
        job.error_message = None
        job.completed_at = utc_now()
        await session.commit()

    async def save_token_usage(
        self,
        session: AsyncSession,
        job_id: int,
        usage: dict[str, Any],
        estimated_cost_usd: Any,
    ) -> ContentTokenUsage:
        record = ContentTokenUsage(
            content_job_id=job_id,
            agent_name=str(usage.get("agent_name") or "content_writer"),
            provider=str(usage.get("provider") or "unknown"),
            model_name=str(usage.get("model") or "unknown"),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            estimated_cost_usd=estimated_cost_usd,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    @staticmethod
    def word_count(content: dict[str, Any]) -> int:
        pieces = [
            str(content.get("title") or ""),
            str(content.get("h1") or ""),
            str(content.get("meta_description") or ""),
        ]
        body = content.get("body") or []
        if isinstance(body, str):
            pieces.append(body)
        for section in body if isinstance(body, list) else []:
            if isinstance(section, dict):
                pieces.extend(
                    [
                        str(section.get("heading") or ""),
                        str(section.get("content") or ""),
                    ]
                )
        return len(" ".join(pieces).split())
