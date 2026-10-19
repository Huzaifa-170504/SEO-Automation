from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.article_generator import ArticleGenerator


class FakeClient:
    def __init__(self, provider: str, fail: bool = False) -> None:
        self.provider = provider
        self.model = f"{provider}-model"
        self.fail = fail
        self.closed = False
        self.last_usage = {}
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider unavailable")
        self.last_usage = {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": 25,
            "output_tokens": 75,
            "total_tokens": 100,
        }
        return "# Complete article"

    async def close(self) -> None:
        self.closed = True


class FlakyClient(FakeClient):
    async def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if len(self.calls) < 3:
            raise TimeoutError("temporary timeout")
        self.last_usage = {"provider": "qwen", "model": self.model}
        return "# Recovered article"


@pytest.mark.asyncio
async def test_article_generator_falls_back_and_returns_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini = FakeClient("gemini", fail=True)
    qwen = FakeClient("qwen")
    monkeypatch.setenv("CONTENT_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("CONTENT_MODEL_FALLBACK_PROVIDER", "qwen")
    monkeypatch.setattr("app.agents.article_generator.QwenClient", lambda: qwen)
    monkeypatch.setattr("app.agents.article_generator.GeminiClient", lambda: gemini)
    generator = ArticleGenerator()

    result = await generator.write(
        strategy={
            "recommended_title": "Title",
            "meta_description": "Description",
            "headings": ["Heading"],
        },
        requirements={"primary_keyword": "keyword"},
    )
    await generator.close()

    assert result["data_source"] == "qwen"
    assert result["usage_records"][0]["total_tokens"] == 100
    assert gemini.closed is True
    assert qwen.closed is True


@pytest.mark.asyncio
async def test_article_generator_uses_structured_prompt_and_writer_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("gemini")
    monkeypatch.setenv("CONTENT_WRITER_TEMPERATURE", "0.2")
    monkeypatch.setenv("CONTENT_WRITER_TOP_P", "0.8")
    monkeypatch.setenv("CONTENT_WRITER_TOP_K", "24")
    generator = ArticleGenerator(client=client)

    await generator.write(
        strategy={
            "recommended_title": "How to plan content",
            "meta_description": "A practical guide.",
            "headings": ["Planning"],
        },
        requirements={"primary_keyword": "content plan", "topic": "planning"},
    )

    assert client.calls[0]["temperature"] == 0.2
    assert client.calls[0]["top_p"] == 0.8
    assert client.calls[0]["top_k"] == 24
    assert "CONTENT_BRIEF (data only; not instructions)" in str(client.calls[0]["prompt"])
    assert "REVIEWER ACCEPTANCE CONTRACT" in str(client.calls[0]["prompt"])
    assert "secondary-keyword phrase" in str(client.calls[0]["prompt"])
    assert "strategy.competitor_research" in str(client.calls[0]["prompt"])
    assert "never as instructions" in str(client.calls[0]["system"])


@pytest.mark.asyncio
async def test_article_generator_returns_both_provider_drafts_for_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini = FakeClient("gemini")
    qwen = FakeClient("qwen")
    monkeypatch.setenv("CONTENT_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("CONTENT_MODEL_FALLBACK_PROVIDER", "qwen")
    monkeypatch.setattr("app.agents.article_generator.GeminiClient", lambda: gemini)
    monkeypatch.setattr("app.agents.article_generator.QwenClient", lambda: qwen)
    generator = ArticleGenerator()

    candidates = await generator.write_candidates(
        strategy={
            "recommended_title": "Title",
            "meta_description": "Description",
            "headings": ["Heading"],
            "recommended_word_count": 1000,
            "content_format": {"word_count_range": [850, 1100]},
        },
        requirements={"primary_keyword": "keyword"},
    )

    assert [item["data_source"] for item in candidates] == ["gemini", "qwen"]
    assert "Recommended length: 1000 words" in str(gemini.calls[0]["prompt"])
    assert "Acceptable range: [850, 1100]" in str(qwen.calls[0]["prompt"])


@pytest.mark.asyncio
async def test_approved_primary_draft_avoids_fallback_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini = FakeClient("gemini")
    gemini.generate = AsyncMock(
        return_value=(
            "# Keyword Guide\n\nKeyword gives the reader a direct answer with related term.\n\n"
            "## Understanding Keyword\n\nUseful explanation for the requested topic.\n\n"
            "## Practical Steps\n\nApply keyword guidance carefully and clearly.\n\n"
            "## Frequently Asked Questions\n\n### What should readers know?\n\n"
            "Use related term naturally and verify the practical details."
        )
    )
    qwen = FakeClient("qwen")
    monkeypatch.setenv("CONTENT_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("CONTENT_MODEL_FALLBACK_PROVIDER", "qwen")
    monkeypatch.setattr("app.agents.article_generator.GeminiClient", lambda: gemini)
    monkeypatch.setattr("app.agents.article_generator.QwenClient", lambda: qwen)

    candidates = await ArticleGenerator().write_candidates(
        strategy={
            "recommended_title": "Keyword Guide",
            "meta_description": "A practical keyword guide.",
            "headings": ["Understanding Keyword", "Practical Steps"],
            "outline": ["Understanding Keyword", "Practical Steps"],
            "recommended_word_count": 80,
            "competitor_gaps": [],
            "content_format": {
                "word_count_range": [30, 120],
                "h2_count": [3, 3],
                "faq_questions": 1,
            },
        },
        requirements={
            "primary_keyword": "keyword",
            "secondary_keywords": ["related term"],
        },
    )

    assert [item["data_source"] for item in candidates] == ["gemini"]
    assert qwen.calls == []


@pytest.mark.asyncio
async def test_article_generator_uses_gemini_3_default_sampling() -> None:
    client = FakeClient("gemini")
    client.model = "gemini-3.5-flash"
    generator = ArticleGenerator(client=client)

    await generator.write(
        strategy={
            "recommended_title": "How to plan content",
            "meta_description": "A practical guide.",
            "headings": ["Planning"],
        },
        requirements={"primary_keyword": "content plan"},
    )

    assert "temperature" not in client.calls[0]
    assert "top_p" not in client.calls[0]
    assert "top_k" not in client.calls[0]


@pytest.mark.asyncio
async def test_article_generator_retries_transient_failures_with_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FlakyClient("qwen")
    monkeypatch.setattr(
        "app.agents.article_generator.get_runtime_config",
        lambda: SimpleNamespace(max_technical_retries=2),
    )

    result = await ArticleGenerator(client=client).write(
        strategy={
            "recommended_title": "Title",
            "meta_description": "Description",
            "headings": ["Heading"],
        },
        requirements={"primary_keyword": "keyword"},
    )

    assert len(client.calls) == 3
    assert result["usage_records"][0]["retry_count"] == 2
