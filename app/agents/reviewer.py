from __future__ import annotations

import re
from typing import Any

from app.config import get_runtime_config
from app.models.contracts import (
    ReviewIssue,
    ReviewRequest,
    ReviewResult,
    RevisionTarget,
)


class Reviewer:
    """
    Quality-control agent for SEO content.

    Responsibilities:
    - Validate generated content against the approved SEO strategy.
    - Check keyword usage and basic on-page requirements.
    - Identify missing or potentially problematic elements.
    - Return structured validation results.

    This initial implementation is deterministic. AI-assisted review can
    be added later without changing the reviewer contract.
    """

    def __init__(self) -> None:
        self.name = "reviewer"

    def _normalize(self, value: Any) -> str:
        """Normalize text for validation."""

        if value is None:
            return ""

        return " ".join(str(value).strip().split())

    def _normalize_lower(self, value: Any) -> str:
        """Normalize text and convert it to lowercase."""

        return self._normalize(value).lower()

    def _keyword_occurrences(
        self,
        content: str,
        keyword: str,
    ) -> int:
        """Count case-insensitive keyword occurrences."""

        normalized_content = self._normalize_lower(content)
        normalized_keyword = self._normalize_lower(keyword)

        if not normalized_content or not normalized_keyword:
            return 0

        return normalized_content.count(normalized_keyword)

    def _combine_content(
        self,
        content: dict[str, Any],
    ) -> str:
        """Combine relevant content fields for validation."""

        parts: list[str] = []

        for field in (
            "title",
            "h1",
            "meta_description",
        ):
            value = self._normalize(content.get(field))

            if value:
                parts.append(value)

        headings = content.get("headings") or []

        if isinstance(headings, list):
            parts.extend(
                self._normalize(heading)
                for heading in headings
                if self._normalize(heading)
            )

        body = content.get("body") or []

        if isinstance(body, list):
            for section in body:
                if not isinstance(section, dict):
                    continue

                heading = self._normalize(section.get("heading"))
                section_content = self._normalize(section.get("content"))

                if heading:
                    parts.append(heading)

                if section_content:
                    parts.append(section_content)

        elif isinstance(body, str):
            parts.append(self._normalize(body))

        return " ".join(parts)

    def check_required_elements(
        self,
        content: dict[str, Any],
    ) -> list[str]:
        """Check whether essential SEO content elements exist."""

        issues: list[str] = []

        if not self._normalize(content.get("title")):
            issues.append("Missing SEO title.")

        if not self._normalize(content.get("h1")):
            issues.append("Missing H1 heading.")

        if not self._normalize(content.get("meta_description")):
            issues.append("Missing meta description.")

        headings = content.get("headings") or []

        if not isinstance(headings, list) or not headings:
            issues.append("Missing heading structure.")

        body = content.get("body") or []

        if not body:
            issues.append("Missing body content.")

        return issues

    def check_primary_keyword(
        self,
        content: dict[str, Any],
        primary_keyword: str,
    ) -> dict[str, Any]:
        """Validate primary keyword usage."""

        keyword = self._normalize_lower(primary_keyword)
        combined_content = self._combine_content(content)

        occurrences = self._keyword_occurrences(
            combined_content,
            keyword,
        )

        return {
            "keyword": keyword,
            "occurrences": occurrences,
            "present": occurrences > 0,
        }

    def check_secondary_keywords(
        self,
        content: dict[str, Any],
        secondary_keywords: list[str],
    ) -> list[dict[str, Any]]:
        """Validate secondary keyword usage."""

        combined_content = self._combine_content(content)

        results: list[dict[str, Any]] = []

        for keyword in secondary_keywords:
            normalized_keyword = self._normalize_lower(keyword)

            if not normalized_keyword:
                continue

            occurrences = self._keyword_occurrences(
                combined_content,
                normalized_keyword,
            )

            results.append(
                {
                    "keyword": normalized_keyword,
                    "occurrences": occurrences,
                    "present": occurrences > 0,
                }
            )

        return results

    def check_headings(
        self,
        content: dict[str, Any],
        primary_keyword: str,
    ) -> dict[str, Any]:
        """Validate heading structure."""

        headings = content.get("headings") or []

        if not isinstance(headings, list):
            headings = []

        normalized_headings = [
            self._normalize(heading) for heading in headings if self._normalize(heading)
        ]

        primary_keyword = self._normalize_lower(primary_keyword)

        keyword_in_heading = any(
            primary_keyword in heading.lower() for heading in normalized_headings
        )

        return {
            "heading_count": len(normalized_headings),
            "has_headings": bool(normalized_headings),
            "primary_keyword_in_heading": keyword_in_heading,
        }

    def check_content_gaps(
        self,
        content: dict[str, Any],
        content_gaps: list[str],
    ) -> list[str]:
        """
        Check whether supplied competitor/content gaps are represented
        somewhere in the generated content.

        This is a basic phrase-presence check, not a semantic judgment.
        """

        combined_content = self._combine_content(content)

        missing_gaps: list[str] = []

        for gap in content_gaps:
            normalized_gap = self._normalize_lower(gap)

            if not normalized_gap:
                continue

            if normalized_gap not in combined_content.lower():
                missing_gaps.append(gap)

        return missing_gaps

    def detect_keyword_stuffing(
        self,
        content: dict[str, Any],
        primary_keyword: str,
        threshold: int = 20,
    ) -> dict[str, Any]:
        """Detect unusually frequent exact-match keyword repetition."""

        occurrences = self._keyword_occurrences(
            self._combine_content(content),
            primary_keyword,
        )

        return {
            "keyword": self._normalize_lower(primary_keyword),
            "occurrences": occurrences,
            "threshold": threshold,
            "possible_stuffing": occurrences > threshold,
        }

    def check_content_format(
        self,
        content: dict[str, Any],
        strategy: dict[str, Any],
        primary_keyword: str,
    ) -> list[str]:
        specification = strategy.get("content_format") or {}
        body = content.get("body")
        issues: list[str] = []
        title = self._normalize(content.get("title"))
        meta = self._normalize(content.get("meta_description"))
        config = get_runtime_config()
        if len(title) > config.seo_title_max_characters:
            issues.append(
                f"SEO title is {len(title)} characters; the configured guideline is {config.seo_title_max_characters}."
            )
        if len(meta) > config.meta_description_max_characters:
            issues.append(
                f"Meta description is {len(meta)} characters; the configured guideline is {config.meta_description_max_characters}."
            )
        headings = [
            self._normalize(value)
            for value in (content.get("headings") or [])
            if self._normalize(value)
        ]
        if len({value.casefold() for value in headings}) != len(headings):
            issues.append("Heading structure contains duplicate headings.")
        if not isinstance(body, str):
            return issues

        h1_count = len(re.findall(r"(?m)^#\s+", body))
        if h1_count != 1:
            issues.append(f"Markdown article must contain exactly one H1; found {h1_count}.")
        seen_h2 = False
        for match in re.finditer(r"(?m)^(#{2,3})\s+(.+)$", body):
            level = len(match.group(1))
            if level == 2:
                seen_h2 = True
            elif not seen_h2:
                issues.append("Markdown contains an H3 before any parent H2.")
                break
        word_count = len(re.findall(r"\b[\w'-]+\b", body))
        word_range = specification.get("word_count_range")
        if (
            isinstance(word_range, list)
            and len(word_range) == 2
            and not word_range[0] <= word_count <= word_range[1]
        ):
            issues.append(
                f"Article length is {word_count} words; target is {word_range[0]}-{word_range[1]}."
            )

        first_words = " ".join(body.split()[:100]).lower()
        if self._normalize_lower(primary_keyword) not in first_words:
            issues.append("Primary keyword is missing from the first 100 words.")

        h2_count = len(re.findall(r"(?m)^##\s+", body))
        h2_range = specification.get("h2_count")
        if (
            isinstance(h2_range, list)
            and len(h2_range) == 2
            and not h2_range[0] <= h2_count <= h2_range[1]
        ):
            issues.append(
                f"Article has {h2_count} H2 sections; target is {h2_range[0]}-{h2_range[1]}."
            )

        faq_questions = int(specification.get("faq_questions") or 0)
        if faq_questions and "## frequently asked questions" not in body.lower():
            issues.append("Missing the required Frequently Asked Questions section.")
        internal_links = strategy.get("internal_links")
        if isinstance(internal_links, dict):
            for link_type in ("contact", "login"):
                url = self._normalize(internal_links.get(link_type))
                if url and url not in body:
                    issues.append(f"Missing the required {link_type} page link: {url}")
        return issues

    async def review(
        self,
        content: dict[str, Any],
        keyword_data: dict[str, Any],
        strategy: dict[str, Any],
        competitor_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Review generated content against approved SEO inputs.
        """

        primary_keyword_data = keyword_data.get("primary_keyword") or {}

        if isinstance(primary_keyword_data, dict):
            primary_keyword = self._normalize(primary_keyword_data.get("keyword"))
        else:
            primary_keyword = self._normalize(primary_keyword_data)

        if not primary_keyword:
            raise ValueError("Primary keyword is required.")

        keywords = keyword_data.get("keywords") or []

        secondary_keywords: list[str] = []

        for item in keywords:
            if not isinstance(item, dict):
                continue

            role = self._normalize_lower(item.get("role"))
            keyword = self._normalize(item.get("keyword"))

            if role == "secondary" and keyword:
                secondary_keywords.append(keyword)

        competitor_analysis = competitor_analysis or {}

        content_gaps = competitor_analysis.get("content_gaps") or []

        if not isinstance(content_gaps, list):
            content_gaps = []

        required_element_issues = self.check_required_elements(content)

        primary_keyword_result = self.check_primary_keyword(
            content=content,
            primary_keyword=primary_keyword,
        )

        secondary_keyword_results = self.check_secondary_keywords(
            content=content,
            secondary_keywords=secondary_keywords,
        )

        heading_result = self.check_headings(
            content=content,
            primary_keyword=primary_keyword,
        )

        missing_gaps = self.check_content_gaps(
            content=content,
            content_gaps=content_gaps,
        )

        stuffing_result = self.detect_keyword_stuffing(
            content=content,
            primary_keyword=primary_keyword,
        )
        format_issues = self.check_content_format(content, strategy, primary_keyword)

        issues: list[str] = []

        issues.extend(required_element_issues)
        issues.extend(format_issues)

        if not primary_keyword_result["present"]:
            issues.append("Primary keyword is not present in the generated content.")

        for result in secondary_keyword_results:
            if not result["present"]:
                issues.append(f"Secondary keyword is missing: {result['keyword']}")

        if not heading_result["has_headings"]:
            issues.append("Content has no usable heading structure.")

        if stuffing_result["possible_stuffing"]:
            issues.append("Primary keyword appears unusually frequently.")

        for gap in missing_gaps:
            issues.append(f"Content gap not represented: {gap}")

        structured_issues = self._structured_issues(issues)
        critical_failure = any(
            item.severity == "critical" for item in structured_issues
        )
        seo_score = max(
            0.0,
            100.0
            - sum(
                {"critical": 40, "high": 20, "medium": 10, "low": 5, "info": 0}[
                    item.severity
                ]
                for item in structured_issues
            ),
        )
        intent_score = max(0.0, 100.0 - (20.0 * len(missing_gaps)))
        quality_score = 0.0 if "Missing body content." in issues else 100.0
        readability_score = 100.0
        evidence_score = 100.0
        overall_score = round(
            seo_score * 0.2
            + intent_score * 0.25
            + quality_score * 0.25
            + readability_score * 0.1
            + evidence_score * 0.1
            + seo_score * 0.1,
            1,
        )
        status = (
            "approved"
            if not issues
            and overall_score >= get_runtime_config().article_approval_score
            and not critical_failure
            else "needs_revision"
        )
        revision_target = self._revision_target(issues)
        rich_result = ReviewResult(
            status=status,
            overall_score=overall_score,
            seo_score=seo_score,
            quality_score=quality_score,
            intent_score=intent_score,
            readability_score=readability_score,
            evidence_score=evidence_score,
            deterministic_failures=structured_issues,
            semantic_issues=[],
            strengths=(
                ["Required fields and deterministic SEO checks passed."]
                if not issues
                else []
            ),
            revision_instructions=[
                item.suggested_fix or item.message for item in structured_issues
            ],
            revision_target=revision_target,
            critical_failure=critical_failure,
            reason=(
                "All deterministic checks passed."
                if status == "approved"
                else f"{len(issues)} deterministic issue(s) require correction."
            ),
        )

        return {
            "agent": self.name,
            "status": status,
            "primary_keyword": primary_keyword.lower(),
            "required_element_issues": required_element_issues,
            "primary_keyword_check": primary_keyword_result,
            "secondary_keyword_checks": secondary_keyword_results,
            "heading_check": heading_result,
            "missing_content_gaps": missing_gaps,
            "keyword_stuffing_check": stuffing_result,
            "content_format_issues": format_issues,
            "issues": issues,
            "issue_count": len(issues),
            "search_intent": self._normalize_lower(strategy.get("search_intent")),
            **rich_result.model_dump(mode="json"),
        }

    @staticmethod
    def _structured_issues(messages: list[str]) -> list[ReviewIssue]:
        results: list[ReviewIssue] = []
        for message in messages:
            lower = message.lower()
            if "missing body" in lower:
                severity = "critical"
                code = "missing_main_content"
            elif "stuff" in lower:
                severity = "high"
                code = "keyword_stuffing"
            elif "missing h1" in lower or "heading structure" in lower:
                severity = "high"
                code = "invalid_heading_structure"
            elif "meta description" in lower:
                severity = "medium"
                code = "metadata_issue"
            elif "content gap" in lower:
                severity = "medium"
                code = "content_gap"
            else:
                severity = "low"
                code = re.sub(r"[^a-z0-9]+", "_", lower).strip("_")[:60]
            results.append(
                ReviewIssue(
                    code=code or "review_issue",
                    severity=severity,
                    message=message,
                    suggested_fix=f"Correct this issue: {message}",
                )
            )
        return results

    @staticmethod
    def _revision_target(messages: list[str]) -> RevisionTarget:
        combined = " ".join(messages).lower()
        if "content gap" in combined or "search intent" in combined:
            return RevisionTarget.CONTENT_STRATEGIST
        if "heading structure" in combined or "h2 sections" in combined:
            return RevisionTarget.CONTENT_WRITER
        if messages:
            return RevisionTarget.ARTICLE_GENERATOR
        return RevisionTarget.NONE

    async def review_request(self, request: ReviewRequest) -> ReviewResult:
        """Typed reviewer entry point with explicit revision-limit behavior."""
        article = request.article
        content = {
            "title": article.seo_title,
            "h1": article.h1,
            "meta_description": article.meta_description,
            "headings": [item.heading for item in request.brief.outline],
            "body": article.markdown_body,
        }
        keyword_data = {
            "primary_keyword": {"keyword": request.brief.primary_keyword},
            "keywords": [
                {"keyword": item, "role": "secondary"}
                for item in request.brief.secondary_keywords
            ],
        }
        legacy = await self.review(
            content,
            keyword_data,
            request.strategy.model_dump(mode="json", by_alias=True),
            {"content_gaps": request.strategy.content_gaps},
        )
        result = ReviewResult.model_validate(legacy)
        if result.status == "needs_revision" and request.revision_number >= request.max_revisions:
            result.status = "human_review_required"
            result.reason = (
                f"Maximum revision limit ({request.max_revisions}) reached. "
                + result.reason
            )
        return result

    async def review_many(
        self,
        review_jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Review multiple content packages."""

        results: list[dict[str, Any]] = []

        for job in review_jobs:
            result = await self.review(
                content=job.get("content") or {},
                keyword_data=job.get("keyword_data") or {},
                strategy=job.get("strategy") or {},
                competitor_analysis=job.get("competitor_analysis"),
            )

            results.append(result)

        return results
