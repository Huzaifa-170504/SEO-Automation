from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.agents.manager import AgentManager
from app.agents.website_auditor import WebsiteAuditor
from app.services.audit_pdf import build_audit_pdf
from app.web.models import AuditSummary, DemoAuditResult, DemoIssue, DemoPage
from app.web.repository import AuditRepository
from app.web.settings import WebSettings
from app.workflow.orchestrator import convert_crawl_errors, convert_page_findings


class AuditExecutionTimeoutError(TimeoutError):
    """Raised when a public demo crawl exceeds its total execution budget."""


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_client(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


class DemoAuditService:
    def __init__(self, repository: AuditRepository, settings: WebSettings) -> None:
        self.repository = repository
        self.settings = settings

    async def run(self, website_url: str, *, client_hash: str) -> DemoAuditResult:
        await self.repository.enforce_rate_limit(
            client_hash,
            limit=self.settings.demo_rate_limit_per_hour,
            window=timedelta(hours=1),
        )
        auditor = WebsiteAuditor(
            timeout=self.settings.demo_request_timeout_seconds,
            max_pages=self.settings.demo_max_pages,
            delay_seconds=0.1,
        )
        try:
            async with asyncio.timeout(self.settings.demo_timeout_seconds):
                report = await auditor.audit(website_url)
        except TimeoutError as exc:
            raise AuditExecutionTimeoutError from exc

        issues = []
        for page in report.get("pages", []):
            issues.extend(convert_page_findings(page))
        issues.extend(convert_crawl_errors(report))
        AgentManager().route_issues(issues)
        report["issue_details"] = [item.model_dump(mode="json") for item in issues]

        audit_id = uuid4()
        access_token = secrets.token_urlsafe(32)
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(hours=self.settings.demo_retention_hours)
        severity_counts = Counter(str(item.severity) for item in issues)
        warnings = []
        if report.get("crawl_limit_reached"):
            warnings.append(
                f"The public demo stopped at its {self.settings.demo_max_pages}-page safety limit."
            )

        result = DemoAuditResult(
            audit_id=audit_id,
            access_token=access_token,
            website_url=str(report.get("website") or website_url),
            created_at=created_at,
            expires_at=expires_at,
            summary=AuditSummary(
                pages_discovered=int(report.get("pages_discovered", 0)),
                pages_crawled=int(report.get("pages_crawled", 0)),
                pages_failed=int(report.get("pages_failed", 0)),
                issue_count=len(issues),
                crawl_limit_reached=bool(report.get("crawl_limit_reached")),
                severity_counts=dict(severity_counts),
            ),
            issues=[
                DemoIssue.model_validate(item.model_dump(mode="json"))
                for item in issues
            ],
            pages=[
                DemoPage(
                    url=str(page.get("url") or page.get("final_url") or ""),
                    status_code=page.get("status_code"),
                    title=str(page.get("title") or ""),
                    meta_description=str(page.get("meta_description") or ""),
                    h1_headings=list(page.get("h1_headings") or []),
                    canonical=page.get("canonical") or None,
                    image_count=int(page.get("image_count") or 0),
                    internal_link_count=int(page.get("internal_link_count") or 0),
                    external_link_count=int(page.get("external_link_count") or 0),
                    word_count=int(page.get("word_count") or 0),
                    language=page.get("language") or None,
                    issues=list(page.get("issues") or []),
                )
                for page in report.get("pages", [])
                if page.get("url") or page.get("final_url")
            ],
            warnings=warnings,
        )
        pdf = build_audit_pdf(
            report,
            str(audit_id),
            result.website_url,
            created_at,
        ).getvalue()
        await self.repository.save(
            result,
            access_token_hash=hash_secret(access_token),
            pdf_bytes=pdf,
        )
        return result

    async def get(self, audit_id: UUID, access_token: str) -> DemoAuditResult:
        return await self.repository.get(
            audit_id, access_token_hash=hash_secret(access_token)
        )

    async def get_pdf(self, audit_id: UUID, access_token: str) -> bytes:
        return await self.repository.get_pdf(
            audit_id, access_token_hash=hash_secret(access_token)
        )
