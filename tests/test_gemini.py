from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.models.gemini import GeminiClient


class FakeGenerateContent:
    """Mock Gemini generate_content API."""

    def __init__(
        self,
        response: Any,
    ) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        model: str,
        contents: str,
        config: Any,
    ) -> Any:
        self.calls.append(
            {
                "model": model,
                "contents": contents,
                "config": config,
            }
        )
        return self.response


class FakeModels:
    """Mock Gemini models API."""

    def __init__(
        self,
        response: Any,
    ) -> None:
        self.generate_content = FakeGenerateContent(response)


class FakeAio:
    """Mock asynchronous Gemini client interface."""

    def __init__(
        self,
        response: Any,
    ) -> None:
        self.models = FakeModels(response)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeGeminiClient:
    """Mock Google GenAI client containing the async interface."""

    def __init__(
        self,
        fake_aio: FakeAio,
    ) -> None:
        self.aio = fake_aio


def make_response(
    text: str,
    input_tokens: int = 10,
    output_tokens: int = 20,
    total_tokens: int = 30,
) -> Any:
    """Create a fake Gemini response with usage metadata."""
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=input_tokens,
            candidates_token_count=output_tokens,
            total_token_count=total_tokens,
        ),
    )


def replace_client(
    client: GeminiClient,
    fake_aio: FakeAio,
) -> None:
    """Replace the real Google client with a test double."""
    client.client = FakeGeminiClient(fake_aio)


@pytest.mark.asyncio
async def test_generate_sends_expected_request() -> None:
    """Verify Gemini receives the expected generation request."""
    response = make_response(
        "Generated SEO response",
        input_tokens=15,
        output_tokens=25,
        total_tokens=40,
    )

    fake_aio = FakeAio(response)

    client = GeminiClient(
        api_key="test-api-key",
        model="gemini-test-model",
    )

    replace_client(client, fake_aio)

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

    assert len(fake_aio.models.generate_content.calls) == 1

    call = fake_aio.models.generate_content.calls[0]

    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "Write an SEO title."

    config = call["config"]

    assert config.system_instruction == ("You are an SEO specialist.")
    assert config.temperature == 0.4
    assert config.top_p == 0.8
    assert config.top_k == 24


@pytest.mark.asyncio
async def test_generate_records_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Gemini token usage is recorded."""
    monkeypatch.delenv(
        "GEMINI_MODEL",
        raising=False,
    )

    response = make_response(
        "SEO response",
        input_tokens=12,
        output_tokens=18,
        total_tokens=30,
    )

    fake_aio = FakeAio(response)

    client = GeminiClient(api_key="test-api-key")

    replace_client(client, fake_aio)

    try:
        result = await client.generate(prompt="Analyze this page.")
    finally:
        await client.close()

    assert result == "SEO response"

    assert client.last_usage == {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "input_tokens": 12,
        "output_tokens": 18,
        "total_tokens": 30,
    }


@pytest.mark.asyncio
async def test_generate_works_without_system_prompt() -> None:
    """Verify generation works without a system instruction."""
    response = make_response("Response without system prompt")

    fake_aio = FakeAio(response)

    client = GeminiClient(api_key="test-api-key")

    replace_client(client, fake_aio)

    try:
        result = await client.generate(prompt="Analyze this page.")
    finally:
        await client.close()

    assert result == "Response without system prompt"

    call = fake_aio.models.generate_content.calls[0]

    config = call["config"]

    assert config.system_instruction is None


@pytest.mark.asyncio
async def test_generate_raises_for_empty_response() -> None:
    """Verify an empty Gemini response is rejected."""
    response = make_response("")

    fake_aio = FakeAio(response)

    client = GeminiClient(api_key="test-api-key")

    replace_client(client, fake_aio)

    try:
        with pytest.raises(
            RuntimeError,
            match="Gemini returned an empty response",
        ):
            await client.generate("Test prompt")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_generate_handles_missing_usage_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify generation works when Gemini provides no usage metadata."""
    monkeypatch.delenv(
        "GEMINI_MODEL",
        raising=False,
    )

    response = SimpleNamespace(
        text="Response without usage",
        usage_metadata=None,
    )

    fake_aio = FakeAio(response)

    client = GeminiClient(api_key="test-api-key")

    replace_client(client, fake_aio)

    try:
        result = await client.generate("Test prompt")
    finally:
        await client.close()

    assert result == "Response without usage"

    assert client.last_usage == {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def test_gemini_client_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Gemini requires an API key."""
    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValueError,
        match="GEMINI_API_KEY is missing",
    ):
        GeminiClient()


def test_gemini_client_uses_explicit_configuration() -> None:
    """Verify explicit Gemini configuration is preserved."""
    client = GeminiClient(
        api_key="explicit-key",
        model="custom-gemini-model",
        timeout=42.0,
    )

    assert client.api_key == "explicit-key"
    assert client.model == "custom-gemini-model"
    assert client.timeout == 42.0


def test_gemini_client_reads_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Gemini configuration can come from environment variables."""
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "environment-key",
    )

    monkeypatch.setenv(
        "GEMINI_MODEL",
        "gemini-environment-model",
    )

    client = GeminiClient()

    assert client.api_key == "environment-key"
    assert client.model == "gemini-environment-model"


def test_gemini_client_defaults_to_expected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the default Gemini model."""
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    monkeypatch.delenv(
        "GEMINI_MODEL",
        raising=False,
    )

    client = GeminiClient()

    assert client.model == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_close_closes_async_client() -> None:
    """Verify the asynchronous Gemini client is closed."""
    response = make_response("Response")

    fake_aio = FakeAio(response)

    client = GeminiClient(api_key="test-api-key")

    replace_client(client, fake_aio)

    await client.close()

    assert fake_aio.closed is True
