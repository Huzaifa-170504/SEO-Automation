from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


class IssueCategory(str, Enum):
    TECHNICAL_SEO = "technical_seo"
    ON_PAGE_SEO = "on_page_seo"
    CONTENT = "content"
    LINKS = "links"
    INDEXABILITY = "indexability"
    PERFORMANCE = "performance"
    KEYWORDS = "keywords"
    COMPETITORS = "competitors"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class IssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class SEOIssue(BaseModel):
    """Standard structured format for an SEO finding."""

    model_config = ConfigDict(use_enum_values=True)

    issue_id: str = Field(
        default_factory=lambda: str(uuid4()),
    )

    project_id: int | None = None
    workflow_run_id: int | None = None

    source_agent: str
    assigned_agent: str | None = None

    category: IssueCategory
    issue_type: str
    severity: IssueSeverity = IssueSeverity.MEDIUM

    url: str | None = None

    title: str
    description: str

    evidence: dict[str, Any] = Field(default_factory=dict)

    validation_status: ValidationStatus = (
        ValidationStatus.PENDING
    )
    validation_notes: str | None = None

    recommendation: str | None = None

    status: IssueStatus = IssueStatus.OPEN

    detected_at: datetime = Field(default_factory=utc_now)
    validated_at: datetime | None = None
    resolved_at: datetime | None = None

    def confirm(self, notes: str | None = None) -> None:
        """Mark the finding as confirmed."""
        self.validation_status = ValidationStatus.CONFIRMED
        self.validation_notes = notes
        self.validated_at = utc_now()

    def reject(self, notes: str) -> None:
        """Mark the finding as rejected."""
        self.validation_status = ValidationStatus.REJECTED
        self.validation_notes = notes
        self.validated_at = utc_now()

    def mark_uncertain(self, notes: str) -> None:
        """Mark the finding as requiring further verification."""
        self.validation_status = ValidationStatus.UNCERTAIN
        self.validation_notes = notes
        self.validated_at = utc_now()

    def mark_resolved(self) -> None:
        """Mark the issue as resolved."""
        self.status = IssueStatus.RESOLVED
        self.resolved_at = utc_now()