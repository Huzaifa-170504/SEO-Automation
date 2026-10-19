from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_runtime_config
from app.services.url_safety import validate_public_http_url

FetchProgressCallback = Callable[[int, int, str, str], Awaitable[None] | None]


class CompetitorContentFetcher:
    def __init__(
        self,
        timeout: float = 20.0,
        max_bytes: int = 2_000_000,
        max_excerpt_words: int = 600,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_excerpt_words = max_excerpt_words
        self.transport = transport
        self.max_attempts = max(1, max_attempts)

    async def fetch_many(
        self,
        urls: list[str],
        relevance_terms: list[str] | None = None,
        progress_callback: FetchProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        selected_urls = urls[: get_runtime_config().max_competitor_pages]
        completed = 0
        progress_lock = asyncio.Lock()

        async def fetch_one(url: str) -> dict[str, Any] | Exception:
            nonlocal completed
            status = "fetched"
            try:
                return await self.fetch(url, relevance_terms=relevance_terms)
            except Exception as exc:  # noqa: BLE001 - persisted as structured fetch evidence
                status = "unavailable"
                return exc
            finally:
                async with progress_lock:
                    completed += 1
                    if progress_callback is not None:
                        result = progress_callback(
                            completed, len(selected_urls), url, status
                        )
                        if asyncio.iscoroutine(result):
                            await result

        results = await asyncio.gather(*(fetch_one(url) for url in selected_urls))
        pages: list[dict[str, Any]] = []
        for url, result in zip(selected_urls, results, strict=True):
            if isinstance(result, BaseException):
                pages.append(
                    {"url": url, "status": "unavailable", "error": str(result)}
                )
            else:
                pages.append(result)
        return pages

    async def fetch(
        self, url: str, relevance_terms: list[str] | None = None
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Competitor URL must use http:// or https://.")

        # Many publishers reject generic bot user agents even for ordinary public
        # pages. This profile requests the same HTML a normal desktop browser sees.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=False,
            headers=headers,
            transport=self.transport,
        ) as client:
            current_url = url
            for _ in range(4):
                await self._validate_public_url(current_url)
                response = await self._request_with_retry(client, current_url)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError(
                            "Competitor page returned an invalid redirect."
                        )
                    current_url = urljoin(current_url, location)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in {401, 403}:
                        raise ValueError(
                            f"Competitor site denied access (HTTP {status}). "
                            "Use a URL the bot can reach without credentials or a bot challenge."
                        ) from exc
                    raise ValueError(
                        f"Competitor page returned HTTP {status}."
                    ) from exc
                break
            else:
                raise ValueError("Competitor page exceeded the redirect limit.")

        content_type = response.headers.get("content-type", "").lower()
        looks_like_html = response.text.lstrip().lower().startswith(
            ("<!doctype html", "<html")
        )
        if "text/html" not in content_type and not looks_like_html:
            raise ValueError("Competitor URL did not return an HTML page.")
        if len(response.content) > self.max_bytes:
            raise ValueError("Competitor page exceeded the 2 MB analysis limit.")

        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "nav",
                "footer",
                "header",
                "aside",
                "form",
            ]
        ):
            element.decompose()

        title = " ".join(
            (soup.title.get_text(" ", strip=True) if soup.title else "").split()
        )
        description_tag = soup.find("meta", attrs={"name": "description"})
        description = ""
        if description_tag is not None:
            description = " ".join(str(description_tag.get("content") or "").split())
        all_headings = [
            " ".join(heading.get_text(" ", strip=True).split())
            for heading in soup.find_all(["h1", "h2", "h3"])
        ]
        all_headings = [heading for heading in all_headings if heading][:40]
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = " ".join(main.get_text(" ", strip=True).split())
        words = text.split()
        normalized_terms = self._terms(relevance_terms or [])
        headings = self._relevant_headings(all_headings, normalized_terms)
        passages = self._relevant_passages(main, normalized_terms)
        excerpt = " ".join(item["text"] for item in passages)
        sentences = [
            value.strip() for value in re.split(r"(?<=[.!?])\s+", text) if value.strip()
        ]
        paragraph_count = len(
            [
                node
                for node in main.find_all("p")
                if len(node.get_text(" ", strip=True).split()) >= 8
            ]
        )
        list_item_count = len(main.find_all("li"))
        question_heading_count = sum(heading.endswith("?") for heading in all_headings)
        evidence_markers = len(
            re.findall(
                r"\b(?:according to|study|research|data|percent|\d+%)\b",
                text,
                re.IGNORECASE,
            )
        )
        action_markers = len(
            re.findall(
                r"\b(?:step|how to|tip|checklist|choose|compare)\b",
                text,
                re.IGNORECASE,
            )
        )
        quality_score = min(
            100,
            25
            + min(20, len(all_headings) * 3)
            + min(20, paragraph_count * 2)
            + min(15, action_markers * 3)
            + min(10, evidence_markers * 2)
            + (10 if description else 0),
        )
        average_sentence_words = round(len(words) / max(1, len(sentences)), 1)
        return {
            "url": str(response.url),
            "domain": (urlparse(str(response.url)).hostname or "").lower(),
            "status": "fetched",
            "title": title[:300],
            "meta_description": description[:500],
            "headings": headings,
            "all_heading_count": len(all_headings),
            "word_count": len(words),
            "content_excerpt": " ".join(excerpt.split()[: self.max_excerpt_words]),
            "relevant_passages": passages,
            "analysis": {
                "quality_score": quality_score,
                "average_sentence_words": average_sentence_words,
                "paragraph_count": paragraph_count,
                "list_item_count": list_item_count,
                "question_heading_count": question_heading_count,
                "evidence_markers": evidence_markers,
                "actionable_markers": action_markers,
                "content_nature": self._content_nature(
                    list_item_count, question_heading_count, action_markers
                ),
                "wording_style": self._wording_style(average_sentence_words),
            },
        }

    async def _request_with_retry(
        self, client: httpx.AsyncClient, url: str
    ) -> httpx.Response:
        """Retry temporary network and throttling failures with a small backoff."""
        last_error: httpx.HTTPError | None = None
        response: httpx.Response | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await client.get(url)
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                    return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            if attempt + 1 < self.max_attempts:
                await asyncio.sleep(0.4 * (2**attempt))
        if response is not None:
            return response
        raise ValueError(
            "Competitor page could not be reached after multiple attempts."
        ) from last_error

    @staticmethod
    def _terms(values: list[str]) -> list[str]:
        terms: list[str] = []
        for value in values:
            normalized = " ".join(str(value).lower().split())
            if len(normalized) >= 3 and normalized not in terms:
                terms.append(normalized)
            for word in re.findall(r"[a-z0-9][a-z0-9+-]{2,}", normalized):
                if word not in terms:
                    terms.append(word)
        return terms[:30]

    async def _validate_public_url(self, url: str) -> None:
        """Block private/link-local destinations for user-supplied fetches."""
        if self.transport is not None:
            return
        await validate_public_http_url(
            url, allow_private=get_runtime_config().allow_private_urls
        )

    @staticmethod
    def _score(text: str, terms: list[str]) -> int:
        lowered = text.lower()
        return sum(3 if " " in term else 1 for term in terms if term in lowered)

    def _relevant_headings(self, headings: list[str], terms: list[str]) -> list[str]:
        if not terms:
            return headings[:12]
        relevant = [heading for heading in headings if self._score(heading, terms)]
        return (relevant or headings[:8])[:16]

    def _relevant_passages(self, main: Any, terms: list[str]) -> list[dict[str, Any]]:
        candidates: list[tuple[int, int, str, str]] = []
        current_heading = ""
        order = 0
        for node in main.find_all(["h1", "h2", "h3", "p", "li"]):
            value = " ".join(node.get_text(" ", strip=True).split())
            if node.name in {"h1", "h2", "h3"}:
                current_heading = value
                continue
            if len(value.split()) < 8:
                continue
            score = self._score(f"{current_heading} {value}", terms)
            candidates.append((score, order, current_heading, value))
            order += 1

        ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
        if terms and any(item[0] > 0 for item in ranked):
            strongest_score = ranked[0][0]
            minimum_score = max(2, int(strongest_score * 0.4))
            ranked = [item for item in ranked if item[0] >= minimum_score]
        selected: list[tuple[int, int, str, str]] = []
        word_total = 0
        for item in ranked:
            remaining = self.max_excerpt_words - word_total
            if remaining <= 0 or len(selected) >= 10:
                break
            passage_words = item[3].split()[:remaining]
            if not passage_words:
                continue
            selected.append((item[0], item[1], item[2], " ".join(passage_words)))
            word_total += len(passage_words)
        selected.sort(key=lambda item: item[1])
        return [
            {
                "heading": heading,
                "text": value,
                "word_count": len(value.split()),
                "relevance_score": score,
            }
            for score, _, heading, value in selected
        ]

    @staticmethod
    def _content_nature(
        list_item_count: int, question_heading_count: int, action_markers: int
    ) -> str:
        if list_item_count >= 5 or action_markers >= 4:
            return "practical/how-to"
        if question_heading_count >= 2:
            return "question-led explainer"
        return "editorial explainer"

    @staticmethod
    def _wording_style(average_sentence_words: float) -> str:
        if average_sentence_words <= 14:
            return "concise and direct"
        if average_sentence_words >= 23:
            return "dense and formal"
        return "balanced and explanatory"
