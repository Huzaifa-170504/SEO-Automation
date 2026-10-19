"""
SQLAlchemy database models for SEO-AUTOMATION.

Defines:
- SEOProject
- WorkflowRun
- AgentExecution
- TokenUsage
- SEOIssueRecord
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all database models."""


class SEOProject(Base):
    """A website or SEO project managed by the system."""

    __tablename__ = "seo_projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    content_jobs: Mapped[list[ContentJob]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    issues: Mapped[list[SEOIssueRecord]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<SEOProject(id={self.id}, name={self.name!r})>"


class WorkflowRun(Base):
    """A single execution of an SEO automation workflow."""

    __tablename__ = "workflow_runs"

    __table_args__ = (
        Index("ix_workflow_project_status", "project_id", "status"),
        Index("ix_workflow_created_at", "created_at"),
        Index("ix_workflow_requester_created", "requester_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("seo_projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    requester_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )

    trigger: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        nullable=False,
    )

    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    current_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)

    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    technical_retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    project: Mapped[SEOProject] = relationship(
        back_populates="workflow_runs",
    )

    agent_executions: Mapped[list[AgentExecution]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    token_usages: Mapped[list[TokenUsage]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    issues: Mapped[list[SEOIssueRecord]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowRun(id={self.id}, project_id={self.project_id}, "
            f"status={self.status!r})>"
        )


class AgentExecution(Base):
    """Execution record for an individual AI agent."""

    __tablename__ = "agent_executions"

    __table_args__ = (
        Index("ix_agent_workflow_status", "workflow_run_id", "status"),
        Index("ix_agent_name_created", "agent_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workflow_run: Mapped[WorkflowRun] = relationship(
        back_populates="agent_executions",
    )

    token_usages: Mapped[list[TokenUsage]] = relationship(
        back_populates="agent_execution",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AgentExecution(id={self.id}, agent_name={self.agent_name!r}, "
            f"status={self.status!r})>"
        )


class TokenUsage(Base):
    """Token usage and estimated cost for an LLM API call."""

    __tablename__ = "token_usages"

    __table_args__ = (
        Index("ix_token_workflow_created", "workflow_run_id", "created_at"),
        Index("ix_token_provider_model", "provider", "model_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    agent_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"),
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 8),
        default=Decimal(0),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    workflow_run: Mapped[WorkflowRun] = relationship(
        back_populates="token_usages",
    )

    agent_execution: Mapped[AgentExecution | None] = relationship(
        back_populates="token_usages",
    )

    def __repr__(self) -> str:
        return (
            f"<TokenUsage(id={self.id}, provider={self.provider!r}, "
            f"model_name={self.model_name!r}, "
            f"total_tokens={self.total_tokens})>"
        )


class SEOIssueRecord(Base):
    """Database record for a detected SEO issue."""

    __tablename__ = "seo_issues"

    __table_args__ = (
        Index("ix_issue_project_status", "project_id", "status"),
        Index("ix_issue_workflow", "workflow_run_id"),
        Index("ix_issue_assigned_agent", "assigned_agent"),
        Index("ix_issue_type", "issue_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    issue_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
    )

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("seo_projects.id", ondelete="CASCADE"),
        nullable=True,
    )

    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
    )

    source_agent: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    assigned_agent: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    issue_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        nullable=False,
    )

    url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    validation_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )

    validation_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    recommendation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="open",
        nullable=False,
    )

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    project: Mapped[SEOProject | None] = relationship(
        back_populates="issues",
    )

    workflow_run: Mapped[WorkflowRun | None] = relationship(
        back_populates="issues",
    )

    def __repr__(self) -> str:
        return (
            f"<SEOIssueRecord(id={self.id}, "
            f"issue_type={self.issue_type!r}, "
            f"status={self.status!r})>"
        )


class ContentJob(Base):
    __tablename__ = "content_jobs"
    __table_args__ = (
        Index("ix_content_job_project_status", "project_id", "status"),
        Index("ix_content_job_completed", "completed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requester_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("seo_projects.id", ondelete="CASCADE"), nullable=False
    )
    audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    current_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_revisions: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    technical_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    previous_review_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    revision_target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped[SEOProject] = relationship(back_populates="content_jobs")
    audit_run: Mapped[WorkflowRun | None] = relationship()
    keywords: Mapped[list[ContentKeyword]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    competitors: Mapped[list[ContentCompetitor]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    conversion_links: Mapped[list[ContentConversionLink]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    strategies: Mapped[list[ContentStrategy]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    versions: Mapped[list[ContentVersion]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    reviews: Mapped[list[ContentReview]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )
    token_usages: Mapped[list[ContentTokenUsage]] = relationship(
        back_populates="content_job", cascade="all, delete-orphan", passive_deletes=True
    )


class ContentKeyword(Base):
    __tablename__ = "content_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    keyword_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_job: Mapped[ContentJob] = relationship(back_populates="keywords")


class ContentCompetitor(Base):
    __tablename__ = "content_competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    content_job: Mapped[ContentJob] = relationship(back_populates="competitors")


class ContentConversionLink(Base):
    __tablename__ = "content_conversion_links"
    __table_args__ = (
        Index(
            "ix_content_conversion_link_job_type",
            "content_job_id",
            "link_type",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_job: Mapped[ContentJob] = relationship(back_populates="conversion_links")


class ContentStrategy(Base):
    __tablename__ = "content_strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    content_job: Mapped[ContentJob] = relationship(back_populates="strategies")


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        Index(
            "ix_content_version_job_number",
            "content_job_id",
            "version_number",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    content_job: Mapped[ContentJob] = relationship(back_populates="versions")
    reviews: Mapped[list[ContentReview]] = relationship(
        back_populates="content_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ContentReview(Base):
    __tablename__ = "content_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_version_id: Mapped[int] = mapped_column(
        ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    content_job: Mapped[ContentJob] = relationship(back_populates="reviews")
    content_version: Mapped[ContentVersion] = relationship(back_populates="reviews")


class ContentTokenUsage(Base):
    __tablename__ = "content_token_usages"
    __table_args__ = (
        Index("ix_content_token_job_created", "content_job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), default=Decimal(0), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    content_job: Mapped[ContentJob] = relationship(back_populates="token_usages")
