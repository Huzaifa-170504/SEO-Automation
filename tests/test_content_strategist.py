import pytest

from app.agents.content_strategist import ContentStrategist
from app.models.issue import (
    IssueCategory,
    IssueSeverity,
    SEOIssue,
)


def make_issue(
    issue_type: str,
    category: IssueCategory = IssueCategory.ON_PAGE_SEO,
) -> SEOIssue:
    return SEOIssue(
        issue_id=f"test-{issue_type}",
        url="https://example.com/test-page",
        issue_type=issue_type,
        category=category,
        severity=IssueSeverity.HIGH,
        title=f"Test {issue_type}",
        description=f"Test issue for {issue_type}",
        source_agent="website_auditor",
    )


@pytest.mark.asyncio
async def test_content_strategist_can_handle_missing_h1():
    agent = ContentStrategist()

    issue = make_issue("missing_h1")

    assert agent.can_handle(issue) is True


@pytest.mark.asyncio
async def test_content_strategist_analyzes_missing_h1():
    agent = ContentStrategist()

    issue = make_issue("missing_h1")

    result = await agent.analyze(issue)

    assert result["agent"] == "content_strategist"
    assert result["issue_id"] == "test-missing_h1"
    assert result["issue_type"] == "missing_h1"
    assert result["url"] == "https://example.com/test-page"
    assert result["status"] == "analyzed"

    assert "strategy" in result
    assert result["strategy"]["priority"] == "high"
    assert len(result["strategy"]["actions"]) > 0


@pytest.mark.asyncio
async def test_content_strategist_analyzes_missing_title():
    agent = ContentStrategist()

    issue = make_issue("missing_title")

    result = await agent.analyze(issue)

    assert result["status"] == "analyzed"
    assert result["strategy"]["priority"] == "high"


@pytest.mark.asyncio
async def test_content_strategist_analyzes_meta_description():
    agent = ContentStrategist()

    issue = make_issue("missing_meta_description")

    result = await agent.analyze(issue)

    assert result["status"] == "analyzed"
    assert result["strategy"]["priority"] == "medium"


@pytest.mark.asyncio
async def test_content_strategist_rejects_unsupported_issue():
    agent = ContentStrategist()

    issue = make_issue(
        "broken_internal_link",
        category=IssueCategory.TECHNICAL_SEO,
    )

    assert agent.can_handle(issue) is False

    with pytest.raises(ValueError):
        await agent.analyze(issue)


@pytest.mark.asyncio
async def test_content_strategist_analyze_many():
    agent = ContentStrategist()

    issues = [
        make_issue("missing_h1"),
        make_issue("missing_title"),
        make_issue("missing_meta_description"),
        make_issue(
            "broken_internal_link",
            category=IssueCategory.TECHNICAL_SEO,
        ),
    ]

    results = await agent.analyze_many(issues)

    assert len(results) == 3

    issue_types = {
        result["issue_type"]
        for result in results
    }

    assert issue_types == {
        "missing_h1",
        "missing_title",
        "missing_meta_description",
    }
