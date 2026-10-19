import pytest

from app.agents.reviewer import Reviewer


@pytest.fixture
def reviewer() -> Reviewer:
    return Reviewer()


@pytest.fixture
def keyword_data() -> dict:
    return {
        "primary_keyword": {
            "keyword": "seo services",
            "role": "primary",
        },
        "keywords": [
            {
                "keyword": "seo services",
                "role": "primary",
            },
            {
                "keyword": "seo agency",
                "role": "secondary",
            },
            {
                "keyword": "seo pricing",
                "role": "secondary",
            },
        ],
    }


@pytest.fixture
def strategy() -> dict:
    return {
        "search_intent": "commercial",
        "objective": "Help users evaluate SEO services.",
    }


@pytest.fixture
def valid_content() -> dict:
    return {
        "title": "SEO Services Guide",
        "h1": "Professional SEO Services",
        "meta_description": (
            "Learn about SEO services, SEO agencies, and SEO pricing."
        ),
        "headings": [
            "What Are SEO Services?",
            "Choosing an SEO Agency",
            "SEO Pricing",
            "Frequently Asked Questions",
        ],
        "body": [
            {
                "heading": "What Are SEO Services?",
                "content": (
                    "SEO services help businesses improve organic search visibility."
                ),
            },
            {
                "heading": "Choosing an SEO Agency",
                "content": (
                    "An SEO agency can provide technical and content "
                    "optimization services."
                ),
            },
            {
                "heading": "SEO Pricing",
                "content": (
                    "SEO pricing depends on scope, competition, and "
                    "the services required."
                ),
            },
        ],
    }


def test_required_elements_present(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    issues = reviewer.check_required_elements(valid_content)

    assert issues == []


def test_required_elements_missing(
    reviewer: Reviewer,
) -> None:
    issues = reviewer.check_required_elements({})

    assert "Missing SEO title." in issues
    assert "Missing H1 heading." in issues
    assert "Missing meta description." in issues
    assert "Missing heading structure." in issues
    assert "Missing body content." in issues


def test_primary_keyword_check(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    result = reviewer.check_primary_keyword(
        content=valid_content,
        primary_keyword="SEO services",
    )

    assert result["keyword"] == "seo services"
    assert result["present"] is True
    assert result["occurrences"] > 0


def test_secondary_keyword_check(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    results = reviewer.check_secondary_keywords(
        content=valid_content,
        secondary_keywords=[
            "SEO agency",
            "SEO pricing",
        ],
    )

    assert len(results) == 2
    assert all(result["present"] for result in results)


def test_heading_check(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    result = reviewer.check_headings(
        content=valid_content,
        primary_keyword="SEO services",
    )

    assert result["heading_count"] == 4
    assert result["has_headings"] is True
    assert result["primary_keyword_in_heading"] is True


def test_content_gap_check(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    missing = reviewer.check_content_gaps(
        content=valid_content,
        content_gaps=[
            "SEO pricing",
            "technical SEO",
        ],
    )

    assert missing == ["technical SEO"]


def test_keyword_stuffing_detection(
    reviewer: Reviewer,
    valid_content: dict,
) -> None:
    result = reviewer.detect_keyword_stuffing(
        content=valid_content,
        primary_keyword="SEO services",
        threshold=20,
    )

    assert result["occurrences"] < 20
    assert result["possible_stuffing"] is False


def test_content_format_check_rejects_an_incomplete_markdown_article(
    reviewer: Reviewer,
) -> None:
    issues = reviewer.check_content_format(
        {"body": "# Title\n\nA short article without the keyword."},
        {
            "content_format": {
                "word_count_range": [1200, 1600],
                "h2_count": [4, 6],
                "faq_questions": 1,
            },
            "internal_links": {
                "contact": "https://example.com/contact",
                "login": "https://example.com/login",
            },
        },
        "seo services",
    )

    assert any("Article length" in issue for issue in issues)
    assert "Primary keyword is missing from the first 100 words." in issues
    assert any("H2 sections" in issue for issue in issues)
    assert "Missing the required Frequently Asked Questions section." in issues
    assert any("contact page link" in issue for issue in issues)
    assert any("login page link" in issue for issue in issues)


@pytest.mark.asyncio
async def test_review_approved_content(
    reviewer: Reviewer,
    valid_content: dict,
    keyword_data: dict,
    strategy: dict,
) -> None:
    result = await reviewer.review(
        content=valid_content,
        keyword_data=keyword_data,
        strategy=strategy,
        competitor_analysis={
            "content_gaps": [],
        },
    )

    assert result["agent"] == "reviewer"
    assert result["status"] == "approved"
    assert result["primary_keyword"] == "seo services"
    assert result["issue_count"] == 0
    assert result["issues"] == []
    assert result["primary_keyword_check"]["present"] is True


@pytest.mark.asyncio
async def test_review_detects_missing_elements(
    reviewer: Reviewer,
    keyword_data: dict,
    strategy: dict,
) -> None:
    result = await reviewer.review(
        content={
            "title": "",
            "h1": "",
            "meta_description": "",
            "headings": [],
            "body": [],
        },
        keyword_data=keyword_data,
        strategy=strategy,
    )

    assert result["status"] == "needs_revision"
    assert result["issue_count"] > 0
    assert "Missing SEO title." in result["issues"]
    assert "Missing H1 heading." in result["issues"]
    assert "Missing meta description." in result["issues"]


@pytest.mark.asyncio
async def test_review_detects_missing_secondary_keyword(
    reviewer: Reviewer,
    keyword_data: dict,
    strategy: dict,
) -> None:
    content = {
        "title": "SEO Services",
        "h1": "SEO Services",
        "meta_description": "Learn about SEO services.",
        "headings": [
            "SEO Services",
            "Frequently Asked Questions",
        ],
        "body": [
            {
                "heading": "SEO Services",
                "content": ("SEO services help businesses improve visibility."),
            }
        ],
    }

    result = await reviewer.review(
        content=content,
        keyword_data=keyword_data,
        strategy=strategy,
    )

    assert result["status"] == "needs_revision"

    assert any("seo agency" in issue for issue in result["issues"])

    assert any("seo pricing" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_review_many(
    reviewer: Reviewer,
    valid_content: dict,
    keyword_data: dict,
    strategy: dict,
) -> None:
    jobs = [
        {
            "content": valid_content,
            "keyword_data": keyword_data,
            "strategy": strategy,
        },
        {
            "content": valid_content,
            "keyword_data": keyword_data,
            "strategy": strategy,
        },
    ]

    results = await reviewer.review_many(jobs)

    assert len(results) == 2
    assert results[0]["status"] == "approved"
    assert results[1]["status"] == "approved"


@pytest.mark.asyncio
async def test_review_requires_primary_keyword(
    reviewer: Reviewer,
    valid_content: dict,
    strategy: dict,
) -> None:
    with pytest.raises(ValueError):
        await reviewer.review(
            content=valid_content,
            keyword_data={},
            strategy=strategy,
        )
