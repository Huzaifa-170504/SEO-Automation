import pytest

from app.agents.content_writer import ContentWriter


@pytest.fixture
def writer() -> ContentWriter:
    return ContentWriter()


@pytest.fixture
def keyword_data() -> dict:
    return {
        "primary_keyword": {
            "keyword": "SEO services",
            "role": "primary",
        },
        "keywords": [
            {
                "keyword": "SEO services",
                "role": "primary",
            },
            {
                "keyword": "SEO agency",
                "role": "secondary",
            },
            {
                "keyword": "SEO pricing",
                "role": "secondary",
            },
        ],
    }


@pytest.fixture
def strategy() -> dict:
    return {
        "search_intent": "commercial",
        "objective": "Help users understand and evaluate SEO services.",
        "title": "SEO Services Guide",
        "h1": "Professional SEO Services",
        "meta_description": (
            "Learn how SEO services can improve search visibility "
            "and support business growth."
        ),
        "headings": [
            "What Are SEO Services?",
            "How SEO Services Work",
            "Choosing an SEO Agency",
            "Frequently Asked Questions",
        ],
    }


def test_extract_primary_keyword(
    writer: ContentWriter,
    keyword_data: dict,
) -> None:
    result = writer._extract_primary_keyword(keyword_data)

    assert result == "seo services"


def test_extract_secondary_keywords(
    writer: ContentWriter,
    keyword_data: dict,
) -> None:
    result = writer._extract_secondary_keywords(keyword_data)

    assert result == [
        "seo agency",
        "seo pricing",
    ]


def test_build_title(
    writer: ContentWriter,
) -> None:
    result = writer.build_title(
        primary_keyword="seo services",
        strategy={"title": "Professional SEO Services"},
    )

    assert result == "Professional SEO Services"


def test_build_default_title(
    writer: ContentWriter,
) -> None:
    result = writer.build_title(
        primary_keyword="seo services",
        strategy={},
    )

    assert result == "Seo Services | Expert Guide"


def test_build_h1(
    writer: ContentWriter,
) -> None:
    result = writer.build_h1(
        primary_keyword="seo services",
        strategy={"h1": "Professional SEO Services"},
    )

    assert result == "Professional SEO Services"


def test_build_meta_description(
    writer: ContentWriter,
) -> None:
    result = writer.build_meta_description(
        primary_keyword="seo services",
        strategy={},
    )

    assert "seo services" in result
    assert len(result) > 50


def test_build_headings(
    writer: ContentWriter,
) -> None:
    result = writer.build_headings(
        primary_keyword="seo services",
        strategy={},
        secondary_keywords=["seo agency"],
    )

    assert len(result) >= 4
    assert "Frequently Asked Questions" in result
    assert "seo agency" in result[2].lower()


def test_build_content_brief(
    writer: ContentWriter,
) -> None:
    result = writer.build_content_brief(
        primary_keyword="seo services",
        secondary_keywords=[
            "seo agency",
            "seo pricing",
        ],
        strategy={
            "search_intent": "commercial",
            "objective": "Help users evaluate SEO services.",
            "headings": [
                "SEO Services Overview",
                "Choosing an SEO Agency",
            ],
        },
        competitor_analysis={
            "content_gaps": [
                "Competitors lack detailed pricing information.",
                "Competitors have limited FAQ coverage.",
            ]
        },
    )

    assert result["primary_keyword"] == "seo services"
    assert result["secondary_keywords"] == [
        "seo agency",
        "seo pricing",
    ]
    assert result["search_intent"] == "commercial"
    assert len(result["headings"]) == 2
    assert len(result["content_gaps"]) == 2


@pytest.mark.asyncio
async def test_write(
    writer: ContentWriter,
    keyword_data: dict,
    strategy: dict,
) -> None:
    result = await writer.write(
        keyword_data=keyword_data,
        strategy=strategy,
        competitor_analysis={
            "content_gaps": [
                "Add more detailed FAQ coverage.",
            ]
        },
    )

    assert result["agent"] == "content_writer"
    assert result["status"] == "written"
    assert result["primary_keyword"] == "seo services"
    assert result["secondary_keywords"] == [
        "seo agency",
        "seo pricing",
    ]
    assert result["title"] == "SEO Services Guide"
    assert result["h1"] == "Professional SEO Services"
    assert len(result["headings"]) == 4
    assert len(result["body"]) == 4
    assert result["content_brief"]["search_intent"] == "commercial"


@pytest.mark.asyncio
async def test_write_requires_primary_keyword(
    writer: ContentWriter,
    strategy: dict,
) -> None:
    with pytest.raises(ValueError):
        await writer.write(
            keyword_data={},
            strategy=strategy,
        )


@pytest.mark.asyncio
async def test_write_many(
    writer: ContentWriter,
) -> None:
    jobs = [
        {
            "keyword_data": {
                "primary_keyword": {
                    "keyword": "SEO services",
                    "role": "primary",
                },
                "keywords": [
                    {
                        "keyword": "SEO agency",
                        "role": "secondary",
                    }
                ],
            },
            "strategy": {
                "search_intent": "commercial",
                "objective": "Help users evaluate SEO services.",
            },
        },
        {
            "keyword_data": {
                "primary_keyword": {
                    "keyword": "content marketing",
                    "role": "primary",
                },
                "keywords": [],
            },
            "strategy": {
                "search_intent": "informational",
                "objective": "Explain content marketing.",
            },
        },
    ]

    results = await writer.write_many(jobs)

    assert len(results) == 2
    assert results[0]["primary_keyword"] == "seo services"
    assert results[1]["primary_keyword"] == "content marketing"