from __future__ import annotations

import json

import httpx
import pytest

from app.models.qwen import QwenClient


@pytest.mark.asyncio
async def test_generate_sends_expected_chat_request() -> None:
    """Verify Qwen receives the expected Ollama chat payload."""
    captured_request: dict[str, object] = {}

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        captured_request.update(json.loads(request.content))

        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "Generated SEO response",
                },
                "prompt_eval_count": 11,
                "eval_count": 17,
            },
        )

    client = QwenClient(
        base_url="http://testserver",
        model="qwen-seo:4b",
    )

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        result = await client.generate(
            prompt="Write an SEO title.",
            system="You are an SEO specialist.",
            temperature=0.4,
            top_p=0.8,
            top_k=24,
        )
    finally:
        await client.close()

    assert result == "Generated SEO response"
    assert client.last_usage == {
        "provider": "qwen",
        "model": "qwen-seo:4b",
        "input_tokens": 11,
        "output_tokens": 17,
        "total_tokens": 28,
    }

    assert captured_request == {
        "model": "qwen-seo:4b",
        "messages": [
            {
                "role": "system",
                "content": "You are an SEO specialist.",
            },
            {
                "role": "user",
                "content": "Write an SEO title.",
            },
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 4096,
            "num_ctx": 32768,
            "top_p": 0.8,
            "top_k": 24,
        },
    }


@pytest.mark.asyncio
async def test_generate_works_without_system_prompt() -> None:
    """Verify generate supports prompts without a system message."""
    captured_request: dict[str, object] = {}

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        captured_request.update(json.loads(request.content))

        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "Response without system prompt",
                },
            },
        )

    client = QwenClient(base_url="http://testserver")

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        result = await client.generate(
            prompt="Analyze this page.",
        )
    finally:
        await client.close()

    assert result == "Response without system prompt"

    assert captured_request["messages"] == [
        {
            "role": "user",
            "content": "Analyze this page.",
        },
    ]


@pytest.mark.asyncio
async def test_generate_raises_for_empty_response() -> None:
    """Verify an empty Qwen response is rejected."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "",
                },
            },
        )

    client = QwenClient(base_url="http://testserver")

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="Qwen returned an empty response",
        ):
            await client.generate("Test prompt")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_generate_raises_for_http_error() -> None:
    """Verify HTTP errors from Ollama are propagated."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": "Ollama server error",
            },
        )

    client = QwenClient(base_url="http://testserver")

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.generate("Test prompt")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_health_check_returns_true_when_ollama_is_reachable() -> None:
    """Verify a successful Ollama health check."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == "/api/tags"

        return httpx.Response(
            200,
            json={
                "models": [],
            },
        )

    client = QwenClient(base_url="http://testserver")

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        assert await client.health_check() is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_health_check_returns_false_when_ollama_is_unreachable() -> None:
    """Verify a failed Ollama health check returns False."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    client = QwenClient(base_url="http://testserver")

    await client.client.aclose()

    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )

    try:
        assert await client.health_check() is False
    finally:
        await client.close()


def test_qwen_client_uses_explicit_configuration() -> None:
    """Verify explicit client configuration is preserved."""
    client = QwenClient(
        base_url="http://localhost:12345/",
        model="custom-qwen-model",
        timeout=42.0,
    )

    assert client.base_url == "http://localhost:12345"
    assert client.model == "custom-qwen-model"
    assert client.timeout == 42.0


def test_qwen_client_reads_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Qwen configuration can be supplied through environment variables."""
    monkeypatch.setenv(
        "OLLAMA_BASE_URL",
        "http://env-server:11434/",
    )

    monkeypatch.setenv(
        "QWEN_MODEL",
        "qwen-seo:4b",
    )

    client = QwenClient()

    assert client.base_url == "http://env-server:11434"
    assert client.model == "qwen-seo:4b"


def test_qwen_client_defaults_to_local_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the default Ollama endpoint and current model fallback."""
    monkeypatch.delenv(
        "OLLAMA_BASE_URL",
        raising=False,
    )

    monkeypatch.delenv(
        "QWEN_MODEL",
        raising=False,
    )

    client = QwenClient()

    assert client.base_url == "http://127.0.0.1:11434"
    assert client.model == "qwen-seo:4b"
