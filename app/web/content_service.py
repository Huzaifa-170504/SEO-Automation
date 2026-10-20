from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.agents.article_generator import ArticleGenerator
from app.agents.reviewer import Reviewer
from app.services.competitor_content import CompetitorContentFetcher
from app.services.content_pdf import build_content_pdf
from app.web.models import DemoAuditResult, DemoContentRequest, DemoContentResult
from app.web.repository import AuditRepository
from app.web.service import hash_secret
from app.web.settings import WebSettings
from app.workflow.content_orchestrator import ContentWorkflowOrchestrator


class ContentExecutionTimeoutError(TimeoutError):
    """Raised when public content generation exceeds its execution budget."""


class DemoContentService:
    def __init__(self, repository: AuditRepository, settings: WebSettings) -> None:
        self.repository = repository
        self.settings = settings

    async def run(
        self, payload: DemoContentRequest, *, client_hash: str
    ) -> DemoContentResult:
        await self.repository.enforce_rate_limit(
            hash_secret(f"content:{client_hash}"), limit=2, window=timedelta(hours=1)
        )
        audit = await self.repository.get(
            payload.audit_id, access_token_hash=hash_secret(payload.audit_token)
        )
        writer = ArticleGenerator()
        try:
            async with asyncio.timeout(self.settings.demo_timeout_seconds):
                result = await self._generate(payload, audit, writer)
        except TimeoutError as exc:
            raise ContentExecutionTimeoutError from exc
        finally:
            await writer.close()
        return result

    async def _generate(
        self,
        payload: DemoContentRequest,
        audit: DemoAuditResult,
        writer: ArticleGenerator,
    ) -> DemoContentResult:
        topic = payload.topic or payload.primary_keyword
        requirements = {
            "project_name": "Recruiter web demo",
            "website_url": audit.website_url,
            "primary_keyword": payload.primary_keyword,
            "secondary_keywords": payload.secondary_keywords,
            "competitor_urls": payload.competitor_urls,
            "topic": topic,
        }
        terms = [payload.primary_keyword, *payload.secondary_keywords, topic]
        audit_pages = [page.model_dump(mode="json") for page in audit.pages]
        selected_pages = ContentWorkflowOrchestrator._select_internal_pages(
            audit_pages, terms
        )
        fetcher = CompetitorContentFetcher(
            timeout=self.settings.demo_request_timeout_seconds, max_attempts=2
        )
        competitor_pages, internal_pages = await asyncio.gather(
            fetcher.fetch_many(payload.competitor_urls, terms),
            fetcher.fetch_many([item["url"] for item in selected_pages], terms),
        )
        fetched_competitors = [
            page for page in competitor_pages if page.get("status") == "fetched"
        ]
        if payload.competitor_urls and not fetched_competitors:
            raise ValueError(
                "None of the competitor pages could be read. Use public URLs without a bot challenge."
            )
        fetched_internal = [
            page for page in internal_pages if page.get("status") == "fetched"
        ]
        research_pages = [*fetched_competitors, *fetched_internal]
        competitors = {
            "source": "user_supplied_and_audited_website",
            "competitors": fetched_competitors,
            "internal_pages": fetched_internal,
            "unavailable_competitors": [
                page for page in competitor_pages if page.get("status") != "fetched"
            ],
            "unavailable_internal_pages": [
                page for page in internal_pages if page.get("status") != "fetched"
            ],
            "coverage_opportunities": ContentWorkflowOrchestrator._coverage_opportunities(
                research_pages, terms
            ),
            "content_gaps": [],
            "comparison": self._comparison(fetched_competitors),
            "internal_comparison": self._comparison(fetched_internal),
        }
        audit_context = {
            "selected_page_urls": [item["url"] for item in selected_pages],
            "selected_pages": selected_pages,
            "issues": [
                {
                    "type": issue.issue_type,
                    "url": issue.url,
                    "description": issue.description,
                    "recommendation": issue.recommendation,
                }
                for issue in audit.issues
                if issue.assigned_agent == "content_strategist"
            ][:12],
        }
        strategy = ContentWorkflowOrchestrator._strategy(
            requirements, competitors, audit_context
        )
        candidates = await writer.write_candidates(strategy, requirements)
        reviewer = Reviewer()
        evaluated = []
        for candidate in candidates:
            review = await reviewer.review(
                content=candidate,
                keyword_data=ContentWorkflowOrchestrator._keyword_data(requirements),
                strategy=strategy,
                competitor_analysis={"content_gaps": strategy.get("competitor_gaps") or []},
            )
            evaluated.append((candidate, review))
        article, review = max(
            evaluated, key=lambda item: float(item[1].get("overall_score") or 0)
        )
        revisions_used = 0
        if review.get("status") != "approved":
            feedback = [
                str(item)
                for item in (
                    review.get("revision_instructions") or review.get("issues") or []
                )
            ] or ["Improve SEO coverage, readability, and evidence alignment."]
            article = await writer.write(
                strategy,
                requirements,
                previous_content=str(article.get("body") or ""),
                feedback=feedback,
            )
            review = await reviewer.review(
                content=article,
                keyword_data=ContentWorkflowOrchestrator._keyword_data(requirements),
                strategy=strategy,
                competitor_analysis={"content_gaps": strategy.get("competitor_gaps") or []},
            )
            revisions_used = 1

        content_id = uuid4()
        access_token = secrets.token_urlsafe(32)
        created_at = datetime.now(UTC)
        status = (
            "approved" if review.get("status") == "approved" else "human_review_required"
        )
        result = DemoContentResult(
            content_id=content_id,
            access_token=access_token,
            audit_id=payload.audit_id,
            website_url=audit.website_url,
            primary_keyword=payload.primary_keyword,
            secondary_keywords=payload.secondary_keywords,
            competitor_urls=payload.competitor_urls,
            topic=topic,
            status=status,
            created_at=created_at,
            expires_at=created_at + timedelta(hours=self.settings.demo_retention_hours),
            research=competitors,
            strategy=strategy,
            article=article,
            review=review,
            revisions_used=revisions_used,
        )
        pdf = build_content_pdf(
            {
                "job_id": int(content_id.int % 1_000_000_000),
                "status": result.status,
                "website": result.website_url,
                "primary_keyword": result.primary_keyword,
                "strategy": {"research": result.research, "strategy": result.strategy},
                "drafts": [{"version": 1, **result.article}],
                "reviews": [result.review],
                "final_content": result.article,
            }
        ).getvalue()
        await self.repository.save_content(
            result, access_token_hash=hash_secret(access_token), pdf_bytes=pdf
        )
        return result

    @staticmethod
    def _comparison(pages: list[dict[str, object]]) -> dict[str, object]:
        if not pages:
            return {"dimensions": [], "average_word_count": 0, "pages": []}
        return ContentWorkflowOrchestrator._compare_competitors(pages)

    async def get(self, content_id: UUID, token: str) -> DemoContentResult:
        return await self.repository.get_content(
            content_id, access_token_hash=hash_secret(token)
        )

    async def get_pdf(self, content_id: UUID, token: str) -> bytes:
        return await self.repository.get_content_pdf(
            content_id, access_token_hash=hash_secret(token)
        )
