from __future__ import annotations

import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from app.agents.manager import AgentManager
from app.agents.website_auditor import WebsiteAuditor
from app.models.issue import (
    IssueCategory,
    IssueSeverity,
    SEOIssue,
)
from app.storage.database import get_session, init_db
from app.storage.issue_repository import IssueRepository
from app.storage.models import SEOProject, WorkflowRun, utc_now
from app.storage.retention_manager import RetentionManager
from app.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def convert_page_findings(page: dict[str, Any]) -> list[SEOIssue]:
    """Convert supported page findings into structured SEO issues."""
    issues: list[SEOIssue] = []

    issue_mapping = {
        "Missing title": {
            "issue_type": "missing_title",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.HIGH,
            "recommendation": "Add a unique, descriptive title tag.",
        },
        "Title longer than 60 characters": {
            "issue_type": "long_title",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.LOW,
            "recommendation": "Shorten the title while retaining the primary topic.",
        },
        "Missing meta description": {
            "issue_type": "missing_meta_description",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": "Add a specific meta description for this page.",
        },
        "Meta description longer than 160 characters": {
            "issue_type": "long_meta_description",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.LOW,
            "recommendation": "Rewrite the meta description to about 160 characters.",
        },
        "Missing H1 heading": {
            "issue_type": "missing_h1",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": (
                "Add a descriptive H1 heading that reflects the page topic."
            ),
        },
        "Multiple H1 headings": {
            "issue_type": "multiple_h1",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": "Keep one primary H1 and use H2/H3 for subheadings.",
        },
        "Missing canonical tag": {
            "issue_type": "missing_canonical",
            "category": IssueCategory.TECHNICAL_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": "Declare the preferred URL with a canonical tag.",
        },
        "Page has a noindex robots directive": {
            "issue_type": "noindex_page",
            "category": IssueCategory.INDEXABILITY,
            "severity": IssueSeverity.HIGH,
            "recommendation": (
                "Remove noindex if this page should appear in search results; "
                "otherwise confirm the directive is intentional."
            ),
        },
        "Duplicate title found": {
            "issue_type": "duplicate_title",
            "category": IssueCategory.ON_PAGE_SEO,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": ("Review the title tag and make it unique to this page."),
        },
        "Duplicate page content found": {
            "issue_type": "duplicate_content",
            "category": IssueCategory.CONTENT,
            "severity": IssueSeverity.MEDIUM,
            "recommendation": "Consolidate, canonicalize, or differentiate duplicate page content.",
        },
    }

    for finding in page.get("issues", []):
        if finding.endswith("images missing alt text"):
            image_urls = page.get("images_missing_alt", [])

            issues.append(
                SEOIssue(
                    source_agent="website_auditor",
                    category=IssueCategory.CONTENT,
                    issue_type="missing_image_alt",
                    severity=IssueSeverity.LOW,
                    url=page.get("url"),
                    title="Images missing alt text",
                    description=(
                        f"{len(image_urls)} images on this page are missing alt text."
                    ),
                    evidence={
                        "image_count": len(image_urls),
                        "image_urls": image_urls,
                    },
                    recommendation=("Add meaningful alt text to informative images."),
                )
            )
            continue

        if finding.startswith("HTTP error"):
            issues.append(
                SEOIssue(
                    source_agent="website_auditor",
                    category=IssueCategory.TECHNICAL_SEO,
                    issue_type="http_error",
                    severity=IssueSeverity.HIGH,
                    url=page.get("url"),
                    title=finding,
                    description=f"{finding} on {page.get('url')}",
                    evidence={"status_code": page.get("status_code")},
                    recommendation=(
                        "Restore the page or redirect it to the most relevant working URL."
                    ),
                )
            )
            continue

        mapped = issue_mapping.get(finding)

        if mapped:
            issues.append(
                SEOIssue(
                    source_agent="website_auditor",
                    category=mapped["category"],
                    issue_type=mapped["issue_type"],
                    severity=mapped["severity"],
                    url=page.get("url"),
                    title=finding,
                    description=f"{finding} on {page.get('url')}",
                    evidence={
                        "title": page.get("title"),
                        "h1_headings": page.get("h1_headings", []),
                        "canonical": page.get("canonical"),
                    },
                    recommendation=mapped["recommendation"],
                )
            )

    return issues


def convert_crawl_errors(report: dict[str, Any]) -> list[SEOIssue]:
    """Convert crawler errors into structured SEO issues."""
    issues: list[SEOIssue] = []

    for error in report.get("errors", []):
        url = error.get("url")
        message = error.get("error", "Unknown crawl error")

        issues.append(
            SEOIssue(
                source_agent="website_auditor",
                category=IssueCategory.TECHNICAL_SEO,
                issue_type="sitemap_error",
                severity=IssueSeverity.MEDIUM,
                url=url,
                title="Sitemap crawl error",
                description=message,
                evidence={"error_message": message},
                recommendation=("Review the sitemap response and verify its format."),
            )
        )

    return issues


class WorkflowOrchestrator:
    """Coordinate audits, issue routing, specialist processing, and persistence."""

    def __init__(
        self,
        auditor: WebsiteAuditor | None = None,
        manager: AgentManager | None = None,
        repository: IssueRepository | None = None,
        report_path: str | None = None,
        progress_callback=None,
        retention_manager: RetentionManager | None = None,
    ) -> None:
        self.progress_callback = progress_callback
        self.auditor = auditor or WebsiteAuditor(
            progress_callback=progress_callback,
        )
        self.manager = manager or AgentManager()
        self.repository = repository or IssueRepository()
        self.report_path = report_path
        self.retention_manager = retention_manager or RetentionManager()

    async def _get_or_create_project(
        self,
        website_url: str,
        project_id: int | None,
        project_name: str,
    ) -> SEOProject:
        """Find an existing project or create one for this website."""
        async with get_session() as session:
            if project_id is not None:
                project = await session.get(SEOProject, project_id)

                if project is None:
                    raise ValueError(f"SEO project with ID {project_id} was not found.")

                return project

            result = await session.execute(
                select(SEOProject).where(SEOProject.website_url == website_url)
            )
            project = result.scalar_one_or_none()

            if project is None:
                hostname = urlparse(website_url).hostname or website_url

                project = SEOProject(
                    name=project_name or hostname,
                    website_url=website_url,
                )

                session.add(project)
                await session.flush()
                await session.commit()
                await session.refresh(project)

            return project

    async def _create_workflow_run(
        self,
        project_id: int,
        website_url: str,
        requester_id: str | None,
    ) -> WorkflowRun:
        """Create and persist a new running workflow record."""
        async with get_session() as session:
            workflow_run = WorkflowRun(
                project_id=project_id,
                requester_id=requester_id,
                status="running",
                trigger="manual",
                input_data={"website_url": website_url},
                started_at=utc_now(),
            )

            session.add(workflow_run)
            await session.commit()
            await session.refresh(workflow_run)

            return workflow_run

    async def _update_failed_run(
        self,
        workflow_run_id: int,
        error_message: str,
    ) -> None:
        """Mark a persisted workflow run as failed."""
        async with get_session() as session:
            workflow_run = await session.get(
                WorkflowRun,
                workflow_run_id,
            )

            if workflow_run is not None:
                workflow_run.status = "failed"
                workflow_run.error_message = error_message
                workflow_run.completed_at = utc_now()

                await session.commit()

    async def _discard_cancelled_run(self, workflow_run_id: int) -> None:
        """Remove every persisted artifact for a cancelled audit run."""
        paths = {Path(f"data/reports/audit_{workflow_run_id}.json")}
        async with get_session() as session:
            workflow_run = await session.get(WorkflowRun, workflow_run_id)
            if workflow_run is not None:
                output = workflow_run.output_data or {}
                saved_path = output.get("report_path")
                if isinstance(saved_path, str) and saved_path:
                    paths.add(Path(saved_path))
                await session.delete(workflow_run)
                await session.commit()

        for path in paths:
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                logger.exception(
                    "Could not delete report for cancelled workflow %s",
                    workflow_run_id,
                )

    async def _update_run_stage(
        self, workflow_run_id: int | None, status: str, current_agent: str | None
    ) -> None:
        if workflow_run_id is None:
            return
        async with get_session() as session:
            workflow_run = await session.get(WorkflowRun, workflow_run_id)
            if workflow_run is not None:
                workflow_run.status = status
                workflow_run.current_agent = current_agent
                await session.commit()

    async def run(
        self,
        website_url: str,
        project_id: int | None = None,
        workflow_run_id: int | None = None,
        project_name: str = "",
        requester_id: str | None = None,
    ) -> WorkflowState:
        """Run the full audit-to-specialist-to-database workflow."""
        state = WorkflowState(
            website_url=website_url,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            project_name=project_name,
        )
        state.mark_started()

        persisted_run_id: int | None = None

        try:
            await init_db()
            await self.retention_manager.ensure_capacity()

            # 1. Find or create the SEO project.
            state.current_agent = "project_repository"

            project = await self._get_or_create_project(
                website_url=website_url,
                project_id=project_id,
                project_name=project_name,
            )
            state.project_id = project.id

            # 2. Create or resume a persistent workflow run.
            state.current_agent = "workflow_repository"

            if workflow_run_id is None:
                workflow_run = await self._create_workflow_run(
                    project_id=project.id,
                    website_url=website_url,
                    requester_id=requester_id,
                )

                persisted_run_id = workflow_run.id
                state.workflow_run_id = workflow_run.id

            else:
                async with get_session() as session:
                    workflow_run = await session.get(
                        WorkflowRun,
                        workflow_run_id,
                    )

                    if workflow_run is None:
                        raise ValueError(
                            f"Workflow run {workflow_run_id} was not found."
                        )

                    if workflow_run.project_id != project.id:
                        raise ValueError(
                            "The workflow run does not belong to the selected project."
                        )

                    if (
                        requester_id is not None
                        and workflow_run.requester_id != requester_id
                    ):
                        raise ValueError(
                            "The workflow run does not belong to the requesting user."
                        )

                    workflow_run.status = "running"
                    workflow_run.error_message = None
                    workflow_run.started_at = utc_now()
                    workflow_run.completed_at = None

                    await session.commit()

                persisted_run_id = workflow_run_id

            logger.info(
                "Starting workflow %s for %s",
                persisted_run_id,
                website_url,
            )

            # 3. Run the website audit.
            state.current_agent = "website_auditor"
            await self._update_run_stage(
                persisted_run_id, "auditing", state.current_agent
            )

            report = await self.auditor.audit(website_url)

            # 4. Save the raw audit report.
            report_path = (
                self.report_path or f"data/reports/audit_{persisted_run_id}.json"
            )
            report_path = self.auditor.save_report(report, report_path)

            state.add_result(
                "website_auditor",
                {
                    "website": report.get("website"),
                    "pages_crawled": report.get("pages_crawled", 0),
                    "errors_count": report.get("errors_count", 0),
                    "report_path": report_path,
                },
            )

            # 5. Convert findings into structured issues.
            state.current_agent = "issue_processor"

            issues: list[SEOIssue] = []

            for page in report.get("pages", []):
                issues.extend(convert_page_findings(page))

            issues.extend(convert_crawl_errors(report))

            for issue in issues:
                issue.project_id = project.id
                issue.workflow_run_id = persisted_run_id

            # 6. Route issues to specialist agents.
            state.current_agent = "agent_manager"
            await self._update_run_stage(
                persisted_run_id, "routing", state.current_agent
            )

            self.manager.route_issues(issues)

            # Keep the machine-readable report useful to humans and downstream
            # integrations: every finding includes severity, nature, exact URL,
            # evidence, and a recommended action in addition to raw crawl data.
            report["issue_details"] = [
                issue.model_dump(mode="json") for issue in issues
            ]
            self.auditor.save_report(report, report_path)

            agent_counts = Counter(
                issue.assigned_agent or "unassigned" for issue in issues
            )

            state.add_result(
                "issue_processor",
                {
                    "issues_created": len(issues),
                    "agent_counts": dict(agent_counts),
                },
            )

            # 7. Save issues and complete the workflow run.
            state.current_agent = "issue_repository"
            await self._update_run_stage(
                persisted_run_id, "running", state.current_agent
            )

            async with get_session() as session:
                saved_count = await self.repository.save_issues(
                    session,
                    issues,
                )

                workflow_run = await session.get(
                    WorkflowRun,
                    persisted_run_id,
                )

                if workflow_run is None:
                    raise ValueError(f"Workflow run {persisted_run_id} was not found.")

                workflow_run.status = "completed"
                workflow_run.current_agent = None
                workflow_run.output_data = {
                    "website": report.get("website"),
                    "pages_crawled": report.get("pages_crawled", 0),
                    "errors_count": report.get("errors_count", 0),
                    "issues_created": len(issues),
                    "issues_saved": saved_count,
                    "agent_counts": dict(agent_counts),
                    "report_path": report_path,
                }
                workflow_run.error_message = None
                workflow_run.completed_at = utc_now()

                await session.commit()

            state.add_result(
                "issue_repository",
                {"issues_saved": saved_count},
            )

            state.current_agent = None
            state.mark_completed()

            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after audit completion")

            logger.info(
                "Workflow %s completed: %d issues saved",
                persisted_run_id,
                saved_count,
            )

        except asyncio.CancelledError:
            if persisted_run_id is not None:
                await self._discard_cancelled_run(persisted_run_id)
            logger.info("Cancelled and discarded workflow %s", persisted_run_id)
            raise
        except Exception as exc:
            logger.exception(
                "SEO workflow failed for %s",
                website_url,
            )

            state.add_error(
                state.current_agent or "workflow",
                str(exc),
            )
            state.mark_failed()

            if persisted_run_id is not None:
                try:
                    await self._update_failed_run(
                        persisted_run_id,
                        str(exc),
                    )
                except Exception:
                    logger.exception(
                        "Could not update failed workflow run %s",
                        persisted_run_id,
                    )
            try:
                await self.retention_manager.cleanup()
            except Exception:
                logger.exception("Retention cleanup failed after audit failure")

        return state
