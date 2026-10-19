from __future__ import annotations

from typing import Any

from app.config import get_runtime_config
from app.models.contracts import (
    ContentBrief,
    ContentSection,
    ContentStrategy,
    InternalLinkRecommendation,
)


class ContentWriter:
    """
    Specialist agent for SEO content generation.

    Responsibilities:
    - Consume an approved content strategy.
    - Use approved primary and secondary keywords.
    - Generate structured page-content components.
    - Prepare content that can later be generated or expanded by an LLM.

    This initial implementation is deterministic. Gemini/Qwen generation
    will be integrated after the writer contract is tested.
    """

    def __init__(self) -> None:
        self.name = "content_writer"

    def _normalize_text(self, value: Any) -> str:
        """Normalize a text value."""

        if value is None:
            return ""

        return " ".join(str(value).strip().split())

    def _extract_primary_keyword(
        self,
        keyword_data: dict[str, Any],
    ) -> str:
        """Extract the approved primary keyword."""

        primary = keyword_data.get("primary_keyword") or {}

        if isinstance(primary, dict):
            keyword = self._normalize_text(primary.get("keyword"))
        else:
            keyword = self._normalize_text(primary)

        if not keyword:
            raise ValueError("Primary keyword is required.")

        return keyword.lower()

    def _extract_secondary_keywords(
        self,
        keyword_data: dict[str, Any],
    ) -> list[str]:
        """Extract approved secondary keywords."""

        keywords = keyword_data.get("keywords") or []

        secondary: list[str] = []

        for item in keywords:
            if isinstance(item, dict):
                role = self._normalize_text(item.get("role")).lower()
                keyword = self._normalize_text(item.get("keyword"))
            else:
                role = "secondary"
                keyword = self._normalize_text(item)

            if role == "secondary" and keyword:
                normalized = keyword.lower()

                if normalized not in secondary:
                    secondary.append(normalized)

        return secondary

    def build_title(
        self,
        primary_keyword: str,
        strategy: dict[str, Any],
    ) -> str:
        """Build a deterministic SEO title."""

        proposed_title = self._normalize_text(
            strategy.get("title")
        )

        if proposed_title:
            return proposed_title

        return f"{primary_keyword.title()} | Expert Guide"

    def build_h1(
        self,
        primary_keyword: str,
        strategy: dict[str, Any],
    ) -> str:
        """Build the primary page heading."""

        proposed_h1 = self._normalize_text(
            strategy.get("h1")
        )

        if proposed_h1:
            return proposed_h1

        return primary_keyword.title()

    def build_meta_description(
        self,
        primary_keyword: str,
        strategy: dict[str, Any],
    ) -> str:
        """Build a deterministic meta description."""

        proposed_description = self._normalize_text(
            strategy.get("meta_description")
        )

        if proposed_description:
            limit = get_runtime_config().meta_description_max_characters
            return proposed_description[:limit].rstrip()

        return (
            f"Learn about {primary_keyword}, including practical "
            f"strategies, key considerations, and useful guidance."
        )

    def build_validated_brief(
        self,
        strategy: ContentStrategy,
        *,
        page_url: str | None = None,
        brand_name: str | None = None,
        internal_links: list[InternalLinkRecommendation] | None = None,
        tone: str | None = None,
    ) -> ContentBrief:
        """Create the typed, implementation-ready brief without generating prose."""
        del page_url, brand_name
        primary = strategy.primary_keyword or "the page topic"
        title = (strategy.objective or primary.title())[:80].rstrip()
        seo_title = title[: get_runtime_config().seo_title_max_characters].rstrip()
        meta = f"Learn about {primary}, key considerations, and practical next steps."
        headings = strategy.key_topics or [
            f"Understanding {primary.title()}",
            "Key Considerations",
            "Practical Next Steps",
        ]
        outline = [
            ContentSection(
                heading_level=2,
                heading=heading,
                objective=f"Explain {heading.lower()} clearly and practically.",
                keywords=[primary] if index == 0 else [],
                questions_to_answer=[],
            )
            for index, heading in enumerate(dict.fromkeys(headings))
        ]
        target = strategy.recommended_word_count_max
        if strategy.recommended_word_count_min and target:
            target = (strategy.recommended_word_count_min + target) // 2
        return ContentBrief(
            title=title,
            alternative_titles=[],
            seo_title=seo_title,
            meta_description=meta[: get_runtime_config().meta_description_max_characters],
            slug=None,
            h1=title,
            outline=outline,
            introduction_goal=f"Answer the main question about {primary} immediately.",
            conclusion_goal="Give the reader a concise, practical next step.",
            primary_keyword=strategy.primary_keyword,
            secondary_keywords=strategy.secondary_keywords,
            target_word_count=target,
            keyword_guidance=["Use keywords only where they improve clarity."],
            internal_links=internal_links or [],
            faq_questions=[],
            CTA=strategy.cta,
            source_requirements=["Use only supplied, verifiable source material."],
            prohibited_claims=[
                "Unsupported statistics, rankings, certifications, quotes, or product claims"
            ],
            tone=tone,
        )

    def build_headings(
        self,
        primary_keyword: str,
        strategy: dict[str, Any],
        secondary_keywords: list[str],
    ) -> list[str]:
        """Build a structured heading outline."""

        supplied_headings = strategy.get("headings") or []

        headings: list[str] = []

        if isinstance(supplied_headings, list):
            for heading in supplied_headings:
                normalized = self._normalize_text(heading)

                if normalized and normalized not in headings:
                    headings.append(normalized)

        if not headings:
            headings = [
                f"What Is {primary_keyword.title()}?",
                f"Why {primary_keyword.title()} Matters",
            ]

            if secondary_keywords:
                headings.append(
                    f"How to Choose {secondary_keywords[0].title()}"
                )

            headings.extend(
                [
                    f"Best Practices for {primary_keyword.title()}",
                    "Frequently Asked Questions",
                ]
            )

        return headings

    def build_content_brief(
        self,
        primary_keyword: str,
        secondary_keywords: list[str],
        strategy: dict[str, Any],
        competitor_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build the structured brief that will guide content generation.
        """

        competitor_analysis = competitor_analysis or {}

        content_gaps = competitor_analysis.get(
            "content_gaps",
            [],
        )

        if not isinstance(content_gaps, list):
            content_gaps = []

        return {
            "primary_keyword": primary_keyword,
            "secondary_keywords": secondary_keywords,
            "search_intent": self._normalize_text(
                strategy.get("search_intent")
            ).lower()
            or "informational",
            "objective": self._normalize_text(
                strategy.get("objective")
            ),
            "headings": self.build_headings(
                primary_keyword=primary_keyword,
                strategy=strategy,
                secondary_keywords=secondary_keywords,
            ),
            "content_gaps": [
                self._normalize_text(gap)
                for gap in content_gaps
                if self._normalize_text(gap)
            ],
        }

    async def write(
        self,
        keyword_data: dict[str, Any],
        strategy: dict[str, Any],
        competitor_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a structured content package from approved SEO inputs.
        """

        primary_keyword = self._extract_primary_keyword(keyword_data)

        secondary_keywords = self._extract_secondary_keywords(
            keyword_data
        )

        title = self.build_title(
            primary_keyword=primary_keyword,
            strategy=strategy,
        )

        h1 = self.build_h1(
            primary_keyword=primary_keyword,
            strategy=strategy,
        )

        meta_description = self.build_meta_description(
            primary_keyword=primary_keyword,
            strategy=strategy,
        )

        brief = self.build_content_brief(
            primary_keyword=primary_keyword,
            secondary_keywords=secondary_keywords,
            strategy=strategy,
            competitor_analysis=competitor_analysis,
        )

        return {
            "agent": self.name,
            "status": "written",
            "primary_keyword": primary_keyword,
            "secondary_keywords": secondary_keywords,
            "title": title,
            "h1": h1,
            "meta_description": meta_description,
            "headings": brief["headings"],
            "content_brief": brief,
            "body": self._build_draft_body(
                primary_keyword=primary_keyword,
                headings=brief["headings"],
                strategy=strategy,
            ),
            "data_source": "deterministic",
        }

    def _build_draft_body(
        self,
        primary_keyword: str,
        headings: list[str],
        strategy: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Build placeholder content sections.

        This deliberately produces structured draft sections rather than
        pretending deterministic templates are equivalent to high-quality
        LLM-generated prose.
        """

        objective = self._normalize_text(
            strategy.get("objective")
        )

        sections: list[dict[str, str]] = []

        for index, heading in enumerate(headings):
            if index == 0:
                paragraph = (
                    f"This section introduces {primary_keyword} "
                    f"and explains its relevance to the reader."
                )
            elif objective:
                paragraph = (
                    f"This section supports the content objective: "
                    f"{objective}"
                )
            else:
                paragraph = (
                    f"This section provides practical information "
                    f"related to {primary_keyword}."
                )

            sections.append(
                {
                    "heading": heading,
                    "content": paragraph,
                }
            )

        return sections

    async def write_many(
        self,
        content_jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Write multiple content packages."""

        results: list[dict[str, Any]] = []

        for job in content_jobs:
            keyword_data = job.get("keyword_data") or {}
            strategy = job.get("strategy") or {}
            competitor_analysis = job.get("competitor_analysis")

            result = await self.write(
                keyword_data=keyword_data,
                strategy=strategy,
                competitor_analysis=competitor_analysis,
            )

            results.append(result)

        return results
