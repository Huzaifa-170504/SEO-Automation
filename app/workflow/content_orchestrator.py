from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.agents.article_generator import ArticleGenerator
from app.agents.reviewer import Reviewer
from app.services.competitor_content import CompetitorContentFetcher
from app.storage.content_repository import ContentRepository
from app.storage.database import get_session
from app.storage.models import SEOIssueRecord, WorkflowRun
from app.storage.retention_manager import RetentionManager
from app.workflow.cost_controller import CostController

ProgressCallback = Callable[[str, str, int], Awaitable[None] | None]
logger = logging.getLogger(__name__)


class ContentWorkflowOrchestrator:
    def __init__(
        self,
        repository: ContentRepository | None = None,
        writer: ArticleGenerator | None = None,
        reviewer: Reviewer | None = None,
        retention_manager: RetentionManager | None = None,
        competitor_fetcher: CompetitorContentFetcher | None = None,
        progress_callback: ProgressCallback | None = None,
        max_revisions: int | None = None,
    ) -> None:
        self.repository = repository or ContentRepository()
        self.writer = writer or ArticleGenerator()
        self.reviewer = reviewer or Reviewer()
        self.retention_manager = retention_manager or RetentionManager()
        self.competitor_fetcher = competitor_fetcher or CompetitorContentFetcher()
        self.progress_callback = progress_callback
        self.max_revisions = (
            max_revisions
            if max_revisions is not None
            else int(os.getenv("MAX_CONTENT_REVISIONS", "3"))
        )
        self.cost_controller = CostController()

    async def run(self, job_id: int) -> dict[str, Any]:
        try:
            async with get_session() as session:
                job = await self.repository.get_job(session, job_id)
                if job is None:
                    raise ValueError(f"Content job {job_id} was not found.")
                requirements = self._requirements(job)
                audit_context = await self._audit_context(
                    session, job.audit_run_id, requirements
                )

            await self._status(job_id, "strategy_running", "content_strategist")
            await self._progress(
                "strategy", "Selecting and fetching relevant website pages", 0
            )
            competitor_urls = [item.url for item in job.competitors]
            relevance_terms = [
                requirements["primary_keyword"],
                *requirements["secondary_keywords"],
                requirements["topic"],
            ]
            competitor_pages = await self._fetch_research_pages(
                competitor_urls,
                relevance_terms,
                "Competitor research",
            )
            internal_urls = audit_context.get("selected_page_urls", [])
            internal_pages = await self._fetch_research_pages(
                internal_urls,
                relevance_terms,
                "Website research",
            )
            unavailable = [
                page for page in competitor_pages if page.get("status") != "fetched"
            ]
            fetched_pages = [
                page for page in competitor_pages if page.get("status") == "fetched"
            ]
            fetched_internal_pages = [
                page for page in internal_pages if page.get("status") == "fetched"
            ]
            if competitor_urls and not fetched_pages:
                details = "; ".join(
                    f"{page['url']}: {page.get('error', 'unavailable')}"
                    for page in unavailable
                )
                raise RuntimeError(
                    "None of the competitor pages could be read. "
                    f"Check that the URLs are reachable without credentials and try replacements. Details: {details}"
                )
            if unavailable:
                await self._progress(
                    "strategy",
                    f"Continuing with {len(fetched_pages)}/{len(competitor_urls)} accessible competitor pages",
                    0,
                )
            await self._progress(
                "strategy",
                f"Fetched {len(fetched_internal_pages)}/{len(internal_urls)} related "
                f"website pages and {len(fetched_pages)}/{len(competitor_urls)} competitor "
                "pages; comparing ideas, quality, format, and length",
                0,
            )
            comparison = (
                self._compare_competitors(fetched_pages)
                if fetched_pages
                else {
                    "dimensions": [],
                    "average_word_count": 0,
                    "shortest_word_count": 0,
                    "longest_word_count": 0,
                    "average_quality_score": 0,
                    "wording_styles": [],
                    "content_natures": [],
                    "pages": [],
                }
            )
            internal_comparison = (
                self._compare_competitors(fetched_internal_pages)
                if fetched_internal_pages
                else {
                    "dimensions": [],
                    "average_word_count": 0,
                    "pages": [],
                }
            )
            research_pages = [*fetched_pages, *fetched_internal_pages]
            competitors = {
                "source": "user_supplied_and_audited_website",
                "competitors": fetched_pages,
                "internal_pages": fetched_internal_pages,
                "unavailable_internal_pages": [
                    page for page in internal_pages if page.get("status") != "fetched"
                ],
                "unavailable_competitors": unavailable,
                "coverage_opportunities": self._coverage_opportunities(
                    research_pages, relevance_terms
                ),
                "content_gaps": [],
                "comparison": comparison,
                "internal_comparison": internal_comparison,
            }
            strategy = self._strategy(requirements, competitors, audit_context)
            async with get_session() as session:
                await self.repository.save_strategy(session, job_id, strategy)
            await self._progress(
                "strategy",
                "Page comparison saved; focused content strategy completed",
                0,
            )

            await self._status(job_id, "writer_running", "content_writer")
            await self._progress("writer", "Writing model drafts", 0)
            write_candidates = getattr(self.writer, "write_candidates", None)
            if callable(write_candidates):
                contents = await write_candidates(
                    strategy=strategy,
                    requirements=requirements,
                )
            else:
                contents = [
                    await self.writer.write(
                        strategy=strategy,
                        requirements=requirements,
                    )
                ]

            saved: list[tuple[Any, dict[str, Any]]] = []
            for content in contents:
                async with get_session() as session:
                    version = await self.repository.save_version(
                        session, job_id, content
                    )
                    await self._save_usage(
                        session, job_id, content.get("usage_records") or []
                    )
                saved.append((version, content))
            target_words = int(strategy.get("recommended_word_count") or 0)
            saved.sort(key=lambda item: abs(int(item[0].word_count) - target_words))
            version, content = saved[0]
            await self._status(job_id, "awaiting_review", None)
            await self._progress(
                "awaiting_review",
                f"{len(saved)} draft(s) saved; waiting for /review",
                0,
            )
            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after content generation")
            return {
                "job_id": job_id,
                "status": "awaiting_review",
                "content": content,
                "draft_count": len(saved),
                "word_count": version.word_count,
                "usage": self.cost_controller.summary(),
            }
        except Exception as exc:
            async with get_session() as session:
                await self.repository.set_status(
                    session,
                    job_id,
                    "failed",
                    error_message=str(exc),
                )
            await self._progress("failed", str(exc), 0)
            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after content failure")
            raise
        finally:
            await self.writer.close()

    async def review(self, job_id: int) -> dict[str, Any]:
        """Review and perform bounded, orchestrator-controlled targeted revisions."""
        all_reviews: list[dict[str, Any]] = []
        try:
            async with get_session() as session:
                job = await self.repository.get_job(session, job_id)
                if job is None:
                    raise ValueError(f"Content job {job_id} was not found.")
                strategy_record = max(
                    job.strategies, key=lambda item: item.id, default=None
                )
                if strategy_record is None:
                    raise ValueError("The content strategy is unavailable.")
                strategy = dict(strategy_record.strategy_data)
                requirements = self._requirements(job)
                revision_count = int(job.revision_count or 0)
                reviewed_ids = {item.content_version_id for item in job.reviews}
                versions = [
                    item for item in job.versions if item.id not in reviewed_ids
                ]
                resumed: tuple[Any, dict[str, Any]] | None = None
                if not versions and job.status == "needs_revision" and job.reviews:
                    latest_review = max(job.reviews, key=lambda item: item.id)
                    resumed_version = next(
                        (
                            item
                            for item in job.versions
                            if item.id == latest_review.content_version_id
                        ),
                        None,
                    )
                    if resumed_version is not None:
                        resumed = (
                            resumed_version,
                            dict(latest_review.feedback or {}),
                        )
            if not versions and resumed is None:
                raise ValueError("This content job has no reviewable drafts.")

            await self._status(job_id, "review_running", "reviewer", revision_count)
            await self._progress(
                "reviewer", f"Reviewing {len(versions)} saved draft(s)", revision_count
            )
            if resumed is not None:
                selected_version, selected_review = resumed
                all_reviews.append(selected_review)
            else:
                evaluated = await self._review_versions(
                    job_id, versions, requirements, strategy, revision_count
                )
                all_reviews.extend(item[1] for item in evaluated)
                selected_version, selected_review = self._select_review(
                    evaluated, strategy
                )

            while selected_review.get("status") != "approved":
                issues = self._review_instructions(selected_review)
                target = str(
                    selected_review.get("revision_target")
                    or self._infer_revision_target(issues)
                )
                if revision_count >= self.max_revisions:
                    async with get_session() as session:
                        await self.repository.set_status(
                            session,
                            job_id,
                            "human_review_required",
                            current_agent=None,
                            error_message="; ".join(issues),
                            revision_count=revision_count,
                            previous_review_status="needs_revision",
                            revision_target=target,
                            revision_reason="; ".join(issues),
                        )
                    await self._progress(
                        "human_review_required",
                        f"Maximum revision limit ({self.max_revisions}) reached",
                        revision_count,
                    )
                    return {
                        "job_id": job_id,
                        "status": "human_review_required",
                        "selected_version_id": selected_version.id,
                        "revision_count": revision_count,
                        "revision_target": target,
                        "reviews": all_reviews,
                    }

                revision_count += 1
                async with get_session() as session:
                    await self.repository.set_status(
                        session,
                        job_id,
                        "needs_revision",
                        current_agent=target,
                        error_message="; ".join(issues),
                        revision_count=revision_count,
                        previous_review_status=str(selected_review.get("status")),
                        revision_target=target,
                        revision_reason="; ".join(issues),
                    )
                await self._progress(
                    "revision",
                    f"Revision {revision_count}/{self.max_revisions}: {target}",
                    revision_count,
                )

                if target == "content_strategist":
                    strategy = self._revise_strategy(strategy, issues)
                    async with get_session() as session:
                        await self.repository.save_strategy(session, job_id, strategy)
                elif target == "content_writer":
                    strategy = self._revise_brief(strategy, issues)

                previous_body = str(selected_version.content.get("body") or "")
                revised = await self.writer.write(
                    strategy=strategy,
                    requirements=requirements,
                    previous_content=previous_body,
                    feedback=issues,
                )
                async with get_session() as session:
                    selected_version = await self.repository.save_version(
                        session, job_id, revised
                    )
                    await self._save_usage(
                        session, job_id, revised.get("usage_records") or []
                    )
                evaluated = await self._review_versions(
                    job_id,
                    [selected_version],
                    requirements,
                    strategy,
                    revision_count,
                )
                all_reviews.extend(item[1] for item in evaluated)
                selected_version, selected_review = evaluated[0]

            async with get_session() as session:
                await self.repository.approve(session, job_id, selected_version.id)
            await self._progress(
                "approved", "Quality review passed", revision_count
            )
            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after content review")
            return {
                "job_id": job_id,
                "status": "approved",
                "selected_version_id": selected_version.id,
                "revision_count": revision_count,
                "reviews": all_reviews,
            }
        except Exception as exc:
            async with get_session() as session:
                await self.repository.set_status(
                    session, job_id, "failed", error_message=str(exc)
                )
            logger.exception("content_review_failed", extra={"job_id": job_id})
            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after content review failure")
            raise
        finally:
            await self.writer.close()

    async def _review_versions(
        self,
        job_id: int,
        versions: list[Any],
        requirements: dict[str, Any],
        strategy: dict[str, Any],
        revision_number: int,
    ) -> list[tuple[Any, dict[str, Any]]]:
        evaluated: list[tuple[Any, dict[str, Any]]] = []
        competitor_analysis = {
            "content_gaps": strategy.get("competitor_gaps") or []
        }
        for version in versions:
            review = await self.reviewer.review(
                content=version.content,
                keyword_data=self._keyword_data(requirements),
                strategy=strategy,
                competitor_analysis=competitor_analysis,
            )
            review["provider"] = version.content.get("data_source", "unknown")
            review["revision_number"] = revision_number
            async with get_session() as session:
                await self.repository.save_review(session, job_id, version.id, review)
            evaluated.append((version, review))
        return evaluated

    @staticmethod
    def _select_review(
        evaluated: list[tuple[Any, dict[str, Any]]], strategy: dict[str, Any]
    ) -> tuple[Any, dict[str, Any]]:
        target_words = int(strategy.get("recommended_word_count") or 0)
        evaluated.sort(
            key=lambda item: (
                item[1].get("status") != "approved",
                -float(item[1].get("overall_score") or 0),
                int(item[1].get("issue_count", len(item[1].get("issues", [])))),
                abs(int(item[0].word_count) - target_words),
            )
        )
        return evaluated[0]

    @staticmethod
    def _review_instructions(review: dict[str, Any]) -> list[str]:
        values = review.get("revision_instructions") or review.get("issues") or []
        return [str(item) for item in values] or ["Improve the article quality."]

    @staticmethod
    def _infer_revision_target(instructions: list[str]) -> str:
        combined = " ".join(instructions).lower()
        if "search intent" in combined or "content gap" in combined:
            return "content_strategist"
        if "heading" in combined or "outline" in combined:
            return "content_writer"
        return "article_generator"

    @staticmethod
    def _revise_strategy(
        strategy: dict[str, Any], instructions: list[str]
    ) -> dict[str, Any]:
        revised = dict(strategy)
        revised["revision_instructions"] = instructions
        revised["seo_requirements"] = list(
            dict.fromkeys([*(strategy.get("seo_requirements") or []), *instructions])
        )
        return revised

    @staticmethod
    def _revise_brief(
        strategy: dict[str, Any], instructions: list[str]
    ) -> dict[str, Any]:
        revised = dict(strategy)
        revised["brief_revision_instructions"] = instructions
        return revised

    async def _status(
        self,
        job_id: int,
        status: str,
        agent: str | None,
        revision_count: int | None = None,
    ) -> None:
        async with get_session() as session:
            await self.repository.set_status(
                session,
                job_id,
                status,
                current_agent=agent,
                revision_count=revision_count,
            )

    async def _progress(self, stage: str, detail: str, revision: int) -> None:
        if self.progress_callback is None:
            return
        result = self.progress_callback(stage, detail, revision)
        if inspect.isawaitable(result):
            await result

    async def _fetch_research_pages(
        self,
        urls: list[str],
        relevance_terms: list[str],
        progress_label: str,
    ) -> list[dict[str, Any]]:
        if not urls:
            return []
        parameters = inspect.signature(self.competitor_fetcher.fetch_many).parameters

        async def progress(
            completed: int, total: int, url: str, status: str
        ) -> None:
            domain = url.split("/", 3)[2] if "://" in url else url
            await self._progress(
                "strategy",
                f"{progress_label} {completed}/{total}: {domain} ({status})",
                0,
            )

        options: dict[str, Any] = {}
        if "relevance_terms" in parameters:
            options["relevance_terms"] = relevance_terms
        if "progress_callback" in parameters:
            options["progress_callback"] = progress
        return await self.competitor_fetcher.fetch_many(urls, **options)

    async def _save_usage(
        self, session: Any, job_id: int, records: list[dict[str, Any]]
    ) -> None:
        for usage in records:
            provider = str(usage.get("provider") or "unknown")
            model = str(usage.get("model") or "unknown")
            prefix = provider.upper()
            self.cost_controller.set_pricing(
                model,
                os.getenv(f"{prefix}_INPUT_COST_PER_MILLION", "0"),
                os.getenv(f"{prefix}_OUTPUT_COST_PER_MILLION", "0"),
            )
            cost = self.cost_controller.record_usage(
                provider=provider,
                model_name=model,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
            await self.repository.save_token_usage(
                session, job_id, usage, cost.estimated_cost_usd
            )

    async def _audit_context(
        self,
        session: Any,
        audit_run_id: int | None,
        requirements: dict[str, Any],
    ) -> dict[str, Any]:
        if audit_run_id is None:
            return {"issues": [], "selected_page_urls": []}
        workflow_run = await session.get(WorkflowRun, audit_run_id)
        report: dict[str, Any] = {}
        if workflow_run is not None:
            report_path = (workflow_run.output_data or {}).get("report_path")
            if isinstance(report_path, str) and report_path:
                path = Path(report_path)
                try:
                    report = await asyncio.to_thread(
                        lambda: json.loads(path.read_text(encoding="utf-8"))
                    )
                except (OSError, json.JSONDecodeError):
                    logger.warning(
                        "Could not read audit report for content job: %s",
                        report_path,
                        exc_info=True,
                    )
        selected_pages = self._select_internal_pages(
            report.get("pages") or [],
            [
                requirements["primary_keyword"],
                *requirements["secondary_keywords"],
                requirements["topic"],
            ],
        )
        result = await session.execute(
            select(SEOIssueRecord)
            .where(
                SEOIssueRecord.workflow_run_id == audit_run_id,
                SEOIssueRecord.assigned_agent == "content_strategist",
            )
            .order_by(SEOIssueRecord.detected_at.desc())
            .limit(12)
        )
        return {
            "selected_page_urls": [page["url"] for page in selected_pages],
            "selected_pages": selected_pages,
            "issues": [
                {
                    "type": issue.issue_type,
                    "url": issue.url,
                    "description": issue.description,
                    "recommendation": issue.recommendation,
                }
                for issue in result.scalars()
            ]
        }

    @staticmethod
    def _select_internal_pages(
        pages: list[dict[str, Any]], relevance_terms: list[str]
    ) -> list[dict[str, Any]]:
        """Choose the two strongest audited pages for the requested article."""
        terms = CompetitorContentFetcher._terms(relevance_terms)
        excluded_paths = (
            "/contact",
            "/login",
            "/sign-in",
            "/signup",
            "/privacy",
            "/terms",
            "/account",
            "/author/",
            "/tag/",
        )
        ranked: list[tuple[int, int, int, dict[str, Any]]] = []
        seen: set[str] = set()
        for position, page in enumerate(pages):
            url = str(page.get("url") or page.get("final_url") or "")
            if not url or url in seen or any(marker in url.lower() for marker in excluded_paths):
                continue
            seen.add(url)
            headings = [
                *list(page.get("h1_headings") or []),
                *list(page.get("h2_headings") or []),
                *list(page.get("h3_headings") or []),
            ]
            searchable = " ".join(
                [
                    url,
                    str(page.get("title") or ""),
                    str(page.get("meta_description") or ""),
                    *[str(value) for value in headings],
                ]
            )
            relevance = CompetitorContentFetcher._score(searchable, terms)
            word_count = int(page.get("word_count") or 0)
            ranked.append((relevance, word_count, -position, page))
        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2]))
        return [
            {
                "url": str(item[3].get("url") or item[3].get("final_url")),
                "title": str(item[3].get("title") or ""),
                "audit_word_count": int(item[3].get("word_count") or 0),
                "relevance_score": item[0],
            }
            for item in ranked[:2]
        ]

    @staticmethod
    def _requirements(job: Any) -> dict[str, Any]:
        secondary = [
            item.keyword for item in job.keywords if item.keyword_type == "secondary"
        ]
        topic = job.topic or job.primary_keyword
        return {
            "project_name": job.project.name,
            "website_url": job.project.website_url,
            "primary_keyword": job.primary_keyword,
            "secondary_keywords": secondary,
            "competitor_urls": [item.url for item in job.competitors],
            "topic": topic,
        }

    @staticmethod
    def _coverage_opportunities(
        pages: list[dict[str, Any]], relevance_terms: list[str] | None = None
    ) -> list[str]:
        opportunities: list[str] = []
        seen: set[str] = set()
        terms = CompetitorContentFetcher._terms(relevance_terms or [])
        for page in pages:
            for heading in page.get("headings") or []:
                normalized = " ".join(str(heading).split()).strip(" -:;,.#")
                key = normalized.lower()
                related = not terms or any(term in key for term in terms)
                if related and 4 <= len(normalized) <= 120 and key not in seen:
                    seen.add(key)
                    opportunities.append(normalized)
        return opportunities[:10]

    @staticmethod
    def _compare_competitors(pages: list[dict[str, Any]]) -> dict[str, Any]:
        if not pages:
            raise ValueError("At least one fetched competitor page is required.")
        lengths = [int(page.get("word_count") or 0) for page in pages]
        analyses = [page.get("analysis") or {} for page in pages]
        quality_scores = [int(item.get("quality_score") or 0) for item in analyses]
        styles = [str(item.get("wording_style") or "not measured") for item in analyses]
        natures = [
            str(item.get("content_nature") or "not measured") for item in analyses
        ]
        average_length = sum(lengths) // len(lengths)
        return {
            "dimensions": ["content quality", "wording", "content nature", "length"],
            "average_word_count": average_length,
            "shortest_word_count": min(lengths),
            "longest_word_count": max(lengths),
            "average_quality_score": round(sum(quality_scores) / len(quality_scores)),
            "wording_styles": list(dict.fromkeys(styles)),
            "content_natures": list(dict.fromkeys(natures)),
            "pages": [
                {
                    "url": page.get("url"),
                    "title": page.get("title"),
                    "word_count": int(page.get("word_count") or 0),
                    "quality_score": int(
                        (page.get("analysis") or {}).get("quality_score") or 0
                    ),
                    "wording_style": (page.get("analysis") or {}).get("wording_style"),
                    "content_nature": (page.get("analysis") or {}).get(
                        "content_nature"
                    ),
                    "relevant_passage_count": len(page.get("relevant_passages") or []),
                }
                for page in pages
            ],
        }

    @staticmethod
    def _keyword_data(requirements: dict[str, Any]) -> dict[str, Any]:
        primary = requirements["primary_keyword"]
        return {
            "primary_keyword": {"keyword": primary, "role": "primary"},
            "keywords": [
                {"keyword": primary, "role": "primary"},
                *[
                    {"keyword": keyword, "role": "secondary"}
                    for keyword in requirements["secondary_keywords"]
                ],
            ],
        }

    @staticmethod
    def _strategy(
        requirements: dict[str, Any],
        competitors: dict[str, Any],
        audit_context: dict[str, Any],
    ) -> dict[str, Any]:
        primary = requirements["primary_keyword"]
        topic = requirements["topic"].strip()
        title_keyword = primary[:1].upper() + primary[1:]
        title = (
            topic if primary.lower() in topic.lower() else f"{title_keyword}: {topic}"
        )
        title = title[:60].rstrip(" -:;,.")
        secondary = requirements["secondary_keywords"]
        fetched_competitors = competitors.get("competitors", [])
        fetched_internal_pages = competitors.get("internal_pages", [])
        benchmark_pages = [*fetched_competitors, *fetched_internal_pages]
        benchmark_word_counts = [
            int(page.get("word_count") or 0)
            for page in benchmark_pages
            if page.get("status") == "fetched"
        ]
        benchmark_average = (
            sum(benchmark_word_counts) // len(benchmark_word_counts)
            if benchmark_word_counts
            else 0
        )
        target_word_count = (
            max(600, min(1600, int(round((benchmark_average * 0.9) / 50) * 50)))
            if benchmark_average
            else 800
        )
        comparison = competitors.get("comparison") or (
            ContentWorkflowOrchestrator._compare_competitors(fetched_competitors)
            if fetched_competitors
            else {
                "dimensions": [],
                "average_word_count": 0,
                "pages": [],
            }
        )
        internal_comparison = competitors.get("internal_comparison") or {
            "dimensions": [],
            "average_word_count": 0,
            "pages": [],
        }
        coverage_topics = competitors.get("coverage_opportunities", [])[:4]
        headings = [f"Understanding {primary.title()}"]
        headings.extend(
            f"{keyword[:1].upper() + keyword[1:]} in Practice"
            for keyword in secondary[:2]
        )
        if coverage_topics:
            headings.append("Key Considerations and Trade-Offs")
        headings.append("Practical Next Steps")
        # Reserve one H2 for the required FAQ so the generated article cannot
        # exceed the reviewer's five-H2 ceiling.
        headings = list(dict.fromkeys(headings))[:4]
        intent_text = f"{primary} {topic}".lower()
        if any(
            marker in intent_text for marker in ("best", " vs ", "compare", "review")
        ):
            search_intent = "commercial comparison"
        elif any(
            marker in intent_text for marker in ("buy", "price", "cost", "service")
        ):
            search_intent = "commercial decision"
        else:
            search_intent = "focused informational"
        lower_bound = max(500, int(target_word_count * 0.85))
        upper_bound = int(target_word_count * 1.1)
        expected_h2_count = len(headings) + 1
        reviewer_acceptance_contract = {
            "word_count_range": [lower_bound, upper_bound],
            "h1_count": 1,
            "h2_count": expected_h2_count,
            "primary_keyword_first_100_words": primary,
            "primary_keyword_in_h2": primary,
            "secondary_keywords_required": secondary,
            "coverage_phrases_required": coverage_topics,
            "maximum_primary_keyword_occurrences": 20,
            "faq_heading": "Frequently Asked Questions",
            "faq_questions": 1,
            "duplicate_headings_allowed": False,
        }
        return {
            "recommended_action_type": "new_article",
            "problem_summary": "Create focused content for the selected topic and search intent.",
            "objective": f"Provide the most useful answer for people researching {primary}.",
            "priority": "medium",
            "confidence": 0.9,
            "search_intent": search_intent,
            "target_audience": f"People specifically researching {primary}",
            "recommended_title": title,
            "meta_description": (
                f"Learn how {primary} works, compare important considerations, "
                "and make an informed decision."
            )[:155],
            "outline": headings,
            "headings": headings,
            "keyword_strategy": {
                "primary": primary,
                "secondary": secondary,
                "placement": [
                    "SEO title",
                    "H1",
                    "first 100 words",
                    "one relevant H2",
                ],
                "rule": (
                    "Include every secondary keyword exactly as written at least once, "
                    "only in a context that answers the reader's question."
                ),
            },
            "entities": secondary,
            "questions": [f"What should someone know before choosing {primary}?"],
            "coverage_topics": coverage_topics,
            "competitor_gaps": coverage_topics,
            "competitor_research": fetched_competitors,
            "competitor_comparison": comparison,
            "website_reference_research": fetched_internal_pages,
            "website_reference_comparison": internal_comparison,
            "competitor_benchmark": {
                "pages_compared": len(benchmark_pages),
                "average_word_count": benchmark_average,
                "quality_goal": (
                    "Use the strongest ideas from the compared pages, write original "
                    "wording and structure, and stop when the search intent is satisfied."
                ),
            },
            "internal_links": {
                f"related_page_{index}": page.get("url")
                for index, page in enumerate(fetched_internal_pages, 1)
                if page.get("url")
            },
            "recommended_word_count": target_word_count,
            "reviewer_acceptance_contract": reviewer_acceptance_contract,
            "content_format": {
                "word_count_range": [lower_bound, upper_bound],
                "introduction_words": [60, 100],
                "h2_count": [expected_h2_count, expected_h2_count],
                "faq_questions": 1,
                "title_max_characters": 60,
                "meta_description_max_characters": 155,
                "required_sections": [
                    "direct answer in the introduction",
                    "decision criteria or practical steps",
                    "one Frequently Asked Questions section with one useful question",
                    "concise conclusion",
                ],
            },
            "seo_requirements": [
                "Answer the primary search intent before adding background detail",
                "Use one H1 and only the H2 sections needed to answer the intent",
                "Use the primary keyword in the title, H1, first 100 words, and one H2",
                "Include every secondary keyword phrase at least once without stuffing",
                "Include every coverage topic phrase verbatim at least once",
                "Add exactly one FAQ question under a Frequently Asked Questions H2",
                "Use the audited website reference pages as ideas, never as copy",
                "Add a contextual link to a selected related page only when useful",
                "Improve on compared-page coverage without copying wording or structure",
                "Prioritize accuracy, original practical value, and readability",
                "Do not pad the article to exceed the useful competitor-derived target",
            ],
            "audit_context": audit_context,
        }
