
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowState(BaseModel):
    """Shared state passed between SEO workflow agents."""

    # Workflow identification
    project_id: int | None = None
    workflow_run_id: int | None = None

    # Website information
    website_url: str = ""
    project_name: str = ""

    # Workflow tracking
    status: Literal[
        "pending",
        "running",
        "auditing",
        "routing",
        "strategizing",
        "writing_brief",
        "generating",
        "reviewing",
        "revising",
        "approved",
        "human_review_required",
        "completed",
        "failed",
        "cancelled",
    ] = "pending"

    current_agent: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Data shared between agents
    input_data: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    revision_count: int = Field(default=0, ge=0)
    max_revisions: int = Field(default=3, ge=0, le=10)
    technical_retry_count: int = Field(default=0, ge=0)
    previous_review_status: str | None = None
    revision_target: str | None = None
    revision_reason: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    # Cost and usage tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def add_result(self, agent_name: str, result: Any) -> None:
        """Store an agent's result."""
        self.results[agent_name] = result
        self.updated_at = utc_now()

    def add_error(self, agent_name: str, error: str) -> None:
        """Record an agent error."""
        self.errors.append(f"{agent_name}: {error}")
        self.updated_at = utc_now()

    def mark_started(self) -> None:
        """Mark the workflow as running."""
        self.status = "running"
        self.started_at = utc_now()

    def mark_completed(self) -> None:
        """Mark the workflow as completed."""
        self.status = "completed"
        self.completed_at = utc_now()

    def mark_failed(self) -> None:
        """Mark the workflow as failed."""
        self.status = "failed"
        self.completed_at = utc_now()
