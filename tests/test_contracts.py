from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agents.manager import AgentManager
from app.models.contracts import (
    ContentBrief,
    ContentSection,
    ContentStrategy,
    RoutingRequest,
    SEOAutomationRequest,
)
from app.models.issue import IssueCategory, SEOIssue
from app.services.structured_output import (
    parse_structured_output,
    parse_with_one_repair,
)


def make_issue(issue_type: str = "unknown") -> SEOIssue:
    return SEOIssue(
        source_agent="website_auditor",
        category=IssueCategory.TECHNICAL_SEO,
        issue_type=issue_type,
        title="Issue",
        description="Description",
    )


def test_user_request_normalizes_and_deduplicates_inputs() -> None:
    request = SEOAutomationRequest(
        website_url="Example.COM",
        secondary_keywords=[" SEO audit ", "seo audit", "technical SEO"],
        competitor_urls=["competitor.example", "https://competitor.example/"],
    )

    assert request.website_url == "https://example.com/"
    assert request.secondary_keywords == ["SEO audit", "technical SEO"]
    assert request.competitor_urls == ["https://competitor.example/"]


def test_unknown_routing_is_deterministic_and_never_recursive() -> None:
    decision = AgentManager().route(
        RoutingRequest(
            issue=make_issue(),
            project_id=1,
            available_agents=["website_auditor", "agent_manager"],
        )
    )

    assert decision.assigned_agent == "website_auditor"
    assert decision.fallback_used is False
    assert decision.assigned_agent != "agent_manager"


def test_strategy_rejects_reversed_word_range() -> None:
    with pytest.raises(ValueError, match="Maximum word count"):
        ContentStrategy(
            issue_id="issue",
            problem_summary="Thin content",
            objective="Improve coverage",
            recommended_action_type="content_expansion",
            priority="medium",
            recommended_word_count_min=1000,
            recommended_word_count_max=500,
            recommended_actions=["Expand useful coverage"],
            confidence=0.9,
        )


def test_brief_rejects_h3_without_parent_and_duplicate_headings() -> None:
    base = {
        "title": "Title",
        "seo_title": "Title",
        "meta_description": "Description",
        "h1": "Title",
        "introduction_goal": "Introduce",
        "conclusion_goal": "Conclude",
    }
    with pytest.raises(ValueError, match="must follow an H2"):
        ContentBrief(
            **base,
            outline=[ContentSection(heading_level=3, heading="Child", objective="Explain")],
        )
    with pytest.raises(ValueError, match="duplicate headings"):
        ContentBrief(
            **base,
            outline=[
                ContentSection(heading_level=2, heading="Same", objective="One"),
                ContentSection(heading_level=2, heading="same", objective="Two"),
            ],
        )


class Payload(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_structured_output_uses_one_bounded_repair() -> None:
    calls = 0

    async def repair(raw: str, schema: str) -> str:
        nonlocal calls
        calls += 1
        assert raw == "not json"
        assert "value" in schema
        return '{"value": 7}'

    result = await parse_with_one_repair("not json", Payload, repair)
    assert result.value == 7
    assert calls == 1
    assert parse_structured_output('```json\n{"value": 8}\n```', Payload).value == 8
