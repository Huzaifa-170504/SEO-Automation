
from __future__ import annotations

import logging
from typing import ClassVar

from app.models.contracts import RoutingDecision, RoutingRequest
from app.models.issue import SEOIssue

logger = logging.getLogger(__name__)


class AgentManager:
    """Routes SEO issues to the appropriate specialist agent."""

    # Default agent for each issue category
    CATEGORY_ROUTING: ClassVar[dict[str, str]] = {
        "technical_seo": "website_auditor",
        "on_page_seo": "content_strategist",
        "content": "content_strategist",
        "links": "website_auditor",
        "indexability": "website_auditor",
        "performance": "website_auditor",
        "keywords": "content_strategist",
        "competitors": "content_strategist",
    }

    # More specific routing rules override category defaults
    ISSUE_ROUTING: ClassVar[dict[str, str]] = {
        "missing_h1": "content_strategist",
        "missing_title": "content_strategist",
        "missing_meta_description": "content_strategist",
        "duplicate_title": "content_strategist",
        "missing_image_alt": "content_writer",
        "keyword_gap": "content_strategist",
        "competitor_content_gap": "content_strategist",
        "broken_internal_link": "website_auditor",
        "sitemap_error": "website_auditor",
        "slow_page": "website_auditor",
    }

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return one deterministic, non-recursive routing decision."""
        issue = request.issue
        available = set(request.available_agents)

        issue_type = issue.issue_type.strip().lower()
        agent = self.ISSUE_ROUTING.get(issue_type)
        reason = f"Exact issue-type rule: {issue_type}"
        confidence = 0.98
        fallback_used = False
        if agent is None:
            category = str(issue.category)
            agent = self.CATEGORY_ROUTING.get(category)
            reason = f"Category rule: {category}"
            confidence = 0.9
        if agent is None or agent not in available or agent == "agent_manager":
            agent = "website_auditor"
            fallback_used = True
            confidence = 0.5
            reason = "Unknown or unavailable owner; deterministic technical fallback"
        if agent not in available:
            raise ValueError("No safe specialist is available for this issue.")

        issue.assigned_agent = agent
        decision = RoutingDecision(
            assigned_agent=agent,
            reason=reason,
            confidence=confidence,
            fallback_used=fallback_used,
        )
        logger.info(
            "seo_issue_routed",
            extra={
                "project_id": request.project_id,
                "issue_id": issue.issue_id,
                "agent": agent,
                "fallback_used": fallback_used,
            },
        )
        return decision

    def assign_agent(self, issue: SEOIssue) -> str:
        """Backward-compatible shortcut returning only the assigned agent name."""
        decision = self.route(
            RoutingRequest(
                issue=issue,
                project_id=issue.project_id or "unknown",
                available_agents=[
                    "website_auditor",
                    "content_strategist",
                    "content_writer",
                ],
            )
        )
        issue.evidence = {
            **issue.evidence,
            "routing": decision.model_dump(mode="json"),
        }
        return decision.assigned_agent

    def route_issues(self, issues: list[SEOIssue]) -> list[SEOIssue]:
        """Assign an agent to every issue and return the updated list."""

        for issue in issues:
            self.assign_agent(issue)

        return issues
