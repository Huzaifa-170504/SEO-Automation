from __future__ import annotations

import httpx
import pytest

from app.services.competitor_content import CompetitorContentFetcher


@pytest.mark.asyncio
async def test_fetch_many_extracts_two_competitor_pages() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<html><head><title>Useful Guide</title>"
                '<meta name="description" content="A useful description"></head>'
                "<body><nav>Menu</nav><main><h1>Main Topic</h1>"
                "<h2>Practical Steps</h2><p>Detailed useful content.</p>"
                "</main></body></html>"
            ),
            request=request,
        )

    fetcher = CompetitorContentFetcher(transport=httpx.MockTransport(handler))
    progress = []

    async def on_progress(completed, total, url, status):
        progress.append((completed, total, url, status))

    pages = await fetcher.fetch_many(
        ["https://one.example/article", "https://two.example/guide"],
        progress_callback=on_progress,
    )

    assert len(pages) == 2
    assert all(page["status"] == "fetched" for page in pages)
    assert pages[0]["title"] == "Useful Guide"
    assert pages[0]["headings"] == ["Main Topic", "Practical Steps"]
    assert "Menu" not in pages[0]["content_excerpt"]
    assert sorted(item[0] for item in progress) == [1, 2]
    assert all(item[3] == "fetched" for item in progress)


@pytest.mark.asyncio
async def test_fetch_many_records_unavailable_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    fetcher = CompetitorContentFetcher(transport=httpx.MockTransport(handler))
    pages = await fetcher.fetch_many(["https://one.example/article"])

    assert pages[0]["status"] == "unavailable"
    assert pages[0]["url"] == "https://one.example/article"


@pytest.mark.asyncio
async def test_fetch_keeps_only_compact_relevant_passages() -> None:
    unrelated = " ".join(["unrelated navigation copy"] * 100)
    relevant = "AI trading bot risk controls help traders set practical loss limits."

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<main><h1>Trading guide</h1>"
                f"<p>{unrelated}</p>"
                "<h2>AI trading bot risk controls</h2>"
                f"<p>{relevant}</p></main>"
            ),
            request=request,
        )

    page = await CompetitorContentFetcher(
        transport=httpx.MockTransport(handler), max_excerpt_words=40
    ).fetch("https://one.example/article", ["AI trading bot", "risk controls"])

    assert relevant in page["content_excerpt"]
    assert "unrelated navigation copy" not in page["content_excerpt"]
    assert len(page["content_excerpt"].split()) <= 40
    assert page["analysis"]["wording_style"]
    assert page["analysis"]["content_nature"]


@pytest.mark.asyncio
async def test_fetch_rejects_private_network_destination() -> None:
    with pytest.raises(ValueError, match="public network addresses"):
        await CompetitorContentFetcher().fetch("http://127.0.0.1/internal")


@pytest.mark.asyncio
async def test_fetch_retries_temporary_server_failure() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><main><h1>Guide</h1><p>Useful public article content here.</p></main></html>",
            request=request,
        )

    page = await CompetitorContentFetcher(
        transport=httpx.MockTransport(handler), max_attempts=2
    ).fetch("https://one.example/article")

    assert attempts == 2
    assert page["status"] == "fetched"


@pytest.mark.asyncio
async def test_fetch_explains_access_denied_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    with pytest.raises(ValueError, match="URL the bot can reach"):
        await CompetitorContentFetcher(
            transport=httpx.MockTransport(handler), max_attempts=1
        ).fetch("https://one.example/article")
