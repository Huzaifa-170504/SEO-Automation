
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from app.config import get_runtime_config
from app.models.contracts import WebsiteAuditRequest
from app.services.url_safety import validate_public_http_url

logger = logging.getLogger(__name__)

USER_AGENT = "SEOAutomationAuditBot/1.0"


class WebsiteAuditor:
    """Crawl and audit discoverable pages on a website."""

    def __init__(
        self,
        timeout: float | None = None,
        max_pages: int | None = None,
        delay_seconds: float = 0.5,
        progress_callback=None,
    ):
        config = get_runtime_config()
        self.timeout = timeout if timeout is not None else config.http_timeout_seconds
        self.max_pages = max_pages if max_pages is not None else config.max_audit_pages
        self.delay_seconds = delay_seconds
        self.progress_callback = progress_callback

        self.base_url = ""
        self.allowed_hosts: set[str] = set()
        self.visited: set[str] = set()
        self.queued: set[str] = set()
        self.pages: list[dict] = []
        self.errors: list[dict] = []
        self.robots: RobotFileParser | None = None
        self.respect_robots_txt = True
        self.use_sitemap = True

    @staticmethod
    def normalize_url(url: str) -> str:
        """Remove fragments and normalize URL formatting."""
        url = urldefrag(url.strip())[0]
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return ""

        if not parsed.hostname:
            return ""

        if parsed.username or parsed.password:
            return ""

        return url.rstrip("/") or url

    def is_internal(self, url: str) -> bool:
        """Check whether a URL belongs to the audited host."""
        host = (urlparse(url).hostname or "").lower()
        return host in self.allowed_hosts

    def is_allowed_by_robots(self, url: str) -> bool:
        if self.robots is None:
            return True

        return self.robots.can_fetch(USER_AGENT, url)

    async def _safe_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        require_internal: bool = True,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """Follow redirects only after validating every destination."""
        current_url = url
        for _ in range(max_redirects + 1):
            await validate_public_http_url(
                current_url,
                allow_private=get_runtime_config().allow_private_urls,
            )
            if require_internal and not self.is_internal(current_url):
                raise ValueError("Redirected URL is outside the audited website.")
            response = await client.get(current_url)
            if not response.is_redirect:
                return response
            location = response.headers.get("location")
            next_url = urldefrag(urljoin(current_url, location or ""))[0].strip()
            parsed = urlparse(next_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Website returned an invalid redirect target.")
            current_url = next_url
        raise ValueError("Website exceeded the maximum redirect count.")

    async def fetch_robots(
        self,
        client: httpx.AsyncClient,
    ) -> list[str]:
        """Read robots.txt and return declared sitemap URLs."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        sitemap_urls = []

        try:
            response = await self._safe_get(client, robots_url)

            if response.status_code == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                self.robots = parser

                for line in response.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        if sitemap_url:
                            sitemap_urls.append(sitemap_url)

            else:
                self.errors.append({
                    "url": robots_url,
                    "error": f"robots.txt returned HTTP {response.status_code}",
                })

        except (httpx.HTTPError, ValueError) as exc:
            self.errors.append({
                "url": robots_url,
                "error": str(exc),
            })

        return sitemap_urls

    async def fetch_sitemap(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        discovered: set[str],
        seen_sitemaps: set[str],
    ) -> None:
        """Read sitemap files and recursively follow sitemap indexes."""
        sitemap_url = self.normalize_url(sitemap_url)

        if not sitemap_url or sitemap_url in seen_sitemaps:
            return

        if not self.is_internal(sitemap_url):
            return

        seen_sitemaps.add(sitemap_url)

        try:
            response = await self._safe_get(client, sitemap_url)
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)

            for element in root:
                tag = element.tag.split("}")[-1].lower()

                if tag == "loc" and element.text:
                    url = self.normalize_url(element.text)

                    if url and self.is_internal(url):
                        discovered.add(url)

                elif tag in ("sitemap", "url"):
                    loc = next(
                        (
                            child.text
                            for child in element
                            if child.tag.split("}")[-1].lower() == "loc"
                            and child.text
                        ),
                        None,
                    )

                    if not loc:
                        continue

                    if tag == "sitemap":
                        await self.fetch_sitemap(
                            client,
                            loc,
                            discovered,
                            seen_sitemaps,
                        )
                    else:
                        url = self.normalize_url(loc)
                        if url and self.is_internal(url):
                            discovered.add(url)

        except (
            httpx.HTTPError,
            ElementTree.ParseError,
            ValueError,
        ) as exc:
            self.errors.append({
                "url": sitemap_url,
                "error": f"Sitemap error: {exc}",
            })

    def audit_html(
        self,
        url: str,
        response: httpx.Response,
    ) -> tuple[dict, list[str]]:
        """Extract on-page SEO signals and discover internal links."""
        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

        description_tag = soup.find(
            "meta",
            attrs={"name": re.compile("^description$", re.IGNORECASE)},
        )
        description = (
            description_tag.get("content", "").strip()
            if description_tag
            else ""
        )

        h1_tags = soup.find_all("h1")
        h1_headings = [
            heading.get_text(" ", strip=True)
            for heading in h1_tags
        ]
        h2_headings = [item.get_text(" ", strip=True) for item in soup.find_all("h2")]
        h3_headings = [item.get_text(" ", strip=True) for item in soup.find_all("h3")]
        main = soup.find("main") or soup.find("article") or soup.body or soup
        main_text = " ".join(main.get_text(" ", strip=True).split())
        word_count = len(re.findall(r"\b[\w'-]+\b", main_text))
        html_tag = soup.find("html")
        language = str(html_tag.get("lang") or "").strip() if html_tag else ""

        canonical_tag = soup.find(
            "link",
            rel=lambda value: value and "canonical" in value,
        )
        canonical = (
            urljoin(url, canonical_tag.get("href", ""))
            if canonical_tag
            else None
        )

        robots_tag = soup.find(
            "meta",
            attrs={"name": re.compile("^robots$", re.IGNORECASE)},
        )
        robots_content = (
            robots_tag.get("content", "").strip()
            if robots_tag
            else ""
        )

        images = soup.find_all("img")
        missing_alt = [
            urljoin(url, image.get("src", ""))
            for image in images
            if not image.get("alt", "").strip()
        ]

        internal_links = set()
        external_links = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()

            if not href or href.startswith(
                ("#", "mailto:", "tel:", "javascript:", "data:")
            ):
                continue

            absolute_url = self.normalize_url(urljoin(url, href))

            if not absolute_url:
                continue

            if self.is_internal(absolute_url):
                internal_links.add(absolute_url)
            else:
                external_links.add(absolute_url)

        issues = []

        if not title:
            issues.append("Missing title")
        elif len(title) > 60:
            issues.append("Title longer than 60 characters")

        if not description:
            issues.append("Missing meta description")
        elif len(description) > 160:
            issues.append("Meta description longer than 160 characters")

        if not h1_tags:
            issues.append("Missing H1 heading")
        elif len(h1_tags) > 1:
            issues.append("Multiple H1 headings")

        if missing_alt:
            issues.append(f"{len(missing_alt)} images missing alt text")

        if not canonical:
            issues.append("Missing canonical tag")

        if "noindex" in robots_content.lower():
            issues.append("Page has a noindex robots directive")

        if response.status_code >= 400:
            issues.append(f"HTTP error {response.status_code}")

        page = {
            "url": url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "title": title,
            "title_length": len(title),
            "meta_description": description,
            "meta_description_length": len(description),
            "h1_headings": h1_headings,
            "h1_count": len(h1_tags),
            "h2_headings": h2_headings,
            "h3_headings": h3_headings,
            "canonical": canonical,
            "robots": robots_content,
            "image_count": len(images),
            "images_missing_alt": missing_alt,
            "internal_link_count": len(internal_links),
            "external_link_count": len(external_links),
            "content_length": len(main_text),
            "word_count": word_count,
            "language": language or None,
            "content_hash": hashlib.sha256(main_text.encode("utf-8")).hexdigest(),
            "issues": issues,
        }

        return page, sorted(internal_links)

    async def audit(self, website_url: str) -> dict:
        """Crawl discoverable pages and return a full audit report."""
        website_url = website_url.strip()

        if not website_url.startswith(("http://", "https://")):
            website_url = f"https://{website_url}"

        parsed = urlparse(website_url)

        if not parsed.hostname:
            raise ValueError("Please provide a valid website URL.")

        await validate_public_http_url(
            website_url,
            allow_private=get_runtime_config().allow_private_urls,
        )

        self.base_url = f"{parsed.scheme}://{parsed.netloc}/"
        hostname = parsed.hostname.lower()
        self.allowed_hosts = {hostname}
        if hostname.startswith("www."):
            self.allowed_hosts.add(hostname.removeprefix("www."))
        else:
            self.allowed_hosts.add(f"www.{hostname}")

        self.visited = set()
        self.queued = set()
        self.pages = []
        self.errors = []

        queue = deque()
        seen_sitemaps = set()
        sitemap_urls = []

        start_url = self.normalize_url(website_url)
        queue.append(start_url)
        self.queued.add(start_url)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:

            if self.respect_robots_txt or self.use_sitemap:
                sitemap_urls.extend(await self.fetch_robots(client))

            if self.use_sitemap:
                for path in (
                    "/sitemap.xml",
                    "/sitemap_index.xml",
                    "/sitemap-index.xml",
                    "/wp-sitemap.xml",
                ):
                    sitemap_urls.append(urljoin(self.base_url, path))

            sitemap_pages = set()

            for sitemap_url in sitemap_urls if self.use_sitemap else []:
                await self.fetch_sitemap(
                    client,
                    sitemap_url,
                    sitemap_pages,
                    seen_sitemaps,
                )

            for url in sorted(sitemap_pages):
                if url not in self.queued:
                    queue.append(url)
                    self.queued.add(url)

            while queue and (
                self.max_pages is None or len(self.visited) < self.max_pages
            ):
                url = queue.popleft()

                if url in self.visited:
                    continue

                if not self.is_internal(url):
                    continue

                if self.respect_robots_txt and not self.is_allowed_by_robots(url):
                    self.errors.append({
                        "url": url,
                        "error": "Blocked by robots.txt",
                    })
                    continue

                self.visited.add(url)

                try:
                    response = await self._safe_get(client, url)

                    if self.progress_callback is not None:
                        await self.progress_callback(
                            pages_crawled=len(self.pages),
                            errors_count=len(self.errors),
                            queued_count=len(queue),
                            current_url=str(response.url),
                        )

                    content_type = response.headers.get(
                        "content-type", ""
                    ).lower()

                    if "text/html" not in content_type:
                        self.errors.append({
                            "url": url,
                            "error": (
                                f"Skipped non-HTML response: {content_type}"
                            ),
                            "status_code": response.status_code,
                        })
                        continue

                    page, internal_links = self.audit_html(
                        str(response.url),
                        response,
                    )
                    page["requested_url"] = url
                    self.pages.append(page)

                    if self.progress_callback is not None:
                        await self.progress_callback(
                            pages_crawled=len(self.pages),
                            errors_count=len(self.errors),
                            queued_count=len(queue),
                            current_url=str(response.url),
                        )

                    for link in internal_links:
                        if link not in self.queued and (
                            self.max_pages is None
                            or len(self.queued) < self.max_pages * 2
                        ):
                            queue.append(link)
                            self.queued.add(link)

                except (httpx.HTTPError, ValueError) as exc:
                    self.errors.append({
                        "url": url,
                        "error": str(exc),
                    })

                    if self.progress_callback is not None:
                        await self.progress_callback(
                            pages_crawled=len(self.pages),
                            errors_count=len(self.errors),
                            queued_count=len(queue),
                            current_url=url,
                        )

                await asyncio.sleep(self.delay_seconds)

        # Detect duplicate titles and descriptions.
        title_counts = {}
        for page in self.pages:
            title = page["title"].strip().lower()
            if title:
                title_counts[title] = title_counts.get(title, 0) + 1

        for page in self.pages:
            if (
                page["title"].strip()
                and title_counts.get(page["title"].strip().lower(), 0) > 1
            ):
                page["issues"].append("Duplicate title found")

        hash_counts: dict[str, int] = {}
        for page in self.pages:
            content_hash = page.get("content_hash")
            if content_hash:
                hash_counts[content_hash] = hash_counts.get(content_hash, 0) + 1
        for page in self.pages:
            if hash_counts.get(page.get("content_hash"), 0) > 1:
                page["issues"].append("Duplicate page content found")

        report = {
            "website": self.base_url,
            "pages_discovered": len(self.queued),
            "pages_crawled": len(self.pages),
            "pages_failed": len(self.errors),
            "max_pages": self.max_pages,
            "crawl_limit_reached": bool(queue) and self.max_pages is not None,
            "sitemaps_found": sorted(seen_sitemaps),
            "errors_count": len(self.errors),
            "errors": self.errors,
            "pages": self.pages,
        }

        return report

    async def audit_request(self, request: WebsiteAuditRequest) -> dict:
        """Typed audit entry point while preserving the legacy dictionary report."""
        previous = (
            self.timeout,
            self.max_pages,
            self.respect_robots_txt,
            self.use_sitemap,
        )
        self.timeout = request.request_timeout_seconds
        self.max_pages = request.max_pages
        self.respect_robots_txt = request.respect_robots_txt
        self.use_sitemap = request.use_sitemap
        try:
            return await self.audit(request.website_url)
        finally:
            (
                self.timeout,
                self.max_pages,
                self.respect_robots_txt,
                self.use_sitemap,
            ) = previous

    @staticmethod
    def save_report(
        report: dict,
        output_path: str,
    ) -> str:
        """Save the audit report to a JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return str(path)
