from __future__ import annotations

from typing import Any, ClassVar

from app.models.contracts import (
    ActionType,
    AgentExecutionResult,
    ContentStrategy,
    ContentStrategyRequest,
)
from app.models.issue import SEOIssue


class ContentStrategist:
    """
    Specialist agent for content and on-page SEO issues.

    Responsibilities:
    - Analyze content-related SEO issues.
    - Identify the likely content problem.
    - Recommend a practical optimization strategy.
    - Produce structured recommendations for downstream agents.

    This agent does NOT directly modify website content.
    """

    SUPPORTED_ISSUE_TYPES: ClassVar[set[str]] = {
        "missing_h1",
        "missing_title",
        "missing_meta_description",
        "duplicate_title",
        "content",
    }

    def __init__(self) -> None:
        self.name = "content_strategist"

    def can_handle(self, issue: SEOIssue) -> bool:
        """
        Return True when this agent is appropriate for the issue.
        """

        issue_type = issue.issue_type.strip().lower()

        return (
            issue_type in self.SUPPORTED_ISSUE_TYPES
            or str(issue.category).lower() in {
                "on_page_seo",
                "content",
            }
        )

    async def analyze(self, issue: SEOIssue) -> dict[str, Any]:
        """
        Analyze a single SEO issue and return a structured strategy.

        The first implementation intentionally uses deterministic rules.
        AI generation will be integrated after the specialist-agent contract
        is established and tested.
        """

        if not self.can_handle(issue):
            raise ValueError(
                f"ContentStrategist cannot handle issue type: "
                f"{issue.issue_type}"
            )

        issue_type = issue.issue_type.strip().lower()

        legacy_strategy = self._build_strategy(issue_type)
        strategy = self._validated_strategy(
            ContentStrategyRequest(
                project_id=issue.project_id or "unknown",
                issue=issue,
                page_url=issue.url,
            ),
            legacy_strategy,
        )

        return {
            "agent": self.name,
            "issue_id": issue.issue_id,
            "issue_type": issue_type,
            "url": issue.url,
            "status": "analyzed",
            "strategy": {
                **legacy_strategy,
                **strategy.model_dump(mode="json", by_alias=True),
            },
        }

    async def analyze_request(
        self, request: ContentStrategyRequest
    ) -> AgentExecutionResult[ContentStrategy]:
        """Typed strategist interface used by new workflow integrations."""
        if not self.can_handle(request.issue):
            raise ValueError(
                f"ContentStrategist cannot handle issue type: {request.issue.issue_type}"
            )
        legacy = self._build_strategy(request.issue.issue_type.strip().lower())
        strategy = self._validated_strategy(request, legacy)
        return AgentExecutionResult(
            success=True,
            status="analyzed",
            agent_name=self.name,
            data=strategy,
            source_urls=[request.page_url] if request.page_url else [],
        )

    @staticmethod
    def _validated_strategy(
        request: ContentStrategyRequest, legacy: dict[str, Any]
    ) -> ContentStrategy:
        issue_type = request.issue.issue_type.strip().lower()
        actions = {
            "missing_meta_description": ActionType.METADATA_ONLY,
            "missing_title": ActionType.METADATA_ONLY,
            "missing_h1": ActionType.HEADING_FIX,
            "duplicate_title": ActionType.METADATA_ONLY,
            "content": ActionType.CONTENT_UPDATE,
            "thin_content": ActionType.CONTENT_EXPANSION,
            "content_gap": ActionType.NEW_ARTICLE,
        }
        action_type = actions.get(issue_type, ActionType.CONTENT_UPDATE)
        needs_article = action_type in {
            ActionType.CONTENT_UPDATE,
            ActionType.CONTENT_EXPANSION,
            ActionType.NEW_ARTICLE,
            ActionType.LANDING_PAGE,
            ActionType.SERVICE_PAGE,
        }
        return ContentStrategy(
            issue_id=request.issue.issue_id,
            problem_summary=legacy["problem"],
            objective=legacy["objective"],
            search_intent=request.search_intent,
            recommended_action_type=action_type,
            priority=legacy["priority"],
            target_audience=request.target_audience,
            primary_keyword=request.primary_keyword,
            secondary_keywords=request.secondary_keywords,
            content_type="article" if needs_article else None,
            recommended_word_count_min=600 if needs_article else None,
            recommended_word_count_max=1600 if needs_article else None,
            key_topics=[request.primary_keyword] if request.primary_keyword else [],
            content_gaps=(
                request.competitor_insights.content_gaps
                if request.competitor_insights
                else []
            ),
            recommended_actions=legacy["actions"],
            CTA=None,
            constraints=["Do not invent unsupported facts or sources."],
            confidence=0.95,
        )

    def _build_strategy(self, issue_type: str) -> dict[str, Any]:
        """
        Build a deterministic strategy for the supported issue type.

        Keeping this logic separate makes it easy to replace or augment
        these recommendations with Gemini/Qwen reasoning later.
        """

        strategies: dict[str, dict[str, Any]] = {
            "missing_h1": {
                "problem": "The page does not contain a clear H1 heading.",
                "objective": (
                    "Establish a single, descriptive primary heading that "
                    "clearly communicates the main topic of the page."
                ),
                "actions": [
                    "Add one primary H1 heading to the page.",
                    "Make the H1 accurately describe the page's main topic.",
                    "Use the primary search intent as guidance.",
                    "Avoid stuffing the H1 with unnecessary keywords.",
                    "Keep the H1 distinct from the page title when appropriate.",
                ],
                "priority": "high",
            },
            "missing_title": {
                "problem": "The page is missing an HTML title element.",
                "objective": (
                    "Create a concise and descriptive title that represents "
                    "the page accurately in search results."
                ),
                "actions": [
                    "Add a unique HTML title element.",
                    "Describe the primary topic of the page clearly.",
                    "Place the most important topic or keyword naturally.",
                    "Keep the title concise enough to reduce truncation risk.",
                    "Make the title unique across the website.",
                ],
                "priority": "high",
            },
            "missing_meta_description": {
                "problem": "The page is missing a meta description.",
                "objective": (
                    "Create a useful search-result description that accurately "
                    "summarizes the page and encourages relevant clicks."
                ),
                "actions": [
                    "Add a unique meta description.",
                    "Summarize the page's primary value or purpose.",
                    "Include the primary topic naturally.",
                    "Write for users rather than keyword density.",
                    "Avoid duplicating descriptions across pages.",
                ],
                "priority": "medium",
            },
            "duplicate_title": {
                "problem": "Multiple pages appear to use the same title.",
                "objective": (
                    "Give each affected page a unique title aligned with its "
                    "specific search intent and content."
                ),
                "actions": [
                    "Identify the pages sharing the duplicate title.",
                    "Determine the unique purpose of each page.",
                    "Create a distinct title for every affected URL.",
                    "Use page-specific topics or value propositions.",
                    "Avoid changing titles solely by adding arbitrary numbers.",
                ],
                "priority": "high",
            },
            "content": {
                "problem": "The page has a content-related SEO issue.",
                "objective": (
                    "Improve the page so its content better satisfies the "
                    "target search intent and provides clear topical value."
                ),
                "actions": [
                    "Identify the primary search intent.",
                    "Clarify the page's main topic.",
                    "Improve content structure with meaningful headings.",
                    "Remove unnecessary or repetitive content.",
                    "Strengthen useful information and topical coverage.",
                    "Ensure the content provides a clear value to visitors.",
                ],
                "priority": "medium",
            },
        }

        return strategies.get(
            issue_type,
            {
                "problem": "The page has a content-related SEO issue.",
                "objective": "Improve the page's content quality and relevance.",
                "actions": [
                    "Review the page's primary search intent.",
                    "Improve topical relevance.",
                    "Improve content structure and clarity.",
                    "Remove unnecessary repetition.",
                ],
                "priority": "medium",
            },
        )

    async def analyze_many(
        self,
        issues: list[SEOIssue],
    ) -> list[dict[str, Any]]:
        """
        Analyze multiple content-related issues.
        """

        results: list[dict[str, Any]] = []

        for issue in issues:
            if self.can_handle(issue):
                result = await self.analyze(issue)
                results.append(result)

        return results
