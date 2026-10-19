from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Literal, TypeVar
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.issue import SEOIssue


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be a valid HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    hostname = parsed.hostname.lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise ValueError("URL hostname must be a fully qualified domain name.")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise ValueError("URL hostname must be a fully qualified domain name.")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), hostname + port, path, "", parsed.query, ""))


def unique_text(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    AUDITING = "auditing"
    ROUTING = "routing"
    STRATEGIZING = "strategizing"
    WRITING_BRIEF = "writing_brief"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    REVISING = "revising"
    APPROVED = "approved"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(str, Enum):
    METADATA_ONLY = "metadata_only"
    HEADING_FIX = "heading_fix"
    CONTENT_UPDATE = "content_update"
    CONTENT_EXPANSION = "content_expansion"
    NEW_ARTICLE = "new_article"
    LANDING_PAGE = "landing_page"
    SERVICE_PAGE = "service_page"
    NO_GENERATION_REQUIRED = "no_generation_required"


class RevisionTarget(str, Enum):
    CONTENT_STRATEGIST = "content_strategist"
    CONTENT_WRITER = "content_writer"
    ARTICLE_GENERATOR = "article_generator"
    NONE = "none"


DataT = TypeVar("DataT")


class AgentExecutionResult(BaseModel, Generic[DataT]):
    success: bool
    status: str
    agent_name: str
    data: DataT | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    execution_time_ms: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)


class RoutingRequest(BaseModel):
    issue: SEOIssue
    project_id: str | int
    available_agents: list[str]


class RoutingDecision(BaseModel):
    assigned_agent: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    fallback_used: bool = False


class WebsiteAuditRequest(BaseModel):
    project_id: str | int | None = None
    website_url: str
    # None means crawl every reachable internal page. Callers may opt into a
    # ceiling for previews or resource-constrained runs.
    max_pages: int | None = Field(default=None, ge=1, le=1_000_000)
    crawl_depth: int = Field(default=2, ge=0, le=10)
    respect_robots_txt: bool = True
    use_sitemap: bool = True
    request_timeout_seconds: float = Field(default=15, gt=0, le=120)
    include_external_links: bool = False

    @field_validator("website_url", mode="before")
    @classmethod
    def validate_url(cls, value: Any) -> str:
        return normalize_url(str(value))


class CrawlSummary(BaseModel):
    discovered: int = Field(ge=0)
    crawled: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(default=0, ge=0)


class WebsiteAuditResult(BaseModel):
    website_url: str
    pages_discovered: int = Field(ge=0)
    pages_crawled: int = Field(ge=0)
    pages_failed: int = Field(ge=0)
    issues: list[SEOIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    crawl_summary: CrawlSummary


class CompetitorEvidence(BaseModel):
    url: str
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    word_count: int = Field(default=0, ge=0)
    summary: str | None = None


class CompetitorInsights(BaseModel):
    competitors_analyzed: list[str] = Field(default_factory=list)
    common_topics: list[str] = Field(default_factory=list)
    competitor_strengths: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    keyword_gaps: list[str] = Field(default_factory=list)
    structural_patterns: list[str] = Field(default_factory=list)
    differentiation_opportunities: list[str] = Field(default_factory=list)
    evidence: list[CompetitorEvidence] = Field(default_factory=list)


class ContentStrategyRequest(BaseModel):
    project_id: str | int
    issue: SEOIssue
    page_url: str | None = None
    primary_keyword: str | None = None
    secondary_keywords: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    search_intent: str | None = None
    business_goal: str | None = None
    existing_title: str | None = None
    existing_meta_description: str | None = None
    existing_h1: str | None = None
    existing_content_summary: str | None = None
    competitor_insights: CompetitorInsights | None = None
    language: str = "en"
    tone: str | None = None

    @field_validator("secondary_keywords")
    @classmethod
    def deduplicate_keywords(cls, value: list[str]) -> list[str]:
        return unique_text(value)


class ContentStrategy(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    issue_id: str
    problem_summary: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    search_intent: str | None = None
    recommended_action_type: ActionType
    priority: Literal["critical", "high", "medium", "low", "info"]
    target_audience: str | None = None
    primary_keyword: str | None = None
    secondary_keywords: list[str] = Field(default_factory=list)
    content_type: str | None = None
    recommended_word_count_min: int | None = Field(default=None, ge=0)
    recommended_word_count_max: int | None = Field(default=None, ge=0)
    key_topics: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(min_length=1)
    cta: str | None = Field(default=None, alias="CTA")
    constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @field_validator("secondary_keywords", "key_topics", "content_gaps", "recommended_actions", "constraints")
    @classmethod
    def deduplicate_lists(cls, value: list[str]) -> list[str]:
        return unique_text(value)

    @model_validator(mode="after")
    def validate_word_range(self) -> ContentStrategy:
        if (
            self.recommended_word_count_min is not None
            and self.recommended_word_count_max is not None
            and self.recommended_word_count_max < self.recommended_word_count_min
        ):
            raise ValueError("Maximum word count cannot be smaller than minimum word count.")
        return self


class InternalLinkCandidate(BaseModel):
    url: str
    anchor_text: str | None = None
    purpose: str | None = None


class InternalLinkRecommendation(InternalLinkCandidate):
    required: bool = False


class ContentSection(BaseModel):
    heading_level: Literal[2, 3]
    heading: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    target_words: int | None = Field(default=None, ge=0)
    keywords: list[str] = Field(default_factory=list)
    questions_to_answer: list[str] = Field(default_factory=list)


class ContentBrief(BaseModel):
    title: str = Field(min_length=1)
    alternative_titles: list[str] = Field(default_factory=list)
    seo_title: str = Field(min_length=1)
    meta_description: str = Field(min_length=1)
    slug: str | None = None
    h1: str = Field(min_length=1)
    outline: list[ContentSection] = Field(default_factory=list)
    introduction_goal: str = Field(min_length=1)
    conclusion_goal: str = Field(min_length=1)
    primary_keyword: str | None = None
    secondary_keywords: list[str] = Field(default_factory=list)
    target_word_count: int | None = Field(default=None, ge=0)
    keyword_guidance: list[str] = Field(default_factory=list)
    internal_links: list[InternalLinkRecommendation] = Field(default_factory=list)
    faq_questions: list[str] = Field(default_factory=list)
    cta: str | None = Field(default=None, alias="CTA")
    source_requirements: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    tone: str | None = None

    @model_validator(mode="after")
    def validate_outline(self) -> ContentBrief:
        seen: set[str] = set()
        has_h2 = False
        for section in self.outline:
            key = section.heading.casefold()
            if key in seen:
                raise ValueError("Content brief contains duplicate headings.")
            seen.add(key)
            if section.heading_level == 2:
                has_h2 = True
            elif not has_h2:
                raise ValueError("An H3 section must follow an H2 section.")
        return self


class ContentWriterRequest(BaseModel):
    strategy: ContentStrategy
    page_url: str | None = None
    brand_name: str | None = None
    brand_description: str | None = None
    internal_link_candidates: list[InternalLinkCandidate] = Field(default_factory=list)
    existing_content: str | None = None
    language: str = "en"
    tone: str | None = None


class FAQItem(BaseModel):
    question: str
    answer: str


class GenerationMetadata(BaseModel):
    provider: str | None = None
    model_name: str | None = None
    revision_number: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)


class GeneratedArticle(BaseModel):
    title: str
    seo_title: str
    meta_description: str
    slug: str | None = None
    h1: str
    markdown_body: str = Field(min_length=1)
    faq: list[FAQItem] = Field(default_factory=list)
    cta: str | None = Field(default=None, alias="CTA")
    internal_links_used: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    word_count: int = Field(ge=0)
    generation_metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)

    @model_validator(mode="after")
    def recalculate_word_count(self) -> GeneratedArticle:
        self.word_count = len(re.findall(r"\b[\w'-]+\b", self.markdown_body))
        return self


class SourceMaterial(BaseModel):
    title: str | None = None
    url: str | None = None
    content: str


class ArticleGenerationRequest(BaseModel):
    project_id: str | int
    strategy: ContentStrategy
    brief: ContentBrief
    brand_name: str | None = None
    brand_description: str | None = None
    source_material: list[SourceMaterial] = Field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None
    revision_instructions: list[str] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    code: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    message: str
    location: str | None = None
    suggested_fix: str | None = None


class ReviewResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: Literal["approved", "needs_revision", "human_review_required"]
    overall_score: float = Field(ge=0, le=100)
    seo_score: float = Field(ge=0, le=100)
    quality_score: float = Field(ge=0, le=100)
    intent_score: float = Field(ge=0, le=100)
    readability_score: float = Field(ge=0, le=100)
    evidence_score: float = Field(ge=0, le=100)
    deterministic_failures: list[ReviewIssue] = Field(default_factory=list)
    semantic_issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    revision_target: RevisionTarget = RevisionTarget.NONE
    critical_failure: bool = False
    reason: str


class ReviewRequest(BaseModel):
    strategy: ContentStrategy
    brief: ContentBrief
    article: GeneratedArticle
    revision_number: int = Field(ge=0)
    max_revisions: int = Field(ge=0, le=10)
    target_url: str | None = None


class SEOAutomationRequest(BaseModel):
    website_url: str
    primary_keyword: str | None = None
    secondary_keywords: list[str] = Field(default_factory=list)
    competitor_urls: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    business_goal: str | None = None
    language: str = "en"
    tone: str = "professional"
    max_pages: int | None = Field(default=None, ge=1, le=1_000_000)
    generate_content: bool = True

    @field_validator("website_url", mode="before")
    @classmethod
    def normalize_website(cls, value: Any) -> str:
        return normalize_url(str(value))

    @field_validator("competitor_urls", mode="before")
    @classmethod
    def normalize_competitors(cls, value: Any) -> list[str]:
        urls = [normalize_url(str(item)) for item in (value or [])]
        return list(dict.fromkeys(urls))

    @field_validator("secondary_keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return unique_text(value)
