from __future__ import annotations

import json

import httpx
import pytest

import app.agents.website_auditor as website_auditor_module
from app.agents.website_auditor import WebsiteAuditor
from app.models.contracts import WebsiteAuditRequest


def test_auditor_extracts_normalized_structural_page_evidence() -> None:
    request = httpx.Request("GET", "https://example.com/start")
    response = httpx.Response(
        200,
        request=request,
        headers={"content-type": "text/html"},
        text=(
            '<html lang="en"><head><title>Example</title>'
            '<meta name="description" content="Useful description">'
            '<link rel="canonical" href="/guide"></head>'
            "<body><main><h1>Guide</h1><h2>Overview</h2><h3>Details</h3>"
            "<p>Useful content with enough words for deterministic extraction.</p>"
            '<a href="/next#part">Next</a></main></body></html>'
        ),
    )
    auditor = WebsiteAuditor(delay_seconds=0)
    auditor.allowed_hosts = {"example.com"}

    page, links = auditor.audit_html("https://example.com/start", response)

    assert page["final_url"] == "https://example.com/start"
    assert page["h2_headings"] == ["Overview"]
    assert page["h3_headings"] == ["Details"]
    assert page["word_count"] > 0
    assert page["language"] == "en"
    assert len(page["content_hash"]) == 64
    assert links == ["https://example.com/next"]


@pytest.mark.asyncio
async def test_auditor_blocks_private_network_before_request() -> None:
    with pytest.raises(ValueError, match="public network addresses"):
        await WebsiteAuditor(delay_seconds=0).audit("http://127.0.0.1/internal")


@pytest.mark.asyncio
async def test_auditor_validates_redirect_destination_before_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    async def validate(url: str, **kwargs) -> None:
        del kwargs
        if "127.0.0.1" in url:
            raise ValueError("URL must resolve only to public network addresses.")

    class RedirectClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            requested.append(str(url))
            request = httpx.Request("GET", str(url))
            return httpx.Response(
                302,
                request=request,
                headers={"location": "http://127.0.0.1/internal"},
            )

    monkeypatch.setattr(website_auditor_module, "validate_public_http_url", validate)
    monkeypatch.setattr(website_auditor_module.httpx, "AsyncClient", RedirectClient)

    report = await WebsiteAuditor(delay_seconds=0, max_pages=1).audit(
        "https://example.com"
    )

    assert "http://127.0.0.1/internal" not in requested
    assert any("public network addresses" in item["error"] for item in report["errors"])


def test_audit_request_has_safe_bounds_and_url_normalization() -> None:
    request = WebsiteAuditRequest(website_url="Example.com")
    assert request.website_url == "https://example.com/"
    assert request.max_pages is None
    with pytest.raises(ValueError):
        WebsiteAuditRequest(website_url="https://example.com", max_pages=1_000_001)


@pytest.mark.asyncio
async def test_default_audit_crawls_and_saves_every_reachable_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    pages = {
        "https://example.com": '<a href="/one">One</a>',
        "https://example.com/one": '<a href="/two">Two</a>',
        "https://example.com/two": '<a href="/three">Three</a>',
        "https://example.com/three": "Complete",
    }

    async def allow_public_url(*args, **kwargs) -> None:
        return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            normalized = str(url).rstrip("/")
            request = httpx.Request("GET", str(url))
            if normalized in pages:
                return httpx.Response(
                    200,
                    request=request,
                    headers={"content-type": "text/html"},
                    text=f"<html><body>{pages[normalized]}</body></html>",
                )
            return httpx.Response(404, request=request, text="Not found")

    monkeypatch.setattr(
        website_auditor_module,
        "validate_public_http_url",
        allow_public_url,
    )
    monkeypatch.setattr(website_auditor_module.httpx, "AsyncClient", FakeClient)

    auditor = WebsiteAuditor(delay_seconds=0)
    report = await auditor.audit("https://example.com")
    output_path = tmp_path / "complete-audit.json"
    auditor.save_report(report, str(output_path))
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["max_pages"] is None
    assert report["crawl_limit_reached"] is False
    assert report["pages_crawled"] == 4
    assert saved["pages_crawled"] == 4
    assert {page["url"] for page in saved["pages"]} == set(pages)
