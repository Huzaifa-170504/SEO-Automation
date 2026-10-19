
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue import SEOIssue
from app.storage.models import SEOIssueRecord


def _enum_value(value: object) -> str:
    """Convert enum members to their plain values."""
    if isinstance(value, Enum):
        return str(value.value)

    return str(value)


class IssueRepository:
    async def save_issues(
        self,
        session: AsyncSession,
        issues: Sequence[SEOIssue],
    ) -> int:
        """Save structured SEO issues to the database."""
        if not issues:
            return 0

        records = [
            SEOIssueRecord(
                issue_id=issue.issue_id,
                project_id=issue.project_id,
                workflow_run_id=issue.workflow_run_id,
                source_agent=issue.source_agent,
                assigned_agent=issue.assigned_agent,
                category=_enum_value(issue.category),
                issue_type=issue.issue_type,
                severity=_enum_value(issue.severity),
                url=issue.url,
                title=issue.title,
                description=issue.description,
                evidence=issue.evidence,
                validation_status=_enum_value(issue.validation_status),
                validation_notes=issue.validation_notes,
                recommendation=issue.recommendation,
                status=_enum_value(issue.status),
                detected_at=issue.detected_at,
                validated_at=issue.validated_at,
                resolved_at=issue.resolved_at,
            )
            for issue in issues
        ]

        session.add_all(records)
        await session.flush()

        return len(records)

    async def get_issue_by_id(
        self,
        session: AsyncSession,
        issue_id: str,
    ) -> SEOIssueRecord | None:
        """Retrieve one issue by its unique issue ID."""
        result = await session.execute(
            select(SEOIssueRecord).where(
                SEOIssueRecord.issue_id == issue_id
            )
        )
        return result.scalar_one_or_none()

    async def get_issues_by_agent(
        self,
        session: AsyncSession,
        agent_name: str,
    ) -> list[SEOIssueRecord]:
        """Retrieve issues assigned to a specific agent."""
        result = await session.execute(
            select(SEOIssueRecord)
            .where(SEOIssueRecord.assigned_agent == agent_name)
            .order_by(SEOIssueRecord.detected_at.desc())
        )
        return list(result.scalars().all())

    async def get_all_issues(
        self,
        session: AsyncSession,
    ) -> list[SEOIssueRecord]:
        """Retrieve all issues, newest first."""
        result = await session.execute(
            select(SEOIssueRecord).order_by(
                SEOIssueRecord.detected_at.desc()
            )
        )
        return list(result.scalars().all())