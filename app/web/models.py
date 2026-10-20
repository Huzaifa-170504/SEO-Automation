from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.contracts import normalize_url


class DemoAuditRequest(BaseModel):
    website_url: str
    company: str = Field(default="", max_length=0, exclude=True)

    @field_validator("website_url", mode="before")
    @classmethod
    def validate_website_url(cls, value: Any) -> str:
        return normalize_url(str(value))


class DemoIssue(BaseModel):
    issue_id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: str
    issue_type: str
    title: str
    description: str
    url: str | None = None
    recommendation: str | None = None
    assigned_agent: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class DemoPage(BaseModel):
    url: str
    status_code: int | None = None
    title: str = ""
    meta_description: str = ""
    h1_headings: list[str] = Field(default_factory=list)
    canonical: str | None = None
    image_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    word_count: int = 0
    language: str | None = None
    issues: list[str] = Field(default_factory=list)


class AuditSummary(BaseModel):
    pages_discovered: int = 0
    pages_crawled: int = 0
    pages_failed: int = 0
    issue_count: int = 0
    crawl_limit_reached: bool = False
    severity_counts: dict[str, int] = Field(default_factory=dict)


class DemoAuditResult(BaseModel):
    audit_id: UUID
    access_token: str | None = None
    website_url: str
    status: Literal["completed"] = "completed"
    created_at: datetime
    expires_at: datetime
    summary: AuditSummary
    issues: list[DemoIssue]
    pages: list[DemoPage]
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "seo-automation-api"
    persistence: Literal["memory", "supabase"]
    demo_max_pages: int


class DemoContentRequest(BaseModel):
    audit_id: UUID
    audit_token: str = Field(min_length=20, max_length=256)
    primary_keyword: str = Field(min_length=2, max_length=200)
    secondary_keywords: list[str] = Field(min_length=1, max_length=8)
    competitor_urls: list[str] = Field(default_factory=list, max_length=2)
    topic: str | None = Field(default=None, min_length=3, max_length=300)
    company: str = Field(default="", max_length=0, exclude=True)

    @field_validator("primary_keyword", "topic", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return " ".join(str(value).split())

    @field_validator("secondary_keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        cleaned = list(
            dict.fromkeys(" ".join(item.split()) for item in value if item.strip())
        )
        if not cleaned or any(len(item) > 200 for item in cleaned):
            raise ValueError("Enter 1 to 8 valid secondary keywords.")
        return cleaned

    @field_validator("competitor_urls", mode="before")
    @classmethod
    def normalize_competitors(cls, value: Any) -> list[str]:
        return list(dict.fromkeys(normalize_url(str(item)) for item in (value or [])))


class DemoContentResult(BaseModel):
    content_id: UUID
    access_token: str | None = None
    audit_id: UUID
    website_url: str
    primary_keyword: str
    secondary_keywords: list[str]
    competitor_urls: list[str]
    topic: str
    status: Literal["approved", "human_review_required"]
    created_at: datetime
    expires_at: datetime
    research: dict[str, Any]
    strategy: dict[str, Any]
    article: dict[str, Any]
    review: dict[str, Any]
    revisions_used: int = 0
