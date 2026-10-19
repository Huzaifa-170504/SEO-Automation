from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.content_repository import ContentRepository
from app.storage.models import (
    Base,
    ContentJob,
    ContentReview,
    ContentStrategy,
    ContentTokenUsage,
    ContentVersion,
    SEOProject,
    WorkflowRun,
    utc_now,
)
from app.workflow.content_orchestrator import ContentWorkflowOrchestrator


class FakeWriter:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def write(self, strategy, requirements, previous_content=None, feedback=None):
        self.calls += 1
        body = (
            "# Best AI Trading Bots\n\nAI trading bot automated trading crypto bot. "
            "Useful and readable guidance."
        )
        return {
            "title": strategy["recommended_title"],
            "h1": strategy["recommended_title"],
            "meta_description": "AI trading bot guidance.",
            "headings": strategy["headings"],
            "body": body,
            "usage_records": [
                {
                    "agent_name": "content_writer",
                    "provider": "qwen",
                    "model": "qwen-seo:4b",
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "total_tokens": 300,
                }
            ],
        }

    async def close(self) -> None:
        self.closed = True


class RevisingReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"status": "needs_revision", "issues": ["Improve the introduction"]}
        return {"status": "approved", "issues": []}


class AlwaysFailReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, **kwargs):
        del kwargs
        self.calls += 1
        return {
            "status": "needs_revision",
            "issues": ["Search intent mismatch"],
            "revision_instructions": ["Align the article with search intent."],
            "revision_target": "content_strategist",
            "overall_score": 55,
        }


class FakeRetention:
    def __init__(self) -> None:
        self.called = False

    async def cleanup(self):
        self.called = True
        return {}


class FakeCompetitorFetcher:
    async def fetch_many(self, urls):
        return [
            {
                "url": url,
                "domain": "competitor.example",
                "status": "fetched",
                "title": "Competitor guide",
                "headings": ["How automated trading works", "Risk considerations"],
                "word_count": 1200,
                "content_excerpt": "Competitor research context.",
            }
            for url in urls
        ]


@pytest.mark.asyncio
async def test_content_generation_waits_for_explicit_manual_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    monkeypatch.setenv("QWEN_INPUT_COST_PER_MILLION", "1")
    monkeypatch.setenv("QWEN_OUTPUT_COST_PER_MILLION", "2")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, record) -> None:
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessions():
        async with factory() as session:
            yield session

    monkeypatch.setattr("app.workflow.content_orchestrator.get_session", sessions)
    report_path = tmp_path / "audit.json"
    report_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "url": "https://example.com/automation-guide",
                        "title": "AI Trading Bot Automation Guide",
                        "h2_headings": ["How automated trading works"],
                        "word_count": 850,
                    },
                    {
                        "url": "https://example.com/risk-controls",
                        "title": "AI Trading Bot Risk Controls",
                        "h2_headings": ["Risk considerations"],
                        "word_count": 1000,
                    },
                    {
                        "url": "https://example.com/contact",
                        "title": "Contact",
                        "word_count": 100,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    async with factory() as session:
        project = SEOProject(name="Example", website_url="https://example.com")
        session.add(project)
        await session.flush()
        audit = WorkflowRun(
            project_id=project.id,
            status="completed",
            completed_at=utc_now(),
            output_data={"report_path": str(report_path)},
        )
        session.add(audit)
        await session.commit()
        job = await ContentRepository().create_job(
            session,
            project.id,
            audit.id,
            "AI trading bot",
            ["automated trading", "crypto bot"],
            ["https://competitor.example/article"],
            "Best AI Trading Bots",
        )

    writer = FakeWriter()
    reviewer = RevisingReviewer()
    retention = FakeRetention()
    progress = []

    async def on_progress(stage, detail, revision):
        progress.append((stage, revision))

    result = await ContentWorkflowOrchestrator(
        writer=writer,
        reviewer=reviewer,
        retention_manager=retention,
        competitor_fetcher=FakeCompetitorFetcher(),
        progress_callback=on_progress,
        max_revisions=3,
    ).run(job.id)

    assert result["status"] == "awaiting_review"
    assert writer.calls == 1
    assert writer.closed is True
    assert retention.called is True
    assert ("awaiting_review", 0) in progress
    async with factory() as session:
        saved = await session.get(ContentJob, job.id)
        versions = list((await session.execute(select(ContentVersion))).scalars())
        reviews = list((await session.execute(select(ContentReview))).scalars())
        usages = list((await session.execute(select(ContentTokenUsage))).scalars())
        strategies = list((await session.execute(select(ContentStrategy))).scalars())
    assert saved.status == "awaiting_review"
    assert saved.final_version_id is None
    assert len(versions) == 1
    assert len(reviews) == 0
    assert len(usages) == 1
    assert len(strategies[0].strategy_data["website_reference_research"]) == 2
    assert strategies[0].strategy_data["website_reference_comparison"][
        "pages"
    ]
    assert result["usage"] == {
        "requests": 1,
        "input_tokens": 100,
        "output_tokens": 200,
        "total_tokens": 300,
        "estimated_cost_usd": "0.0005",
    }

    review_result = await ContentWorkflowOrchestrator(
        writer=writer,
        reviewer=reviewer,
        retention_manager=retention,
        competitor_fetcher=FakeCompetitorFetcher(),
        progress_callback=on_progress,
    ).review(job.id)
    assert review_result["status"] == "approved"
    assert review_result["revision_count"] == 1
    assert reviewer.calls == 2
    async with factory() as session:
        saved = await session.get(ContentJob, job.id)
        reviews = list((await session.execute(select(ContentReview))).scalars())
    assert saved.status == "approved"
    assert saved.revision_count == 1
    assert len(reviews) == 2

    async with factory() as session:
        limited_job = await ContentRepository().create_job(
            session,
            project.id,
            audit.id,
            "risk management",
            [],
            ["https://competitor.example/article"],
            "Risk management guide",
        )
    limited_writer = FakeWriter()
    await ContentWorkflowOrchestrator(
        writer=limited_writer,
        reviewer=AlwaysFailReviewer(),
        retention_manager=retention,
        competitor_fetcher=FakeCompetitorFetcher(),
        max_revisions=2,
    ).run(limited_job.id)
    failing_reviewer = AlwaysFailReviewer()
    limited_result = await ContentWorkflowOrchestrator(
        writer=limited_writer,
        reviewer=failing_reviewer,
        retention_manager=retention,
        competitor_fetcher=FakeCompetitorFetcher(),
        max_revisions=2,
    ).review(limited_job.id)
    assert limited_result["status"] == "human_review_required"
    assert limited_result["revision_count"] == 2
    assert failing_reviewer.calls == 3
    async with factory() as session:
        limited_saved = await session.get(ContentJob, limited_job.id)
    assert limited_saved.status == "human_review_required"
    assert limited_saved.revision_target == "content_strategist"
    await engine.dispose()


def test_strategy_has_a_rank_focused_content_specification() -> None:
    competitor = {
        "url": "https://competitor.example/guide",
        "status": "fetched",
        "title": "Competitor guide",
        "headings": ["AI trading bot risk controls"],
        "word_count": 1200,
        "relevant_passages": [{"text": "Relevant evidence"}],
        "analysis": {
            "quality_score": 76,
            "wording_style": "concise and direct",
            "content_nature": "practical/how-to",
        },
    }
    strategy = ContentWorkflowOrchestrator._strategy(
        {
            "primary_keyword": "AI trading bot",
            "secondary_keywords": ["automated trading"],
            "topic": "A practical guide",
            "website_url": "https://example.com",
        },
        {
            "competitors": [competitor],
            "coverage_opportunities": ["AI trading bot risk controls"],
            "content_gaps": [],
        },
        {"issues": []},
    )

    assert strategy["recommended_word_count"] == 1100
    assert strategy["content_format"]["word_count_range"] == [935, 1210]
    assert strategy["competitor_comparison"]["pages"][0]["quality_score"] == 76
    assert "ai trading bot" in strategy["recommended_title"].lower()


def test_selects_and_compares_two_relevant_audited_pages() -> None:
    pages = [
        {
            "url": "https://example.com/contact",
            "title": "Contact",
            "word_count": 100,
        },
        {
            "url": "https://example.com/automation-guide",
            "title": "AI Trading Bot Automation Guide",
            "meta_description": "Automated trading explained",
            "h2_headings": ["How automated trading works"],
            "word_count": 900,
        },
        {
            "url": "https://example.com/risk-controls",
            "title": "AI Trading Bot Risk Controls",
            "h2_headings": ["Risk management"],
            "word_count": 1200,
        },
        {
            "url": "https://example.com/company-news",
            "title": "Company news",
            "word_count": 1800,
        },
    ]

    selected = ContentWorkflowOrchestrator._select_internal_pages(
        pages, ["AI trading bot", "automated trading"]
    )

    assert [page["url"] for page in selected] == [
        "https://example.com/automation-guide",
        "https://example.com/risk-controls",
    ]


def test_internal_page_comparison_drives_content_ideas_and_length() -> None:
    internal_pages = [
        {
            "url": "https://example.com/automation-guide",
            "status": "fetched",
            "title": "Automation guide",
            "headings": ["Automation workflow"],
            "word_count": 800,
        },
        {
            "url": "https://example.com/risk-controls",
            "status": "fetched",
            "title": "Risk controls",
            "headings": ["Risk controls"],
            "word_count": 1200,
        },
    ]
    internal_comparison = ContentWorkflowOrchestrator._compare_competitors(
        internal_pages
    )

    strategy = ContentWorkflowOrchestrator._strategy(
        {
            "primary_keyword": "AI trading bot",
            "secondary_keywords": ["automated trading"],
            "topic": "AI trading bot guide",
            "website_url": "https://example.com",
        },
        {
            "competitors": [],
            "internal_pages": internal_pages,
            "internal_comparison": internal_comparison,
            "coverage_opportunities": ["Automation workflow", "Risk controls"],
        },
        {"issues": []},
    )

    assert strategy["recommended_word_count"] == 900
    assert strategy["website_reference_comparison"]["average_word_count"] == 1000
    assert len(strategy["website_reference_research"]) == 2
    assert set(strategy["internal_links"]) == {"related_page_1", "related_page_2"}
